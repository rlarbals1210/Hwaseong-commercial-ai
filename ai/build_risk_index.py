"""
실제 폐업률(현황) + 예측 순위(조기경보) + 트렌드 이상탐지 -> risk_index.csv 생성
final_dataset.csv(트레일링 통계) + scores.csv(셀단위 모델 추론)를 결합해 RiskIndex 테이블용 CSV 생성.

Phase 6(2026-08-04) 재작성: "실제값=현황, 예측값=조기경보 순위"로 역할을 완전히 분리했다.
직전 버전(Phase 5)은 예측폐업률(100-성장확률, label_h2 기준 +2분기 후 폐업 확률)을 그대로
화면 절대값·등급 산정에 썼는데, 실측 결과 예측값이 실제 관측 폐업률보다 평균 2.38배(중앙값
2.48배) 구조적으로 높게 나온다는 게 확인됨(진단: 예측평균 7.84% vs 실제평균 3.30%, 표본≥30
n=382). 화성시 평균 실제 폐업률(3.22%)에서 뽑은 색 등급 기준선을 예측값에 그대로 적용하다 보니
표본충분 셀의 57%가 "위험"으로 쏠리는 문제가 있었다.

원인은 두 값의 "성격"이 다르다는 데 있다 — 실제 폐업률(폐업_률_평균)은 "이번 분기 실적"이고
예측값(label_h2)은 "관측시점+2분기 후 폐업 확률"이라 절대 스케일을 맞춰 섞어 쓸 수 없다.
그래서 보정 대신 역할을 나눴다:
  - 지도·순위표(현황 진단) = 실제 폐업률 그대로, 화면에 절대 %로 노출. 보정 없음.
  - 조기경보(예측) = 예측값은 셀 순위 매기는 데만 쓰고 절대값은 화면에 노출하지 않음
    ("예측 위험 순위"만 표시, 실제 최근 폐업률을 팩트로 병기).
  - 성장확률은 위험도와 별개인 "성장성" 지표로 계속 분리 보존.

표본수(점포수) 30 미만 셀은 소표본 노이즈로 순위·등급을 오염시키므로(진단: 표본<30 비율 78.5%)
표본부족_플래그로 분리해 등급·순위 산정에서 제외(목록에는 남기되 "표본부족"으로 별도 표시).

색 등급 경계값(화성시 평균 실제 폐업률, 평균의 2배)은 하드코딩하지 않고 매 실행 시 최신 분기
final_dataset.csv에서 점포수 가중평균으로 계산해 risk_thresholds.json에 저장한다.

사용법:
    python ai/build_risk_index.py
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import linregress

SAMPLE_MIN = 30  # 표본부족 판정 기준 (점포수)


def calc_slope(series: pd.Series) -> float:
    vals = series.dropna().values
    if len(vals) < 2:
        return 0.0
    slope, *_ = linregress(range(len(vals)), vals)
    return float(slope)


def grade_row(actual_pct: float, sample_ok: bool, avg_pct: float, danger_pct: float) -> str:
    """실제 폐업률(%) 기준 등급 — 예측값이 아닌 실측치로만 판정."""
    if not sample_ok:
        return "표본부족"
    if actual_pct >= danger_pct:
        return "위험"
    if actual_pct >= avg_pct:
        return "주의"
    return "안정"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/processed/final_dataset.csv", type=Path)
    parser.add_argument("--scores", default="data/processed/scores.csv", type=Path)
    parser.add_argument("--output", default="data/processed/risk_index.csv", type=Path)
    parser.add_argument("--thresholds-output", default="data/processed/risk_thresholds.json", type=Path)
    args = parser.parse_args()

    print("데이터 로드 중...")
    df = pd.read_csv(args.dataset, encoding="utf-8-sig", low_memory=False)
    scores = pd.read_csv(args.scores, encoding="utf-8-sig")

    # 최근 4분기 폐업률 추이
    quarters = sorted(df["기준_년분기_코드"].unique())[-4:]
    df4 = df[df["기준_년분기_코드"].isin(quarters)].copy()

    print("트렌드 기울기 계산 중...")
    slopes = (
        df4.groupby(["행정동명", "통합카테고리"])["폐업_률_평균"]
        .apply(calc_slope)
        .reset_index()
        .rename(columns={"폐업_률_평균": "트렌드_기울기"})
    )
    slope_std = slopes["트렌드_기울기"].std()
    slopes["이상탐지_플래그"] = slopes["트렌드_기울기"] > slope_std

    # 최신 분기 실적치(실제 폐업률·개업률·점포수) + scores(예측용, 순위 산정 전용) 결합
    latest = df["기준_년분기_코드"].max()
    df_latest = df[df["기준_년분기_코드"] == latest][
        ["행정동명", "통합카테고리", "폐업_률_평균", "개업_율_평균", "업종_포화도", "점포수"]
    ].copy()

    # 화성시 평균 실제 폐업률(점포수 가중) -> 색 등급 기준선. 실제값 기준, 하드코딩 금지.
    avg_closure_pct = round(
        (df_latest["폐업_률_평균"] * df_latest["점포수"]).sum() / df_latest["점포수"].sum() * 100, 2
    )
    danger_pct = round(avg_closure_pct * 2, 2)
    print(f"기준선(실제값 기준): 화성시 평균 폐업률 {avg_closure_pct}% / 위험 임계값(2배) {danger_pct}%")

    merged = scores.merge(df_latest, on=["행정동명", "통합카테고리"], how="left")
    merged = merged.merge(slopes, on=["행정동명", "통합카테고리"], how="left")

    merged["폐업_률_평균"] = merged["폐업_률_평균"].fillna(0)
    merged["개업_율_평균"] = merged["개업_율_평균"].fillna(0)
    merged["업종_포화도"] = merged["업종_포화도"].fillna(0)
    merged["점포수"] = merged["점포수"].fillna(0).astype(int)

    merged["실제폐업률_pct"] = (merged["폐업_률_평균"] * 100).round(2)
    merged["개업률_pct"] = (merged["개업_율_평균"] * 100).round(2)
    merged["표본부족_플래그"] = merged["점포수"] < SAMPLE_MIN

    # 지도·순위표용 등급 — 실제 폐업률만 사용 (예측값 관여 없음)
    merged["위험등급"] = merged.apply(
        lambda r: grade_row(r["실제폐업률_pct"], not r["표본부족_플래그"], avg_closure_pct, danger_pct),
        axis=1,
    )

    # 조기경보용 예측 순위 — 예측폐업률(100-성장확률, label_h2 기준)은 순위 산정에만 쓰고
    # 절대값 자체는 CSV/DB에는 남겨두되(내부용, 디버깅) API 응답에는 노출하지 않는다(routers/alerts.py).
    # 표본부족 셀은 순위 대상에서 제외(rank는 NaN).
    merged["_예측폐업률_내부용"] = (100 - merged["성장확률"]).round(1)
    sample_ok = ~merged["표본부족_플래그"]
    merged["예측순위"] = pd.NA
    # method="first": 동률이어도 1..N 연속 정수로 순위를 매김(Top 10 카드에 "#5"가 두 번 뜨고
    # "#6"이 비는 문제 방지 — method="min"으로 처음 구현했다가 스크린샷 검증에서 발견)
    merged.loc[sample_ok, "예측순위"] = (
        merged.loc[sample_ok, "_예측폐업률_내부용"].rank(ascending=False, method="first").astype(int)
    )

    # 읍면동별 "위험 업종 비율" = 위험 등급 셀 수 / 표본충분 셀 수 (실제값 기준, choropleth용)
    def dong_ratio(g: pd.DataFrame) -> float:
        big = g[~g["표본부족_플래그"]]
        if len(big) == 0:
            return 0.0
        return round((big["위험등급"] == "위험").sum() / len(big) * 100, 1)

    dong_risk_ratio = (
        merged.groupby("행정동명")
        .apply(dong_ratio, include_groups=False)
        .reset_index(name="위험업종비율")
    )
    merged = merged.merge(dong_risk_ratio, on="행정동명", how="left")

    # 위험업종비율(0~33% 대) 자체 분포는 실제폐업률(0~18% 대)과 스케일이 다른 별도 지표이므로
    # 지도(동단위) 등급 기준선도 따로 계산한다 — 셀단위 기준선을 재사용하면 또 스케일 불일치가 생김.
    dong_ratio_avg = round(dong_risk_ratio["위험업종비율"].mean(), 2)
    dong_ratio_danger = round(dong_ratio_avg * 2, 2)
    print(f"기준선(동단위 위험업종비율): 평균 {dong_ratio_avg}% / 위험 임계값(2배) {dong_ratio_danger}%")

    out = merged[[
        "행정동명", "통합카테고리", "기준_년분기_코드",
        "실제폐업률_pct", "위험등급", "표본부족_플래그", "위험업종비율",
        "예측순위", "성장확률", "점포수", "개업률_pct", "업종_포화도",
        "트렌드_기울기", "이상탐지_플래그",
        "_예측폐업률_내부용",
    ]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {args.output} ({len(out):,}행)")

    thresholds = {
        "avg_closure_rate_pct": avg_closure_pct,
        "danger_threshold_pct": danger_pct,
        "dong_ratio_avg_pct": dong_ratio_avg,
        "dong_ratio_danger_pct": dong_ratio_danger,
        "sample_min": SAMPLE_MIN,
        "quarter": int(latest),
    }
    args.thresholds_output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.thresholds_output, "w", encoding="utf-8") as f:
        json.dump(thresholds, f, ensure_ascii=False, indent=2)
    print(f"임계값 저장 완료: {args.thresholds_output} ({thresholds})")


if __name__ == "__main__":
    main()
