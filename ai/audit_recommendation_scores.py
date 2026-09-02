"""수정된 과거 자료의 추천 산식 부분 비교. 운영 모델/데이터는 갱신하지 않는다.

사전 계획: docs/recommendation-score-audit-plan.md
실행: python -m ai.audit_recommendation_scores
출력은 집계 JSON뿐이며, 예측 절대값이나 셀별 원본을 기록하지 않는다.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ai.cumulative import compute_thresholds
from backend.services.recommend import (
    AXES, GROWTH_SPREAD_MIN, SAMPLE_MIN, WEIGHT_PRESETS, Candidate, score_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
KEY = ["area", "industry"]
ORIGINS = (20243, 20244)
VARIANTS = ("baseline", "narrow_spread", "no_saturation", "separate_observed_risk")
WEIGHTS = WEIGHT_PRESETS["균형"]["weights"]
TOP_N = 3
MIN_AREAS = 5
BOOTSTRAPS = 1000
SEED = 42


def validation_end() -> str:
    """학습 코드를 실행/import하지 않고 실제 설정의 리터럴을 읽는다."""
    source = ast.parse((ROOT / "ai" / "train_model.py").read_text(encoding="utf-8"))
    for node in source.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VALID_END" for t in node.targets):
            return str(ast.literal_eval(node.value))
    raise ValueError("학습 코드의 검증 종료 시점을 확인할 수 없습니다")


def quarter_code(label: str) -> int:
    year, quarter = str(label).split("Q")
    if not 1 <= int(quarter) <= 4:
        raise ValueError("분기는 1~4여야 합니다")
    return int(year) * 10 + int(quarter)


def quarter_add(code: int, count: int) -> int:
    year, quarter = divmod(int(code), 10)
    if not 1 <= quarter <= 4:
        raise ValueError("유효하지 않은 분기 코드")
    offset = year * 4 + quarter - 1 + count
    return (offset // 4) * 10 + offset % 4 + 1


def observed_window(commercial: pd.DataFrame, end: int) -> pd.DataFrame:
    """정확히 연속된 4분기의 건수합/직전분기 점포수합. 결측은 미확정이다."""
    work = commercial.copy()
    keys = KEY + ["quarter"]
    if work.duplicated(keys).any():
        raise ValueError("관측 자료의 셀·분기 키가 중복됩니다")
    previous = work[keys + ["stores"]].rename(columns={"stores": "denominator"})
    previous["quarter"] = previous["quarter"].map(lambda q: quarter_add(q, 1))
    work = work.merge(previous, on=keys, how="left", validate="one_to_one")
    quarters = [quarter_add(end, i) for i in range(-3, 1)]
    work = work[work["quarter"].isin(quarters)].copy()
    valid = (work["denominator"] > 0) & work["observed_rate"].between(0, 1)
    work["closures"] = (work["observed_rate"] * work["denominator"]).where(valid)
    work["denominator"] = work["denominator"].where(valid)
    result = work.groupby(KEY).agg(
        quarters=("quarter", "nunique"), valid_quarters=("closures", "count"),
        closures=("closures", "sum"), denominator=("denominator", "sum"),
    )
    complete = (result["quarters"] == 4) & (result["valid_quarters"] == 4)
    result["rate"] = (result["closures"] / result["denominator"] * 100).where(complete)
    result.loc[~complete, ["closures", "denominator"]] = np.nan
    return result


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """미래 결과 없이 같은 업종의 시 전체를 기준으로 운영 점수를 재사용한다."""
    if SAMPLE_MIN != 30:
        raise ValueError("계획의 표본 기준 30이 변경됐습니다. 재계획이 필요합니다")
    work = frame.copy()
    work["raw_saturation"] = work["saturation"]
    for axis in AXES:
        work[axis] = np.nan
    work["baseline"] = np.nan
    work["spread_narrow"] = False
    work["spread_factor"] = 1.0
    for _, group in work.groupby("industry", sort=True):
        candidates = [Candidate(
            area_id=i, area_name=row.area, industry_id=1, industry_name=row.industry,
            growth_prob=row.model_safety, store_count=int(row.stores),
            saturation=row.raw_saturation, closure_rate_cum4_pct=None,
            closure_count_cum4=None, opening_rate_pct=None, tenure_quarters=None,
            cell_type=None, demand_gap=None,
        ) for i, row in enumerate(group.itertuples())]
        meta = score_candidates(candidates, "균형")
        for index, candidate in zip(group.index, candidates):
            work.loc[index, "baseline"] = candidate.score
            for axis in AXES:
                work.loc[index, axis] = candidate.axis_scores[axis]
        # 실제 연산 폭을 사용한다. meta의 표시용 소수 첫째 자리 반올림은 사용하지 않는다.
        reference = group[group["stores"] >= SAMPLE_MIN]
        if reference.empty:
            reference = group
        spread = float(reference["model_safety"].max() - reference["model_safety"].min())
        work.loc[group.index, "spread_factor"] = min(1.0, spread / GROWTH_SPREAD_MIN)
        work.loc[group.index, "spread_narrow"] = meta["growth_spread_narrow"]
    return apply_variants(work)


def apply_variants(work: pd.DataFrame) -> pd.DataFrame:
    work = work.copy()
    # 후보는 충분표본만 평가한다. 소표본 점수는 본래의 축 보정이 이미 적용돼 있다.
    softened = 50 + work["spread_factor"] * (work["growth"] - 50)
    work["narrow_spread"] = [round(value, 1) for value in (
        softened * WEIGHTS["growth"]
        + work["demand"] * WEIGHTS["demand"]
        + work["competition"] * WEIGHTS["competition"]
        + work["saturation"] * WEIGHTS["saturation"]
    )]
    work["no_saturation"] = [round(value, 1) for value in (
        work["growth"] * WEIGHTS["growth"]
        + work["demand"] * WEIGHTS["demand"]
        + work["competition"] * WEIGHTS["competition"]
        + 50 * WEIGHTS["saturation"]
    )]
    work["separate_observed_risk"] = work["baseline"]
    return work


def select_top(frame: pd.DataFrame, variant: str) -> pd.DataFrame:
    candidates = frame[~frame["observed_danger"]] if variant == "separate_observed_risk" else frame
    return (candidates.sort_values(["industry", variant, "area"], ascending=[True, False, True])
            .groupby("industry", sort=True).head(TOP_N))


def correlation(x, y) -> float:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 3 or len(np.unique(x[valid])) < 2 or len(np.unique(y[valid])) < 2:
        return math.nan
    return float(spearmanr(x[valid], y[valid]).statistic)


def paired_interval(deltas: np.ndarray) -> dict:
    deltas = np.asarray(deltas, dtype=float)
    deltas = deltas[np.isfinite(deltas)]
    if len(deltas) == 0:
        return {"industries": 0, "delta_pp": None, "descriptive_ci95": None}
    samples = np.random.default_rng(SEED).choice(deltas, size=(BOOTSTRAPS, len(deltas)), replace=True)
    return {
        "industries": len(deltas), "delta_pp": float(deltas.mean()),
        "descriptive_ci95": np.quantile(samples.mean(axis=1), [0.025, 0.975]).tolist(),
    }


def evaluate(frame: pd.DataFrame) -> tuple[dict, dict[str, pd.DataFrame]]:
    results, selections, industry_rates = {}, {}, {}
    all_rates = frame.groupby("industry")["future_rate"].mean()
    for variant in VARIANTS:
        top = select_top(frame, variant)
        selections[variant] = top
        by_industry = top.groupby("industry")["future_rate"].mean()
        industry_rates[variant] = by_industry
        measured = top.dropna(subset=["future_rate"])
        rhos = [correlation(g[variant], -g["future_rate"]) for _, g in frame.groupby("industry")]
        finite_rhos = [v for v in rhos if np.isfinite(v)]
        base_keys = set(zip(selections["baseline"].area, selections["baseline"].industry))
        top_keys = set(zip(top.area, top.industry))
        eligible = frame[~frame.observed_danger] if variant == "separate_observed_risk" else frame
        results[variant] = {
            "eligible_cells": len(eligible), "eligible_areas": eligible.area.nunique(),
            "eligible_stores": int(eligible.stores.sum()),
            "eligible_industries": eligible.industry.nunique(),
            "selected_cells": len(top), "selected_areas": top.area.nunique(),
            "full_top3_industries": int((top.groupby("industry").size() == TOP_N).sum()),
            "future_missing_selected": int(top.future_rate.isna().sum()),
            "macro_future_rate_pct": float(by_industry.mean()),
            "macro_ratio_to_same_industry": float((by_industry / all_rates.replace(0, np.nan)).mean()),
            "pooled_future_rate_pct": float(measured.future_closures.sum() / measured.future_denominator.sum() * 100),
            "macro_spearman_safety": float(np.mean(finite_rhos)) if finite_rhos else math.nan,
            "spearman_industries": len(finite_rhos),
            "overlap_with_baseline_pct": len(base_keys & top_keys) / len(base_keys) * 100,
            "observed_danger_selected": int(top.observed_danger.sum()),
        }
    for variant in VARIANTS[1:]:
        joined = pd.concat([industry_rates[variant], industry_rates["baseline"]], axis=1).dropna()
        results[variant]["paired_change"] = paired_interval((joined.iloc[:, 0] - joined.iloc[:, 1]).to_numpy())
    return results, selections


def compare_origins(frames: dict[int, pd.DataFrame]) -> dict:
    early, late = (frames[q] for q in ORIGINS)
    common = early.merge(late, on=KEY, suffixes=("_early", "_late"), validate="one_to_one")
    result = {}
    for variant in VARIANTS:
        rhos = [correlation(g[f"{variant}_early"], g[f"{variant}_late"])
                for _, g in common.groupby("industry") if len(g) >= MIN_AREAS]
        rhos = [r for r in rhos if np.isfinite(r)]
        a, b = select_top(early, variant), select_top(late, variant)
        ka, kb = set(zip(a.area, a.industry)), set(zip(b.area, b.industry))
        result[variant] = {
            "common_cells": len(common), "spearman_industries": len(rhos),
            "macro_score_spearman": float(np.mean(rhos)) if rhos else math.nan,
            "top3_retention_pct": len(ka & kb) / len(ka) * 100,
        }
    return result


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    commercial = pd.read_csv(DATA / "final_dataset.csv").rename(columns={
        "행정동명": "area", "통합카테고리": "industry",
        "기준_년분기_코드": "quarter", "점포수": "stores",
        "폐업_률_평균": "observed_rate", "업종_포화도": "saturation",
    })
    cells = pd.read_csv(DATA / "cell_train_table.csv")
    cells["quarter"] = cells["기준분기"].map(quarter_code)
    bundle = joblib.load(DATA / "lgbm_model_cell.pkl")
    for col in ["행정동명", "상권업종중분류명"]:
        cells[col] = cells[col].astype("category")
    selected = cells[cells.quarter.isin(ORIGINS)].copy()
    # 운영 저장 경로와 동일한 클리핑/소수 1자리 양자화. 절대값은 메모리에서만 사용한다.
    selected["model_safety"] = ((1 - bundle["model"].predict(selected[bundle["features"]])) * 100).clip(0, 100).round(1)
    selected = selected.rename(columns={"행정동명": "area", "상권업종중분류명": "industry"})
    for key in KEY:
        selected[key] = selected[key].astype(str)
    label_availability = cells.groupby("quarter")["폐업률"].agg(["size", "count"])
    return commercial, selected[KEY + ["quarter", "model_safety"]], label_availability.to_dict("index")


def latest_case(commercial: pd.DataFrame) -> dict:
    """현재 저장된 공개용 점수 입력에서 질문 사례를 재현한다. 미래 성능 시험이 아니다."""
    from backend.services.recommend import load_demand_scores

    latest = int(commercial.quarter.max())
    scores = pd.read_csv(DATA / "scores.csv").rename(columns={
        "행정동명": "area", "통합카테고리": "industry", "기준_년분기_코드": "quarter",
    })
    work = commercial[commercial.quarter == latest].merge(scores, on=KEY + ["quarter"], validate="one_to_one")
    work = work[work.industry == "일반 교육"]
    demand = load_demand_scores()
    candidates = [Candidate(
        i, row.area, 1, row.industry, row.성장확률, int(row.stores), row.saturation,
        None, None, None, None, None,
        demand_gap=demand.get((row.area, row.industry), {}).get("gap"),
    ) for i, row in enumerate(work.itertuples())]
    score_candidates(candidates, "균형")
    target = next(c for c in candidates if c.area_name == "남양읍")
    past = observed_window(commercial, latest)
    current = commercial[commercial.quarter == latest].set_index(KEY).join(past[["rate"]].round(2))
    thresholds = compute_thresholds(current.rename(columns={"stores": "점포수", "rate": "누적폐업률_pct"}), SAMPLE_MIN)
    rate = float(past.loc[("남양읍", "일반 교육"), "rate"])
    return {
        "source": "local published-score inputs, not a live DB query", "quarter": latest,
        "case": "남양읍·일반 교육", "score": target.score, "axes": target.axis_scores,
        "stores": target.store_count, "observed_rate_pct": rate,
        "danger_threshold_pct": thresholds["danger_pct"], "observed_danger": rate >= thresholds["danger_pct"],
    }


def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), 6) if np.isfinite(value) else None
    return value


def main() -> None:
    demand = pd.read_csv(DATA / "demand_features_historical.csv", usecols=["기준_년분기_코드"])
    demand_quarters = sorted(demand.iloc[:, 0].unique().tolist())
    if set(ORIGINS) & set(demand_quarters):
        raise ValueError("수요 자료 범위가 바뀌었습니다. 부분 비교 계획을 먼저 갱신하세요")
    commercial, predictions, label_availability = load_inputs()
    maturity = quarter_add(quarter_code(validation_end()), 2)
    frames, origins = {}, {}
    for origin in ORIGINS:
        current = commercial[commercial.quarter == origin].merge(predictions, on=KEY + ["quarter"], validate="one_to_one")
        scored = score_frame(current)
        past = observed_window(commercial, origin)[["rate"]].rename(columns={"rate": "past_rate"})
        scored = scored.join(past, on=KEY)
        available = scored[(scored.stores >= SAMPLE_MIN) & scored.past_rate.notna()].copy()
        threshold_input = commercial[commercial.quarter == origin].join(past.round(2), on=KEY)
        thresholds = compute_thresholds(threshold_input.rename(columns={"stores": "점포수", "past_rate": "누적폐업률_pct"}), SAMPLE_MIN)
        scored["observed_danger"] = scored.past_rate.round(2) >= thresholds["danger_pct"]
        sizes = available.groupby("industry").size()
        frame = scored[(scored.stores >= SAMPLE_MIN) & scored.past_rate.notna() & scored.industry.isin(sizes[sizes >= MIN_AREAS].index)].copy()
        # 선택 모집단을 확정한 뒤 미래 창을 붙인다. 미래 결측으로 순위를 다시 만들지 않는다.
        future = observed_window(commercial, quarter_add(origin, 4)).rename(columns={
            "rate": "future_rate", "closures": "future_closures", "denominator": "future_denominator",
        })
        frame = frame.join(future[["future_rate", "future_closures", "future_denominator"]], on=KEY)
        frames[origin] = frame
        duplicate_rhos = [correlation(g.stores, g.raw_saturation) for _, g in frame.groupby("industry")]
        duplicate_rhos = [r for r in duplicate_rhos if np.isfinite(r)]
        metrics, _ = evaluate(frame)
        origins[origin] = {
            "classification": "retrospective_partial_sensitivity_only",
            "validation_labels_matured": origin >= maturity,
            "asof_vintage_verified": False, "untouched_test": False,
            "future_window": [quarter_add(origin, i) for i in range(1, 5)],
            "sufficient_observed_cells": len(available),
            "evaluation_cells": len(frame), "evaluation_industries": frame.industry.nunique(),
            "excluded_small_industry_cells": len(available) - len(frame),
            "future_missing_cells": int(frame.future_rate.isna().sum()),
            "narrow_spread_industries": int(frame.groupby("industry").spread_narrow.first().sum()),
            "median_store_saturation_spearman": float(np.median(duplicate_rhos)),
            "danger_threshold_pct": thresholds["danger_pct"], "variants": metrics,
        }
    files = ["final_dataset.csv", "cell_train_table.csv", "lgbm_model_cell.pkl", "scores.csv",
             "demand_features_historical.csv", "demand_scores.csv"]
    result = sanitize({
        "plan": "docs/recommendation-score-audit-plan.md", "sample_min": SAMPLE_MIN,
        "model_validation_label_maturity": maturity,
        "historical_demand_quarters": demand_quarters,
        "training_target_available_by_quarter": label_availability,
        "production_change_allowed": False,
        "blockers": ["missing_historical_demand", "no_asof_panel_vintages", "no_untouched_test", "overlapping_future_windows", "provisional_latest_outcomes"],
        "bootstrap": {"unit": "industry", "samples": BOOTSTRAPS, "seed": SEED, "interpretation": "descriptive_only"},
        "input_sha256": {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in files},
        "origins": origins, "stability": compare_origins(frames), "latest_case": latest_case(commercial),
    })
    path = DATA / "recommendation_score_audit.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path.relative_to(ROOT)), "production_change_allowed": False,
                      "origins": origins, "latest_case": result["latest_case"]}, ensure_ascii=False, default=sanitize))


if __name__ == "__main__":
    main()
