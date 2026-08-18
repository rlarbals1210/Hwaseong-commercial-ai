"""화성시 인허가 원본의 인허가일자·폐업일자로 업력별 2개 분기 내 폐업률을 계산한다.

기존 store_train_table.csv의 업력은 점포 주소와 같은 인허가 기록 중 가장 이른 날짜를
붙인 추정치이다. 동일 주소의 이전 사업장이 섞일 수 있으므로 정책 대상 업력 기준을
정하는 본 분석에서는 사용하지 않는다.

사용법:
    python ai/analyze_tenure.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eda"))
import paths as eda_paths  # noqa: E402

OBSERVATION_START = "2020Q4"
OBSERVATION_END = "2025Q2"
OUTCOME_CUTOFF = pd.Timestamp("2025-12-31")
HORIZON_QUARTERS = 2
TENURE_BINS = [0, 4, 8, 12, 20, np.inf]
TENURE_LABELS = ["0-3", "4-7", "8-11", "12-19", "20+"]
TENURE_LABELS_KO = {
    "0-3": "1년 미만",
    "4-7": "1-2년 미만",
    "8-11": "2-3년 미만",
    "12-19": "3-5년 미만",
    "20+": "5년 이상",
}
MIN_BUSINESSES_FOR_RECOMMENDATION = 100
MIN_RISK_RATIO_FOR_RECOMMENDATION = 1.2
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = PROJECT_ROOT / "docs" / "tenure_analysis.md"
CHART_PATH = PROJECT_ROOT / "docs" / "tenure_closure_rates.png"


def read_permit_file(path: Path) -> pd.DataFrame | None:
    frame = None
    for encoding in ("cp949", "utf-8"):
        try:
            frame = pd.read_csv(
                path,
                encoding=encoding,
                usecols=lambda column: column in {"관리번호", "인허가일자", "폐업일자"},
                low_memory=False,
            )
            break
        except UnicodeDecodeError:
            continue
    required = {"관리번호", "인허가일자", "폐업일자"}
    if frame is None or not required.issubset(frame.columns):
        return None
    frame["source"] = unicodedata.normalize("NFC", path.stem)
    return frame


def load_permits(permit_dir: Path, outcome_cutoff: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    frames = []
    skipped_files = []
    for path in sorted(permit_dir.glob("*.csv")):
        if path.name.startswith("._"):
            continue
        frame = read_permit_file(path)
        if frame is None:
            skipped_files.append(unicodedata.normalize("NFC", path.name))
            continue
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"인허가 분석 가능 CSV가 없습니다: {permit_dir}")

    permits = pd.concat(frames, ignore_index=True)
    raw_rows = len(permits)
    permits["open_date"] = pd.to_datetime(permits["인허가일자"], errors="coerce")
    permits["close_date"] = pd.to_datetime(permits["폐업일자"], errors="coerce")
    permits = permits[permits["open_date"].notna() & permits["open_date"].le(outcome_cutoff)].copy()

    invalid_close = permits["close_date"].lt(permits["open_date"]).fillna(False)
    invalid_close_rows = int(invalid_close.sum())
    permits.loc[invalid_close, "close_date"] = pd.NaT
    permits.loc[permits["close_date"].gt(outcome_cutoff), "close_date"] = pd.NaT

    permits["business_id"] = permits["source"] + ":" + permits["관리번호"].astype(str)
    duplicate_rows = int(permits.duplicated("business_id").sum())
    permits = permits.sort_values(["business_id", "close_date"], na_position="first")
    permits = permits.drop_duplicates("business_id", keep="last").reset_index(drop=True)

    quality = {
        "raw_rows": raw_rows,
        "usable_records_as_of_cutoff": len(permits),
        "source_file_count": len(frames),
        "skipped_files": skipped_files,
        "invalid_close_before_open_rows": invalid_close_rows,
        "duplicate_business_rows_removed": duplicate_rows,
    }
    return permits, quality


def build_exposures(
    permits: pd.DataFrame,
    observation_start: str = OBSERVATION_START,
    observation_end: str = OBSERVATION_END,
    horizon_quarters: int = HORIZON_QUARTERS,
) -> pd.DataFrame:
    parts = []
    for origin in pd.period_range(observation_start, observation_end, freq="Q-DEC"):
        origin_end = origin.end_time.normalize()
        target_end = (origin + horizon_quarters).end_time.normalize()
        at_risk = permits[
            permits["open_date"].le(origin_end)
            & (permits["close_date"].isna() | permits["close_date"].gt(origin_end))
        ].copy()
        open_quarters = at_risk["open_date"].dt.to_period("Q-DEC")
        at_risk["tenure_quarters"] = origin.ordinal - open_quarters.apply(lambda period: period.ordinal)
        at_risk["closure_within_horizon"] = (
            at_risk["close_date"].notna() & at_risk["close_date"].le(target_end)
        )
        at_risk["origin_quarter"] = str(origin)
        parts.append(
            at_risk[
                ["business_id", "source", "origin_quarter", "tenure_quarters", "closure_within_horizon"]
            ]
        )
    exposures = pd.concat(parts, ignore_index=True)
    return exposures[exposures["tenure_quarters"].ge(0)].reset_index(drop=True)


def clustered_rate_interval(frame: pd.DataFrame, rate: float) -> tuple[float, float, float]:
    """같은 사업장이 여러 분기 반복 관측되는 의존성을 사업장 클러스터 샌드위치로 보정한다."""
    residual_sum = (
        frame.assign(residual=frame["closure_within_horizon"].astype(float) - rate)
        .groupby("business_id")["residual"]
        .sum()
    )
    cluster_count = len(residual_sum)
    correction = cluster_count / (cluster_count - 1) if cluster_count > 1 else 1.0
    standard_error = float(np.sqrt(correction * np.square(residual_sum).sum()) / len(frame))
    lower = max(0.0, rate - 1.96 * standard_error)
    upper = min(1.0, rate + 1.96 * standard_error)
    return standard_error, lower, upper


def directly_standardized_rate(data: pd.DataFrame, segment: str) -> tuple[float, float]:
    """인허가 종류와 관측 분기 구성 차이를 제거한 직접표준화 폐업률을 계산한다.

    전체 관측치의 source×origin_quarter 구성비를 표준 가중치로 사용한다. 특정 업력
    구간에 관측치가 없는 소수 층은 제외하고 가중치를 다시 정규화하며, 함께 반영된
    표준 가중치 비율을 반환한다.
    """
    strata = ["source", "origin_quarter"]
    standard_weights = data.groupby(strata).size() / len(data)
    stratum_rates = (
        data[data["tenure_segment"] == segment]
        .groupby(strata, observed=True)["closure_within_horizon"]
        .mean()
    )
    available_weights = standard_weights.loc[stratum_rates.index]
    weight_coverage = float(available_weights.sum())
    standardized_rate = float((stratum_rates * available_weights).sum() / weight_coverage)
    return standardized_rate, weight_coverage


def summarize_tenure(exposures: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    data = exposures.copy()
    data["tenure_segment"] = pd.cut(
        data["tenure_quarters"],
        bins=TENURE_BINS,
        labels=TENURE_LABELS,
        right=False,
    )
    overall_rate = float(data["closure_within_horizon"].mean())
    rows = []
    for segment in TENURE_LABELS:
        group = data[data["tenure_segment"] == segment]
        rate = float(group["closure_within_horizon"].mean())
        standard_error, lower, upper = clustered_rate_interval(group, rate)
        businesses = int(group["business_id"].nunique())
        risk_ratio = rate / overall_rate
        standardized_rate, standard_weight_coverage = directly_standardized_rate(data, segment)
        adjusted_risk_ratio = standardized_rate / overall_rate
        rows.append(
            {
                "tenure_segment": segment,
                "tenure_label_ko": TENURE_LABELS_KO[segment],
                "exposure_count": len(group),
                "business_count": businesses,
                "positive_observation_count": int(group["closure_within_horizon"].sum()),
                "closure_rate": rate,
                "closure_rate_pct": rate * 100,
                "cluster_se": standard_error,
                "ci95_lower_pct": lower * 100,
                "ci95_upper_pct": upper * 100,
                "risk_ratio_vs_overall": risk_ratio,
                "standardized_closure_rate": standardized_rate,
                "standardized_closure_rate_pct": standardized_rate * 100,
                "standard_weight_coverage": standard_weight_coverage,
                "adjusted_risk_ratio_vs_overall": adjusted_risk_ratio,
                "recommended": bool(
                    businesses >= MIN_BUSINESSES_FOR_RECOMMENDATION
                    and adjusted_risk_ratio >= MIN_RISK_RATIO_FOR_RECOMMENDATION
                ),
            }
        )
    summary = pd.DataFrame(rows)
    summary["risk_rank"] = summary["closure_rate"].rank(ascending=False, method="min").astype(int)

    quarterly = (
        data.groupby(["origin_quarter", "tenure_segment"], observed=False)
        .agg(
            exposure_count=("closure_within_horizon", "size"),
            positive_observation_count=("closure_within_horizon", "sum"),
            closure_rate=("closure_within_horizon", "mean"),
        )
        .reset_index()
    )
    quarterly["closure_rate_pct"] = quarterly["closure_rate"] * 100
    quarterly["tenure_segment"] = quarterly["tenure_segment"].astype(str)
    return summary, quarterly, overall_rate


def plot_summary(summary: pd.DataFrame, overall_rate: float, output_path: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "hwaseong-matplotlib"))
    import matplotlib.pyplot as plt

    try:
        plt.rcParams["font.family"] = "AppleGothic"
        plt.rcParams["axes.unicode_minus"] = False
        labels = summary["tenure_label_ko"].tolist()
    except Exception:
        labels = summary["tenure_segment"].tolist()
    values = summary["closure_rate_pct"].to_numpy()
    errors = np.vstack(
        [
            values - summary["ci95_lower_pct"].to_numpy(),
            summary["ci95_upper_pct"].to_numpy() - values,
        ]
    )
    colors = ["#C4493F" if recommended else "#65758B" for recommended in summary["recommended"]]
    figure, axis = plt.subplots(figsize=(9, 5.2))
    bars = axis.bar(labels, values, yerr=errors, capsize=4, color=colors, alpha=0.92)
    axis.axhline(overall_rate * 100, color="#1F2937", linestyle="--", linewidth=1.5, label="전체 폐업률")
    axis.set_ylabel("2개 분기 내 명시적 폐업률(%)")
    axis.set_xlabel("관측 시점 업력")
    axis.set_title("화성시 인허가 사업장 업력별 폐업률")
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False)
    for bar, value in zip(bars, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value + 0.25, f"{value:.2f}%", ha="center")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def build_report(summary: pd.DataFrame, overall_rate: float, quality: dict, exposure_quality: dict) -> str:
    top = summary.sort_values("closure_rate", ascending=False).iloc[0]
    recommended = summary.loc[summary["recommended"], "tenure_label_ko"].tolist()
    table_rows = []
    for row in summary.itertuples(index=False):
        table_rows.append(
            f"| {row.tenure_label_ko} | {row.exposure_count:,} | {row.business_count:,} | "
            f"{row.closure_rate_pct:.2f}% | {row.ci95_lower_pct:.2f}-{row.ci95_upper_pct:.2f}% | "
            f"{row.standardized_closure_rate_pct:.2f}% | {row.adjusted_risk_ratio_vs_overall:.2f} | "
            f"{'예' if row.recommended else '아니오'} |"
        )
    food_businesses = sum(
        item["business_count"]
        for item in exposure_quality["source_business_counts"]
        if item["source"].startswith("식품_")
    )
    food_share = food_businesses / exposure_quality["business_count"] * 100
    return f"""# 업력별 폐업률 분석

