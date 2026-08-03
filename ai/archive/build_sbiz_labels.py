"""
소상공인 상가정보 -> 화성시 점포 단위 폐업 라벨 시계열 생성 (전처리 1단계)

소상공인시장진흥공단 "상가(상권)정보" 21개 분기 스냅샷(2020년4분기~2025년4분기)에서
화성시(시군구명='화성시') 행만 추출해 세로 결합하고, 상가업소번호를 분기 간 추적해
"다음 분기에 사라지면 폐업"으로 판정한 점포x분기 패널을 만든다.

ai/build_dataset.py(행정동x업종x분기 집계, 개업율/폐업율)와는 별도 산출물 —
이쪽은 점포 단위 원본 시계열 + is_closed 라벨.

사용법:
    python ai/build_sbiz_labels.py
"""
import glob
import io
import os
import re
import zipfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", str(PROJECT_ROOT)))
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

USECOLS = [
    "상가업소번호", "시군구명", "행정동코드", "행정동명",
    "상권업종대분류명", "상권업종중분류명", "상권업종소분류명",
    "지번주소", "경도", "위도",
]
DTYPE = {
    "상가업소번호": str, "시군구명": str, "행정동코드": str, "행정동명": str,
    "상권업종대분류명": str, "상권업종중분류명": str, "상권업종소분류명": str,
    "지번주소": str, "경도": float, "위도": float,
}

# 정규 분기말(0930) 파일이 없는 대신 발간된 비정규 날짜 -> 실제 기준분기 직접 매핑
QUARTER_OVERRIDE = {"20251031": "2025Q3"}


def find_dataset_dir() -> Path:
    matches = glob.glob(str(RAW_DATA_DIR / "**" / "소상공인시장진흥공단_상가*"), recursive=True)
    dirs = [Path(m) for m in matches if Path(m).is_dir()]
    if not dirs:
        raise FileNotFoundError(f"'소상공인시장진흥공단_상가'로 시작하는 폴더를 찾을 수 없음 (검색 위치: {RAW_DATA_DIR})")
    return dirs[0]


def find_quarter_files(dataset_dir: Path) -> list[tuple[str, Path]]:
    """(기준분기, 파일경로) 리스트. 업종코드 파일은 제외."""
    out = []
    for f in sorted(dataset_dir.iterdir()):
        if "업종코드" in f.name:
            continue
        m = re.search(r"_(\d{8})\.(zip|csv)$", f.name)
        if not m:
            continue
        out.append((date_to_quarter(m.group(1)), f))
    return out


def date_to_quarter(date_str: str) -> str:
    if date_str in QUARTER_OVERRIDE:
        return QUARTER_OVERRIDE[date_str]
    year, month = int(date_str[:4]), int(date_str[4:6])
    q = (month - 1) // 3 + 1
    return f"{year}Q{q}"


def quarter_sort_key(q: str) -> tuple[int, int]:
    year, q_num = q.split("Q")
    return int(year), int(q_num)


def _read_gg_csv(fileobj_or_path) -> pd.DataFrame:
    return pd.read_csv(fileobj_or_path, encoding="utf-8-sig", usecols=USECOLS, dtype=DTYPE, low_memory=False)


def _find_gg_entry(namelist: list[str]) -> str:
    return next(n for n in namelist if "경기" in n and n.endswith(".csv"))


def load_quarter(path: Path) -> pd.DataFrame:
    """zip-직접, zip-안-zip, 이미 풀린 csv 세 경우 모두 처리. 임시 파일 생성 없이 메모리에서만 읽음."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path, metadata_encoding="cp949") as outer:
            nested = [n for n in outer.namelist() if n.endswith(".zip")]
            if nested:
                with zipfile.ZipFile(io.BytesIO(outer.read(nested[0])), metadata_encoding="cp949") as inner:
                    name = _find_gg_entry(inner.namelist())
                    with inner.open(name) as f:
                        return _read_gg_csv(f)
            else:
                name = _find_gg_entry(outer.namelist())
                with outer.open(name) as f:
                    return _read_gg_csv(f)
    return _read_gg_csv(path)


def build_hwaseong_all(dataset_dir: Path) -> pd.DataFrame:
    quarter_files = find_quarter_files(dataset_dir)
    if not quarter_files:
        raise FileNotFoundError(f"분기 파일을 찾을 수 없음: {dataset_dir}")

    frames = []
    for quarter, path in quarter_files:
        df = load_quarter(path)
        df = df[df["시군구명"] == "화성시"].copy()
        df["기준분기"] = quarter
        print(f"  {quarter} ({path.name}): 화성시 {len(df):,}건")
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def build_labels(all_df: pd.DataFrame) -> pd.DataFrame:
    quarters_sorted = sorted(all_df["기준분기"].unique(), key=quarter_sort_key)
    last_quarter = quarters_sorted[-1]
    next_quarter_map = {
        quarters_sorted[i]: quarters_sorted[i + 1] for i in range(len(quarters_sorted) - 1)
    }

    presence_pairs = set(zip(all_df["상가업소번호"], all_df["기준분기"]))

    labels_df = all_df[all_df["기준분기"] != last_quarter].copy()
    labels_df["_next_분기"] = labels_df["기준분기"].map(next_quarter_map)
    labels_df["is_closed"] = [
        0 if (biz, nq) in presence_pairs else 1
        for biz, nq in zip(labels_df["상가업소번호"], labels_df["_next_분기"])
    ]
    return labels_df.drop(columns=["_next_분기"])


def report(all_df: pd.DataFrame, labels_df: pd.DataFrame):
    print("\n=== 분기별 화성시 점포 수 추이 ===")
    counts = all_df.groupby("기준분기")["상가업소번호"].nunique()
    for q in sorted(counts.index, key=quarter_sort_key):
        print(f"  {q}: {counts[q]:,}개")

    total_closed = int(labels_df["is_closed"].sum())
    total_labeled = len(labels_df)
    print(f"\n=== 폐업 라벨 총 건수 ===")
    print(f"  폐업: {total_closed:,} / 전체 라벨: {total_labeled:,}")

    print("\n=== 연도별 폐업률(%) ===")
    labels_df["연도"] = labels_df["기준분기"].str[:4]
    yearly = labels_df.groupby("연도")["is_closed"].agg(["sum", "count"])
    yearly["폐업률(%)"] = (yearly["sum"] / yearly["count"] * 100).round(2)
    for year, row in yearly.iterrows():
        print(f"  {year}: {row['폐업률(%)']}% ({int(row['sum']):,}/{int(row['count']):,})")


def main():
    dataset_dir = find_dataset_dir()
    print(f"원본 데이터 위치: {dataset_dir}")

    print("분기별 화성시 데이터 추출 중...")
    all_df = build_hwaseong_all(dataset_dir)
    print(f"\n전체 결합 행 수: {len(all_df):,}")

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_path = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
    all_df.to_csv(all_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {all_path}")

    print("\n폐업 라벨 생성 중...")
    labels_df = build_labels(all_df)
    labels_path = PROCESSED_DATA_DIR / "sbiz_labels.csv"
    labels_df.to_csv(labels_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {labels_path} ({len(labels_df):,}행)")

    report(all_df, labels_df)


if __name__ == "__main__":
    main()
