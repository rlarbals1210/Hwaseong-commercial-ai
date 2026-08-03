"""
화성시 소상공인 데이터셋 구축

소상공인시장진흥공단 "상가(상권)정보" 21개 분기 스냅샷(2020년4분기~2025년4분기)을
화성시(시군구코드=41590)로 필터링하고, 상가업소번호가 분기 간 존재하는지를 비교(diff)해
행정동×업종×분기 단위 점포수/개업율/폐업율을 산출한다.

원본에는 매출·유동인구 수치가 없다(소상공인진흥공단의 별도 상품인 "상권분석서비스" API로만
얻을 수 있음, 이번엔 미확보) — 그래서 "성장여부" 라벨은 매출 증가 대신 다음 분기 점포수
증가 여부로 정의한다. 다운스트림(train_model.py, build_risk_index.py, DB 스키마)이 참조하는
컬럼명(성장여부/성장확률 등)은 그대로 유지해 영향 범위를 최소화했다.

사용법:
    python ai/build_dataset.py [--output data/processed/final_dataset.csv]
"""
import argparse
import io
import os
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

HWASEONG_SGG = "41590"

RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
STORE_ZIP_DIR = (
    RAW_DATA_DIR / "Hwaseong-commercial-ai-main-dataset" / "소상공인시장진흥공단_상가(상권)정보_분기별데이터"
)

# 원본 상권업종대분류명(데이터 파일 내 축약형 — 별도 코드표 파일의 정식 명칭과 다름, 실제 값
# 기준으로 확인함) → 통합카테고리. 현재는 1:1 매핑, 필요시 세분화.
CATEGORY_MAP = {
    "소매": "소매",
    "숙박": "숙박",
    "음식": "음식",
    "부동산": "부동산",
    "과학·기술": "과학·기술",
    "시설관리·임대": "시설관리·임대",
    "교육": "교육",
    "보건의료": "보건의료",
    "예술·스포츠": "예술·스포츠",
    "수리·개인": "수리·개인",
}

QUARTER_MONTH = {"03": 1, "06": 2, "09": 3, "12": 4}

# 정규 분기말(0930) 파일이 없는 대신 발간된 비정규 날짜 — 파일명 날짜 → 기준_년분기_코드 직접 매핑
QUARTER_OVERRIDE = {"20251031": 20253}

USECOLS = ["상가업소번호", "시군구코드", "행정동명", "상권업종대분류명"]

FEATURE_COLS = ["점포수", "개업_율_평균", "폐업_률_평균", "업종_포화도", "경쟁강도"]


def quarter_code(zip_path: Path) -> int:
    m = re.search(r"(\d{8})", zip_path.stem)
    if not m:
        raise ValueError(f"파일명에서 날짜를 찾을 수 없음: {zip_path.name}")
    date_str = m.group(1)
    if date_str in QUARTER_OVERRIDE:
        return QUARTER_OVERRIDE[date_str]
    year, month = date_str[:4], date_str[4:6]
    return int(f"{year}{QUARTER_MONTH[month]}")


def _read_gyeonggi_csv(zf: zipfile.ZipFile) -> pd.DataFrame:
    name = next(n for n in zf.namelist() if "경기" in n and n.endswith(".csv"))
    with zf.open(name) as f:
        return pd.read_csv(f, encoding="utf-8", usecols=USECOLS, dtype={"시군구코드": str}, low_memory=False)


def load_snapshot(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path, metadata_encoding="cp949") as outer:
        nested = [n for n in outer.namelist() if n.endswith(".zip")]
        if nested:
            # 2020Q4~2022Q4: zip 안에 zip이 한 겹 더 있는 구조
            with zipfile.ZipFile(io.BytesIO(outer.read(nested[0])), metadata_encoding="cp949") as inner:
                df = _read_gyeonggi_csv(inner)
        else:
            df = _read_gyeonggi_csv(outer)

    df = df[df["시군구코드"] == HWASEONG_SGG].copy()
    df["통합카테고리"] = df["상권업종대분류명"].map(CATEGORY_MAP).fillna(df["상권업종대분류명"])
    return df[["상가업소번호", "행정동명", "통합카테고리"]]


def load_all_snapshots() -> dict[int, pd.DataFrame]:
    zip_paths = sorted(p for p in STORE_ZIP_DIR.glob("*.zip") if not p.name.startswith("._"))
    if not zip_paths:
        raise FileNotFoundError(f"상가정보 zip 없음: {STORE_ZIP_DIR}")
    snapshots = {}
    for zp in zip_paths:
        q = quarter_code(zp)
        print(f"  {q} 분기 로드 중... ({zp.name})")
        snapshots[q] = load_snapshot(zp)
    return snapshots


def build_dong_category_stats(snapshots: dict[int, pd.DataFrame]) -> pd.DataFrame:
    quarters = sorted(snapshots)
    rows = []
    prev_sets: dict[tuple, set] = {}
    for q in quarters:
        store_sets = snapshots[q].groupby(["행정동명", "통합카테고리"])["상가업소번호"].apply(set)
        for key, store_set in store_sets.items():
            prev_set = prev_sets.get(key)
            row = {
                "행정동명": key[0],
                "통합카테고리": key[1],
                "기준_년분기_코드": q,
                "점포수": len(store_set),
            }
            if prev_set:
                row["개업_율_평균"] = len(store_set - prev_set) / len(prev_set)
                row["폐업_률_평균"] = len(prev_set - store_set) / len(prev_set)
            rows.append(row)
        prev_sets = dict(store_sets.items())
    return pd.DataFrame(rows)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    dong_total = df.groupby(["행정동명", "기준_년분기_코드"])["점포수"].transform("sum")
    df["업종_포화도"] = (df["점포수"] / dong_total.replace(0, np.nan)).round(4)
    df["경쟁강도"] = ((dong_total - df["점포수"]) / df["점포수"].replace(0, np.nan)).round(4)
    return df


def label_growth(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["개업_율_평균", "폐업_률_평균"])  # 직전 분기 없는 첫 분기는 제외
    df = df.sort_values(["행정동명", "통합카테고리", "기준_년분기_코드"])
    df["next_점포수"] = df.groupby(["행정동명", "통합카테고리"])["점포수"].shift(-1)
    df["성장여부"] = (df["next_점포수"] > df["점포수"]).astype(int)
    df = df.dropna(subset=["next_점포수"])
    return df.drop(columns=["next_점포수"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=PROCESSED_DATA_DIR / "final_dataset.csv", type=Path)
    args = parser.parse_args()

    print(f"원본 데이터 위치: {STORE_ZIP_DIR}")
    print("분기별 스냅샷 로드 중...")
    snapshots = load_all_snapshots()

    print("행정동×업종×분기 집계 중...")
    df = build_dong_category_stats(snapshots)
    print(f"  집계 행 수: {len(df):,}")

    print("피처 계산 중...")
    df = build_features(df)

    print("성장 라벨 생성 중...")
    df = label_growth(df)
    print(f"  최종 행 수: {len(df):,}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {args.output}")


if __name__ == "__main__":
    main()
