"""
실제 폐업률(현황) + 예측 순위(조기경보) + 트렌드 이상탐지 -> risk_index.csv 생성
final_dataset.csv(트레일링 통계) + scores.csv(셀단위 모델 추론)를 결합해 RiskIndex 테이블용 CSV 생성.

Phase 6(2026-08-04) 재작성: "실제값=현황, 예측값=조기경보 순위"로 역할을 완전히 분리했다.
직전 버전(Phase 5)은 예측폐업률(100-성장확률, label_h2 기준 +2분기 후 폐업 확률)을 그대로
화면 절대값·등급 산정에 썼는데, 실측 결과 예측값이 실제 관측 폐업률보다 평균 2.38배(중앙값
2.48배) 구조적으로 높게 나온다는 게 확인됨. 그래서 보정 대신 역할을 나눴다:
  - 지도·순위표(현황 진단) = 실제 폐업률 그대로, 화면에 절대 %로 노출. 보정 없음.
  - 조기경보(예측) = 예측값은 셀 순위 매기는 데만 쓰고 절대값은 화면에 노출하지 않음.
  - 성장확률은 위험도와 별개인 "성장성" 지표로 계속 분리 보존.

────────────────────────────────────────────────────────────────────────────
Phase 7(2026-08-20) — 단일 분기 지표를 4분기 누적으로 전환

문제. 지표를 "한 분기 스냅샷" 그대로 쓰고 있었고, 거기서 문제 네 개가 동시에 나왔다.

  1. 분기마다 우선순위가 거의 다 바뀜   순위 상관 +0.296 / Top10 유지 1.0개
  2. 등급 기준선이 분기마다 3배 요동    위험 기준 6.00% ~ 18.76%
  3. 소표본 셀이 상위권 점거           상위 8개가 전부 점포 54~84곳
  4. 데이터 결함 분기가 그대로 노출     2023Q1·2024Q4·2025Q1·2025Q3

원인이 하나다. 점포 60곳짜리 셀에서 폐업 1~2건 차이가 순위를 통째로 뒤집는다.

대응 세 가지.

  (가) 4분기 누적. 분기별 폐업 건수와 분모를 4분기 합산해서 비율을 낸다.
       검증: 순위 상관 +0.296 -> +0.857, Top10 유지 1.0 -> 5.4개.
       "느려지는 것 아니냐"는 우려는 실측으로 반박됐다 — 과거 1분기로 미래를 예측할 때
       상관 +0.319, 4분기 +0.345, 8분기 +0.501로 오히려 긴 창이 미래를 더 잘 맞힌다.
       급변은 대부분 평균으로 회귀한다(급등 셀 3.0% -> 9.7% -> 5.5%).

  (나) 신뢰하한(Wilson). 겉보기 10%라도 점포 50곳이면 4.35%, 1000곳이면 8.29%로
       자동 보정된다. 소표본이 우연히 높게 나와 상위를 점거하는 것을 막는다.
       정렬·순위에만 쓰고 등급 판정에는 쓰지 않는다(등급은 관측 사실이어야 방어된다).

  (다) 등급 기준선을 상위 분위수로. 기존 "시평균 x 2"는 4분기로 바꿔도 6.88~14.38%로
       흔들렸고, 고정 임계값(8.31%)은 위험 셀이 2~85개로 42배 요동했다.
       2025년 폐업 급증이 데이터 결함인지 판정 불가한 상태라, 고정 기준을 쓰면
       그 미확인 급증이 그대로 정책 판단으로 직결된다. 분위수 기준은 모든 셀이 같이
       움직이면 상대 위치가 보존되므로 그 오염에 면역이다(상권 유형 4분류가 중위값
       상대 기준을 쓰는 것과 같은 이유).
       채택: 위험 = 상위 10%, 주의 = 상위 30%. 위험 셀이 매 분기 22~26개로 안정된다.

주의. 등급이 상대 기준이므로 "위험"은 절대적 의미가 아니라 화성시 내 상대 순위다.
      화면에 이 점을 반드시 명시해야 한다.

컬럼 정책. 기존 컬럼은 의미를 바꾸지 않고 그대로 둔다(백엔드가 이미 쓰고 있다).
      단일 분기 값이 필요한 곳은 계속 실제폐업률_pct를 쓰고, 화면 표시와 등급은
      새로 추가한 누적폐업률_pct를 쓴다.

사용법:
    python ai/build_risk_index.py
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import linregress

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cumulative import (  # noqa: E402
    CAUTION_Q,
    DANGER_Q,
    WINDOW,
    add_cell_type,
    add_cumulative,
    compute_thresholds,
    grade as grade_cell,
)

# 표본부족 판정 기준 (점포수). 학습 필터(train_model.py CELL_MIN_STORES=30)와 별개다.
# 30 -> 50 상향(2026-08-18): 30 기준에서는 상위 10개 리프트가 1.14배로 무너졌다.
# 민감도 검증(최신분기 기준): 30->1.14배 / 40->2.07배 / 50->1.85배 / 60->1.79배 / 80->1.74배,
# 스피어만은 50에서 정점(+0.5293). 셀은 382->231개로 줄지만 점포 커버율은 74.8%->61.8%로 유지된다.
SAMPLE_MIN = 50

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
    parser.add_argument("--thresholds-output", default="data/processed/risk_thresholds.json", type=Path)
    args = parser.parse_args()

    print("데이터 로드 중...")
    df = pd.read_csv(args.dataset, encoding="utf-8-sig", low_memory=False)
    scores = pd.read_csv(args.scores, encoding="utf-8-sig")

    print(f"{WINDOW}분기 누적 지표 계산 중...")
    df = add_cumulative(df, WINDOW)

    latest = int(df["기준_년분기_코드"].max())

    # 트렌드 기울기 — 누적 지표의 최근 4분기 기울기.
    # 단일 분기 값으로 기울기를 내면 노이즈가 그대로 기울기가 된다.
    trend_quarters = sorted(df["기준_년분기_코드"].unique())[-WINDOW:]
    print("트렌드 기울기 계산 중...")
    slopes = (
        df[df["기준_년분기_코드"].isin(trend_quarters)]
        .groupby(["행정동명", "통합카테고리"])["누적폐업률_pct"]
        .apply(calc_slope)
        .reset_index()
        .rename(columns={"누적폐업률_pct": "트렌드_기울기"})
    )
    slope_std = slopes["트렌드_기울기"].std()
    slopes["이상탐지_플래그"] = slopes["트렌드_기울기"] > slope_std

    df_latest = df[df["기준_년분기_코드"] == latest][[
        "행정동명", "통합카테고리", "폐업_률_평균", "개업_율_평균", "업종_포화도", "점포수",
        "누적폐업률_pct", "누적폐업건수", "위험도_하한_pct", "개업_율_보정_ma4",
    ]].copy()

    df_latest = add_cell_type(df_latest, SAMPLE_MIN)

    # 등급 기준선 — 표본충분 셀 집합 안에서의 분위수. 하드코딩 금지.
    try:
        levels = compute_thresholds(df_latest, SAMPLE_MIN)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    danger_pct = levels["danger_pct"]
    caution_pct = levels["caution_pct"]
    avg_cum_pct = levels["avg_pct"]
    print(
        f"기준선({WINDOW}분기 누적, 표본충분 {levels['eligible_cells']}셀 분위수): "
        f"위험 상위{(1 - DANGER_Q) * 100:.0f}% >= {danger_pct}% / "
        f"주의 상위{(1 - CAUTION_Q) * 100:.0f}% >= {caution_pct}% / 평균 {avg_cum_pct}%"
    )

    merged = scores.merge(df_latest, on=["행정동명", "통합카테고리"], how="left")
    merged = merged.merge(slopes, on=["행정동명", "통합카테고리"], how="left")

    for column in ["폐업_률_평균", "개업_율_평균", "업종_포화도"]:
        merged[column] = merged[column].fillna(0)
    merged["점포수"] = merged["점포수"].fillna(0).astype(int)

    merged["실제폐업률_pct"] = (merged["폐업_률_평균"] * 100).round(2)  # 단일 분기(기존 의미 유지)
    merged["개업률_pct"] = (merged["개업_율_평균"] * 100).round(2)
    merged["누적개업률_pct"] = (merged["개업_율_보정_ma4"] * 100).round(2)
    merged["표본부족_플래그"] = merged["점포수"] < SAMPLE_MIN

    merged["위험등급"] = merged.apply(
        lambda r: grade_cell(
            r["누적폐업률_pct"], not r["표본부족_플래그"], danger_pct, caution_pct
        ),
        axis=1,
    )

    # 조기경보용 예측 순위 — 예측폐업률(100-성장확률)은 순위 산정에만 쓰고 API에는 노출하지 않는다.
    #
    # 정렬은 모델 단독이다. 앙상블(모델 순위 + 관측 신뢰하한 순위의 평균)을 계산해
    # `우선순위` 컬럼으로 내보내던 시절이 있었는데, 그 컬럼은 DB에도 API에도 들어가지
    # 않아 아무 데도 쓰이지 않았다. 주석만 "앙상블로 정렬한다"고 말하고 있었다.
    #
    # 2026-08-26에 저장된 모델과 cell_train_table로 다시 재봤다(ai/validate_ranking.py).
    # 과거 시점에서 순위를 매기고 그 뒤 4분기 실제 폐업률과 맞춘 결과 —
    #
    #     방식        스피어만   리프트(상위 10%)
    #     모델 단독     0.324       1.180
    #     관측 단독     0.268       1.142
    #     앙상블       0.318       1.208
    #
    # 지표에 따라 승자가 갈리고 차이가 0.006 / 0.028이다. 쓸 수 있는 기준 분기가 2개뿐이라
    # 이 정도는 측정 오차다. 예전 두 주석이 서로 다른 말을 한 것도 각자 유리한 지표를
    # 인용했기 때문이다.
    #
    # 성능으로 못 고르므로 화면 정체성으로 골랐다 — 조기경보는 "모델이 본 2분기 뒤"이고
    # 현장 확인은 "이미 관측된 최근 1년"이다. 두 화면을 그렇게 갈라놓고 안내까지 붙였는데
    # 조기경보 정렬에 관측을 섞으면 그 구분이 흐려진다. 앙상블 컬럼은 제거했다.
    merged["_예측폐업률_내부용"] = (100 - merged["성장확률"]).round(1)
    sample_ok = ~merged["표본부족_플래그"] & merged["위험도_하한_pct"].notna()

    merged["예측순위"] = pd.NA
    if sample_ok.any():
        subset = merged.loc[sample_ok]
        # method="first": 동률이어도 1..N 연속 정수로 매김(Top 10 카드에 "#5"가 두 번 뜨고
        # "#6"이 비는 문제 방지 — method="min"으로 처음 구현했다가 스크린샷 검증에서 발견)
        merged.loc[sample_ok, "예측순위"] = (
            subset["_예측폐업률_내부용"].rank(ascending=False, method="first").astype(int)
        )

    # 업종 내 순위 — 전체 순위만 두면 목록이 한 업종으로 덮인다.
    # 실측(2026-08-20): 위험 등급 24개 중 18개(75%)가 교육 계열이었다. 데이터 결함이 아니라
    # 실제 현상이다(교육은 점포의 14.9%인데 폐업의 28.8%를 차지하고, 인허가 매칭률도 90.2%로
    # 다른 업종 80.3%보다 오히려 높아 교차검증이 잘 된다).
    # 등급은 사실대로 두되, 담당자가 "한식 중에서는 어디가 제일 위험한가"도 볼 수 있게
    # 업종 내 상대 순위를 병기한다.
    merged["업종내_누적순위"] = pd.NA
    merged["업종내_표본충분셀수"] = pd.NA
    ranked = merged.loc[sample_ok]
    if len(ranked):
        merged.loc[sample_ok, "업종내_누적순위"] = (
            ranked.groupby("통합카테고리")["누적폐업률_pct"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
        merged.loc[sample_ok, "업종내_표본충분셀수"] = (
            ranked.groupby("통합카테고리")["누적폐업률_pct"].transform("size").astype(int)
        )

    # 읍면동별 "위험 업종 비율" = 위험 등급 셀 수 / 표본충분 셀 수 (choropleth용)
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

    # 위험업종비율(0~33% 대)은 셀 단위 폐업률과 스케일이 다른 별도 지표이므로 기준선도 따로 낸다.
    dong_ratio_avg = round(float(dong_risk_ratio["위험업종비율"].mean()), 2)
    dong_ratio_danger = round(float(dong_risk_ratio["위험업종비율"].quantile(DANGER_Q)), 2)
    print(
        f"기준선(동단위 위험업종비율): 평균 {dong_ratio_avg}% / "
        f"위험 상위{(1 - DANGER_Q) * 100:.0f}% >= {dong_ratio_danger}%"
    )

    out = merged[[
        "행정동명", "통합카테고리", "기준_년분기_코드",
        "실제폐업률_pct", "누적폐업률_pct", "누적폐업건수", "위험도_하한_pct",
        "위험등급", "표본부족_플래그", "위험업종비율",
        "예측순위", "업종내_누적순위", "업종내_표본충분셀수",
        "상권유형", "유형_개업기준", "유형_폐업기준", "성장확률", "점포수",
        "개업률_pct", "누적개업률_pct", "업종_포화도",
        "트렌드_기울기", "이상탐지_플래그",
        "_예측폐업률_내부용",
    ]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {args.output} ({len(out):,}행)")

    grade_counts = out["위험등급"].value_counts().to_dict()
    print(f"등급 분포: {grade_counts}")
    judged = out[out["상권유형"] != "유형판정보류"]
    if len(judged):
        print(f"상권 유형 분포: {judged['상권유형'].value_counts().to_dict()}")

    danger = out[out["위험등급"] == "위험"]
    if len(danger):
        top_industry = danger["통합카테고리"].value_counts()
        share = top_industry.iloc[0] / len(danger) * 100
        print(
            f"위험 셀 업종 편중: 최다 '{top_industry.index[0]}' "
            f"{top_industry.iloc[0]}/{len(danger)}개 ({share:.0f}%)"
        )

    thresholds = {
        # 기존 키 — 백엔드·임포터가 이미 참조하므로 이름을 바꾸지 않는다.
        # 의미만 "단일 분기 시평균 x 2"에서 "4분기 누적 분위수"로 바뀌었다.
        "avg_closure_rate_pct": avg_cum_pct,
        "danger_threshold_pct": danger_pct,
        "dong_ratio_avg_pct": dong_ratio_avg,
        "dong_ratio_danger_pct": dong_ratio_danger,
        "sample_min": SAMPLE_MIN,
        "quarter": latest,
        # 신규 키
        "caution_threshold_pct": caution_pct,
        "window_quarters": WINDOW,
        "method": "cumulative_quantile",
        "danger_quantile": DANGER_Q,
        "caution_quantile": CAUTION_Q,
        "eligible_cells": levels["eligible_cells"],
        "cell_type_open_cut_pct": float(df_latest["유형_개업기준"].dropna().iloc[0])
        if df_latest["유형_개업기준"].notna().any() else None,
        "cell_type_close_cut_pct": float(df_latest["유형_폐업기준"].dropna().iloc[0])
        if df_latest["유형_폐업기준"].notna().any() else None,
    }
    args.thresholds_output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.thresholds_output, "w", encoding="utf-8") as f:
        json.dump(thresholds, f, ensure_ascii=False, indent=2)
    print(f"임계값 저장 완료: {args.thresholds_output}")


if __name__ == "__main__":
    main()