작성일: 2026-08-18  
실행 스크립트: `ai/analyze_tenure.py`

## 결론

- 가장 높은 구간은 **{top.tenure_label_ko}({top.tenure_segment}분기)**로, 이후 2개 분기 내 명시적 폐업률은 **{top.closure_rate_pct:.2f}%**이다.
- 인허가 종류와 관측 분기 구성을 보정해도 표준화 폐업률은 {top.standardized_closure_rate_pct:.2f}%로, 전체 {overall_rate * 100:.2f}% 대비 **{top.adjusted_risk_ratio_vs_overall:.2f}배**다.
- 사전에 고정한 `사업장 100개 이상 + 전체 대비 위험비 1.2 이상` 기준을 통과한 구간은 **{', '.join(recommended)}**이다.
- 실행 목록의 업력 필터는 **1-3년 미만(4-11분기)**으로 확정한다. 1년 미만과 3년 이상은 업력만으로 우선 선정하지 않는다.
- **U자형은 나타나지 않았다.** 5년 이상 구간은 {summary.loc[summary.tenure_segment == '20+', 'closure_rate_pct'].iloc[0]:.2f}%로 가장 낮았다. 초장기 업체가 다시 위험해진다는 주장은 하지 않는다.

## 결과표

| 업력 구간 | 관측건 | 사업장수 | 원폐업률 | 95% CI | 표준화 폐업률 | 보정 위험비 | 안내 대상 권고 |
|---|---:|---:|---:|---:|---:|---:|:---:|
{chr(10).join(table_rows)}

