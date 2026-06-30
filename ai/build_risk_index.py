"""
폐업위험지수 + 트렌드 이상탐지 → risk_index.csv 생성
scores.csv + final_dataset.csv 를 결합해 RiskIndex 테이블용 CSV 생성

사용법:
    python ai/build_risk_index.py
"""
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import linregress


def calc_slope(series: pd.Series) -> float:
    vals = series.dropna().values
    if len(vals) < 2:
        return 0.0
    slope, *_ = linregress(range(len(vals)), vals)
    return float(slope)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/processed/final_dataset.csv", type=Path)
    parser.add_argument("--scores", default="data/processed/scores.csv", type=Path)
    parser.add_argument("--output", default="data/processed/risk_index.csv", type=Path)
    args = parser.parse_args()

    print("데이터 로드 중...")
    df = pd.read_csv(args.dataset, encoding="utf-8-sig", low_memory=False)
    scores = pd.read_csv(args.scores, encoding="utf-8-sig")

    # 최근 4분기 폐업률 추이
    quarters = sorted(df["기준_년분기_코드"].unique())[-4:]
    df4 = df[df["기준_년분기_코드"].isin(quarters)].copy()

    # 트렌드 기울기 계산 (읍면동×업종)
    print("트렌드 기울기 계산 중...")
    slopes = (
        df4.groupby(["행정동명", "통합카테고리"])["폐업_률_평균"]
        .apply(calc_slope)
        .reset_index()
        .rename(columns={"폐업_률_평균": "트렌드_기울기"})
    )

    # 이상탐지 기준: 전체 기울기의 1 std 초과
    slope_std = slopes["트렌드_기울기"].std()
    slopes["이상탐지_플래그"] = slopes["트렌드_기울기"] > slope_std

    # 최신 분기 폐업률 + scores 합치기
    latest = df["기준_년분기_코드"].max()
    df_latest = df[df["기준_년분기_코드"] == latest][["행정동명", "통합카테고리", "폐업_률_평균"]].copy()
    merged = scores.merge(df_latest, on=["행정동명", "통합카테고리"], how="left")
    merged = merged.merge(slopes, on=["행정동명", "통합카테고리"], how="left")

    merged["폐업_률_평균"] = merged["폐업_률_평균"].fillna(0)
    merged["폐업위험점수"] = (
        (100 - merged["성장확률"]) * 0.6 + merged["폐업_률_평균"] * 0.4
    ).round(1)

    # 읍면동별 공실위험지수 (업종 평균)
    anomaly_ratio = (
        merged.groupby("행정동명")["이상탐지_플래그"]
        .apply(lambda x: x.sum() / len(x))
        .reset_index()
        .rename(columns={"이상탐지_플래그": "이상탐지_비율"})
    )
    dong_avg_risk = (
        merged.groupby("행정동명")["폐업위험점수"]
        .mean()
        .reset_index()
        .rename(columns={"폐업위험점수": "평균위험점수"})
    )
    vacancy = dong_avg_risk.merge(anomaly_ratio, on="행정동명")
    vacancy["공실위험지수"] = (vacancy["평균위험점수"] * 0.7 + vacancy["이상탐지_비율"] * 100 * 0.3).round(1)
    merged = merged.merge(vacancy[["행정동명", "공실위험지수"]], on="행정동명", how="left")

    out = merged[[
        "행정동명", "통합카테고리", "기준_년분기_코드",
        "폐업위험점수", "트렌드_기울기", "이상탐지_플래그", "공실위험지수",
    ]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {args.output} ({len(out):,}행)")


if __name__ == "__main__":
    main()
