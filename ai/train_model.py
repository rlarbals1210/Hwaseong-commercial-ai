"""
LightGBM 학습 → scores.csv 생성
Seoul 프로젝트의 retrain_scores.py와 동일한 로직, 화성시 데이터에 적용

사용법:
    python ai/train_model.py --input data/processed/final_dataset.csv --output data/processed/scores.csv
"""
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
import joblib
from lightgbm import LGBMClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

FEATURE_COLS = [
    "당월매출합", "총_유동인구_수", "점포수", "폐업_률_평균", "개업_율_평균",
    "업종_포화도", "경쟁강도", "업종_점포당매출", "업종_매출점유율",
    "총_직장_인구_수", "주거인구", "월_평균_소득_금액",
    "매출_20대합", "매출_30대합", "매출_40대합", "매출_50대합", "매출_60대이상합",
    "월요일매출합", "화요일매출합", "수요일매출합", "목요일매출합",
    "금요일매출합", "토요일매출합", "일요일매출합",
    "유동_20대", "유동_30대", "유동_40대", "유동_50대", "유동_60대이상",
]


def grade(prob: float) -> str:
    if prob >= 70:
        return "A"
    if prob >= 55:
        return "B"
    if prob >= 40:
        return "C"
    return "D"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/final_dataset.csv", type=Path)
    parser.add_argument("--output", default="data/processed/scores.csv", type=Path)
    parser.add_argument("--model", default="data/processed/lgbm_model.pkl", type=Path)
    args = parser.parse_args()

    print("데이터 로드 중...")
    df = pd.read_csv(args.input, encoding="utf-8-sig", low_memory=False)

    available = [c for c in FEATURE_COLS if c in df.columns]
    X = df[available].fillna(0)
    y = df["성장여부"]

    print(f"학습 데이터: {len(X):,}행, 피처: {len(available)}개")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    model = LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )
    model.fit(X_train, y_train)

    auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    print(f"AUC-ROC: {auc:.3f}")

    args.model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": available, "auc": auc}, args.model)
    print(f"모델 저장 완료: {args.model}")

    # 최신 분기 점수 생성
    latest = df["기준_년분기_코드"].max()
    df_latest = df[df["기준_년분기_코드"] == latest].copy()
    X_latest = df_latest[available].fillna(0)
    df_latest["성장확률"] = (model.predict_proba(X_latest)[:, 1] * 100).round(1)
    df_latest["등급"] = df_latest["성장확률"].apply(grade)

    # 업종 내 순위
    df_latest["업종내_순위"] = df_latest.groupby("통합카테고리")["성장확률"].rank(ascending=False, method="min").astype(int)
    df_latest["업종내_전체동수"] = df_latest.groupby("통합카테고리")["행정동명"].transform("count")
    df_latest["상위_퍼센트"] = (df_latest["업종내_순위"] / df_latest["업종내_전체동수"] * 100).round(1)

    out = df_latest[["행정동명", "통합카테고리", "기준_년분기_코드", "성장확률", "등급", "업종내_순위", "업종내_전체동수", "상위_퍼센트"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {args.output} ({len(out):,}행)")


if __name__ == "__main__":
    main()