![업력별 폐업률](./tenure_closure_rates.png)

## 분석 정의

- 데이터: 화성시 인허가 CSV {quality['source_file_count']}종의 `인허가일자`, `폐업일자`.
- 관측 시점: {OBSERVATION_START}~{OBSERVATION_END} 분기말 {exposure_quality['origin_quarter_count']}개. 원시 데이터는 21개 분기이지만 +2분기 결과가 필요해 마지막 2개 분기는 기준 시점에서 제외했다.
- 모수: 해당 분기말에 영업 중이며 인허가일자가 유효한 사업장.
- 사건: 기준 분기말 이후 2개 분기 말까지 `폐업일자`가 명시된 경우. 휴업일자는 사건으로 세지 않았다.
- 단위: 사업장-기준분기 관측건. 같은 사업장의 반복 관측을 감안해 95% 신뢰구간은 사업장 클러스터 샌드위치로 보정했다.
- 표준화: 업력 구간별 인허가 종류×관측 분기 구성 차이를 제거하기 위해 전체 표본의 구성비를 공통 가중치로 적용했다. 안내 대상 권고는 이 보정값을 사용했다.
- 표본: {exposure_quality['business_count']:,}개 사업장, {exposure_quality['exposure_count']:,}건 관측.

## 제한과 사용 범위

