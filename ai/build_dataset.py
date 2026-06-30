"""
화성시 소상공인 데이터셋 구축
소상공인진흥공단 상권분석서비스 데이터(시군구코드=41590)를 받아
LightGBM 학습용 final_dataset.csv 생성

사용법:
    python ai/build_dataset.py --input data/raw/ --output data/processed/final_dataset.csv
"""
import argparse
import pandas as pd
import numpy as np
from pathlib import Path

HWASEONG_SGG = "41590"

CATEGORY_MAP = {}  # 원본 업종코드 → 통합카테고리 (데이터 수령 후 채울 것)

FEATURE_COLS = [
    "당월매출합", "총_유동인구_수", "점포수", "폐업_률_평균", "개업_율_평균",
    "업종_포화도", "경쟁강도", "업종_점포당매출", "업종_매출점유율",
    "총_직장_인구_수", "주거인구", "월_평균_소득_금액",
    "매출_20대합", "매출_30대합", "매출_40대합", "매출_50대합", "매출_60대이상합",
    "월요일매출합", "화요일매출합", "수요일매출합", "목요일매출합",
    "금요일매출합", "토요일매출합", "일요일매출합",
    "유동_20대", "유동_30대", "유동_40대", "유동_50대", "유동_60대이상",
]


def load_raw(input_dir: Path) -> pd.DataFrame:
    dfs = []
    for f in sorted(input_dir.glob("*.csv")):
        df = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
        # 화성시 필터
        if "시군구_코드" in df.columns:
            df = df[df["시군구_코드"].astype(str).str.startswith(HWASEONG_SGG)]
        dfs.append(df)
    if not dfs:
        raise FileNotFoundError(f"CSV 없음: {input_dir}")
    return pd.concat(dfs, ignore_index=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    # 파생 지표
    df["업종_점포당매출"] = df["당월매출합"] / df["점포수"].replace(0, np.nan)
    행정동_전체매출 = df.groupby(["행정동명", "기준_년분기_코드"])["당월매출합"].transform("sum")
    df["업종_매출점유율"] = df["당월매출합"] / 행정동_전체매출.replace(0, np.nan)
    행정동_전체점포 = df.groupby(["행정동명", "기준_년분기_코드"])["점포수"].transform("sum")
    df["업종_포화도"] = df["점포수"] / df["총_유동인구_수"].replace(0, np.nan)
    df["경쟁강도"] = (행정동_전체점포 - df["점포수"]) / df["점포수"].replace(0, np.nan)

    # 결측 채우기
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0
    df[FEATURE_COLS] = df[FEATURE_COLS].fillna(0)

    return df


def label_growth(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["행정동명", "통합카테고리", "기준_년분기_코드"])
    df["next_sales"] = df.groupby(["행정동명", "통합카테고리"])["당월매출합"].shift(-1)
    df["성장여부"] = (df["next_sales"] > df["당월매출합"]).astype(int)
    df = df.dropna(subset=["next_sales"])
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw", type=Path)
    parser.add_argument("--output", default="data/processed/final_dataset.csv", type=Path)
    args = parser.parse_args()

    print("데이터 로드 중...")
    df = load_raw(args.input)
    print(f"  원본 행 수: {len(df):,}")

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