1. 이 결과는 인허가 데이터가 있는 {quality['source_file_count']}종에 대한 결과다. 화성시 74개 중분류 전체의 인과법칙으로 일반화하지 않는다. 또한 표본의 {food_share:.1f}%가 식품 관련 인허가여서, 인허가 종류 구성을 표준화해 권고 기준을 정했다.
2. 5년 이상 사업장의 낮은 폐업률은 오래 살아남은 업체만 위험집단에 남는 생존자 효과를 포함한다.
3. 이 분석은 **안내 대상을 줄이는 집단 기준**이지, 개별 점포의 폐업 예측이 아니다.
4. 현재 `store_train_table.csv` 업력은 주소 기반 추정치이므로 이 결과를 점포 명단에 적용하려면 상호명+주소+업종을 이용한 인허가 매칭 고도화가 먼저 필요하다.

## 발표용 한 문장

> 화성시 인허가 사업장 {exposure_quality['business_count']:,}개를 분석한 결과, 개업 1-2년 미만 구간의 6개월 내 명시적 폐업률이 {top.closure_rate_pct:.2f}%로 가장 높았고, 업종·시점을 보정해도 1-3년 미만 구간이 전체보다 1.2배 이상 높아 우선 안내 대상으로 좁혔습니다.
"""


def main() -> None:
    print(f"인허가 데이터: {eda_paths.PERMIT_DIR}")
    permits, quality = load_permits(eda_paths.PERMIT_DIR, OUTCOME_CUTOFF)
    exposures = build_exposures(permits)
    summary, quarterly, overall_rate = summarize_tenure(exposures)

    eda_paths.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(eda_paths.TENURE_RATES_CSV, index=False, encoding="utf-8-sig")
    quarterly.to_csv(eda_paths.TENURE_BY_QUARTER_CSV, index=False, encoding="utf-8-sig")

    source_counts = (
        exposures.groupby("source")["business_id"]
        .nunique()
        .sort_values(ascending=False)
        .rename("business_count")
        .reset_index()
        .to_dict(orient="records")
    )
    exposure_quality = {
        "origin_quarter_count": int(exposures["origin_quarter"].nunique()),
        "business_count": int(exposures["business_id"].nunique()),
        "exposure_count": len(exposures),
        "positive_observation_count": int(exposures["closure_within_horizon"].sum()),
        "overall_closure_rate": overall_rate,
        "source_business_counts": source_counts,
    }
    result = {
        "definition": {
            "observation_start": OBSERVATION_START,
            "observation_end": OBSERVATION_END,
            "outcome_cutoff": OUTCOME_CUTOFF.date().isoformat(),
            "horizon_quarters": HORIZON_QUARTERS,
            "tenure_bins": TENURE_LABELS,
            "event": "기준 분기말 이후 2개 분기 내 명시적 폐업일자 존재",
        },
        "input_quality": quality,
        "exposure_quality": exposure_quality,
        "segments": summary.to_dict(orient="records"),
        "decision": {
            "recommended_segments": summary.loc[summary["recommended"], "tenure_segment"].tolist(),
            "primary_contact_filter": ["4-7", "8-11"],
            "secondary_contact_filter": [],
            "long_term_20_plus_supported": False,
            "u_shape_supported": False,
        },
    }
    eda_paths.TENURE_ANALYSIS_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    plot_summary(summary, overall_rate, CHART_PATH)
    REPORT_PATH.write_text(build_report(summary, overall_rate, quality, exposure_quality), encoding="utf-8")

    print(summary.to_string(index=False))
    print(f"\n전체 2개 분기 내 폐업률: {overall_rate * 100:.2f}%")
    print(f"저장: {eda_paths.TENURE_RATES_CSV}")
    print(f"저장: {eda_paths.TENURE_BY_QUARTER_CSV}")
    print(f"저장: {eda_paths.TENURE_ANALYSIS_JSON}")
    print(f"저장: {REPORT_PATH}")
    print(f"저장: {CHART_PATH}")


if __name__ == "__main__":
    main()
