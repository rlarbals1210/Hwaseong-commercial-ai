"""시점 제한 기준 모델 vs 과거 관측 이탈률 추가 모델.

실행: python -m ai.evaluate_closure_history
계획: docs/closure-history-validation-plan.md
운영 train_model.py/DB/API는 호출하거나 갱신하지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ai.pit_closure_dataset import (
    FEATURES, HORIZON, KEY, SnapshotHistory, quarter_add, read_observed_rows,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUTPUT = DATA / "closure_history_pit"
BASE_FEATURES = [*KEY, "store_count", "observed_tenure_quarters"]
ADDED_FEATURES = ["closure_rate_1q", "closure_rate_4q"]
TARGET = "target_absence_h2"
TRAIN_QUARTERS = (20214, 20221, 20222, 20223, 20224)
VALID_QUARTERS = (20233, 20234)
TEST_QUARTERS = (20243, 20244, 20251, 20252)
PRIMARY_QUARTERS = (20243, 20251)
MIN_STORES = 30
BOOTSTRAPS = 1000
SEED = 42


def split_for_quarter(quarter: int) -> str | None:
    if quarter in TRAIN_QUARTERS:
        return "train"
    if quarter in VALID_QUARTERS:
        return "validation"
    if quarter in TEST_QUARTERS:
        return "test"
    return None


def assert_temporal_contract(frame: pd.DataFrame) -> None:
    if not frame.feature_cutoff_quarter.eq(frame.quarter).all():
        raise ValueError("입력 시점이 예측 시점과 다릅니다")
    expected = frame.quarter.map(lambda q: quarter_add(q, HORIZON))
    if not frame.label_available_quarter.eq(expected).all() or not frame.target_quarter.eq(expected).all():
        raise ValueError("정답 확인 가능 시점이 예측 horizon과 다릅니다")
    for before, after in [("train", "validation"), ("validation", "test")]:
        earlier, later = frame[frame.split.eq(before)], frame[frame.split.eq(after)]
        if earlier.empty or later.empty:
            raise ValueError("시간 분할에 필요한 표본이 없습니다")
        if earlier.label_available_quarter.max() >= later.quarter.min():
            raise ValueError("앞 구간 정답이 다음 구간 예측 이전에 완성되지 않습니다")


def encode_categories(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    work = frame.copy()
    levels = {}
    for name in KEY:
        levels[name] = sorted(work.loc[work.split.eq("train"), name].unique().tolist())
        work[name] = work[name].astype(pd.CategoricalDtype(categories=levels[name]))
    return work, levels


def prepare_frame(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    frame = dataset.copy()
    frame["split"] = frame.quarter.map(split_for_quarter)
    selected = frame.split.notna()
    enough = frame.store_count.ge(MIN_STORES)
    complete_features = frame[FEATURES].notna().all(axis=1)
    known_target = frame[TARGET].notna()
    eligible = selected & enough & complete_features & known_target
    matched = frame[eligible].copy().reset_index(drop=True)
    assert_temporal_contract(matched)
    # 학습에 없던 지역은 모델 입력에서 NaN이 돼도 bootstrap 모집단에는 남아야 한다.
    matched["area_cluster"] = matched.area.astype(str)
    matched, _ = encode_categories(matched)
    audit = {
        "rows_in_fixed_periods": int(selected.sum()),
        "sufficient_rows_in_fixed_periods": int((selected & enough).sum()),
        "dropped_for_incomplete_history_or_target": int((selected & enough & ~eligible).sum()),
        "paired_rows": len(matched),
        "counts_by_split_quarter": {str(q): {"split": split_for_quarter(int(q)), "n": int(len(g))}
                                   for q, g in matched.groupby("quarter")},
        "unknown_category_cells_by_split": {
            split: int(matched.loc[matched.split.eq(split), KEY].isna().any(axis=1).sum())
            for split in ["train", "validation", "test"]
        },
        "latest_unlabelled_rows": int(frame[TARGET].isna().sum()),
    }
    return matched, audit


def metrics(truth, prediction, *, with_mae=True) -> dict:
    truth, prediction = np.asarray(truth, dtype=float), np.asarray(prediction, dtype=float)
    if not len(truth) or not np.isfinite(truth).all() or not np.isfinite(prediction).all():
        raise ValueError("평가 입력에 결측이나 빈 표본이 있습니다")
    top = prediction >= np.quantile(prediction, 0.9)
    rho = float(spearmanr(truth, prediction).statistic) if len(np.unique(prediction)) > 1 and len(np.unique(truth)) > 1 else np.nan
    return {
        "n": len(truth), "spearman": rho,
        "lift_top10pct": float(truth[top].mean() / truth.mean()) if truth.mean() > 0 else np.nan,
        "top10_n": int(top.sum()), "mean_target_pct": float(truth.mean() * 100),
        "mae_pp": float(np.abs(truth - prediction).mean() * 100) if with_mae else None,
    }


def by_quarter(frame: pd.DataFrame, prediction_column: str, *, with_mae=True) -> dict:
    return {int(q): metrics(g[TARGET], g[prediction_column], with_mae=with_mae)
            for q, g in frame.groupby("quarter", observed=True)}


def macro_metrics(quarters: dict, selected=PRIMARY_QUARTERS) -> dict:
    return {metric: float(np.mean([quarters[q][metric] for q in selected]))
            for metric in ["spearman", "lift_top10pct", "mae_pp"]}


def fit_variant(frame: pd.DataFrame, features: list[str]) -> tuple[lgb.LGBMRegressor, np.ndarray, dict]:
    train, valid = frame[frame.split.eq("train")], frame[frame.split.eq("validation")]
    model = lgb.LGBMRegressor(
        objective="regression", n_estimators=1000, learning_rate=0.05,
        num_leaves=31, min_child_samples=20, random_state=SEED,
        deterministic=True, force_col_wise=True, n_jobs=2, verbosity=-1,
    )
    model.fit(train[features], train[TARGET], eval_set=[(valid[features], valid[TARGET])],
              categorical_feature=KEY, callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
    prediction = np.clip(model.predict(frame[features]), 0, 1)
    evaluation = frame.assign(_prediction=prediction)
    test_metrics = by_quarter(evaluation[evaluation.split.eq("test")], "_prediction")
    gain = model.booster_.feature_importance(importance_type="gain")
    report = {
        "features": features, "best_iteration": int(model.best_iteration_),
        "validation": by_quarter(evaluation[evaluation.split.eq("validation")], "_prediction"),
        "test": test_metrics, "primary_macro": macro_metrics(test_metrics),
        "relative_training_gain_pct": {name: float(value / gain.sum() * 100) if gain.sum() else 0.0
                                       for name, value in zip(features, gain)},
    }
    return model, prediction, report


def clustered_bootstrap(frame: pd.DataFrame, samples: int = BOOTSTRAPS) -> dict:
    primary = frame[frame.quarter.isin(PRIMARY_QUARTERS)].reset_index(drop=True)
    groups = [g.index.to_numpy() for _, g in primary.groupby("area_cluster", observed=True)]
    rng = np.random.default_rng(SEED)
    deltas = []
    for _ in range(samples):
        index = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        sample = primary.iloc[index]
        before = macro_metrics(by_quarter(sample, "baseline_prediction"))
        after = macro_metrics(by_quarter(sample, "history_prediction"))
        delta = {name: after[name] - before[name] for name in before}
        if np.isfinite(list(delta.values())).all():
            deltas.append(delta)
    if not deltas:
        raise ValueError("유효한 bootstrap 표본이 없습니다")
    return {
        "cluster": "area", "samples_requested": samples, "samples_valid": len(deltas),
        "delta": "history model minus baseline, equal-weight mean across primary quarters",
        "ci95": {name: np.quantile([d[name] for d in deltas], [0.025, 0.975]).tolist()
                 for name in deltas[0]},
    }


def direction_gate(baseline: dict, history: dict, bootstrap: dict) -> bool:
    consistent = all(history["test"][q][m] > baseline["test"][q][m]
                     for q in PRIMARY_QUARTERS for m in ["spearman", "lift_top10pct"])
    uncertainty = all(bootstrap["ci95"][m][0] > 0 for m in ["spearman", "lift_top10pct"])
    return bool(consistent and uncertainty and history["primary_macro"]["mae_pp"] <= baseline["primary_macro"]["mae_pp"])


def diagnose_data(history: SnapshotHistory, observed: pd.DataFrame, frame: pd.DataFrame) -> dict:
    checks = {}
    for quarter in PRIMARY_QUARTERS:
        index = history.quarters.index(quarter)
        prefix = SnapshotHistory(observed[observed.quarter.le(quarter)])
        full_features = history.features_at(index).sort_values(KEY).reset_index(drop=True)
        prefix_features = prefix.features_at(index).sort_values(KEY).reset_index(drop=True)
        checks[quarter] = full_features.equals(prefix_features)
    if not all(checks.values()):
        raise ValueError("실제 자료에서 미래 행을 제거했을 때 과거 입력이 달라졌습니다")
    return {
        "posthoc_only": True, "changed_features_splits_or_models": False,
        "prefix_invariance_checks": checks,
        "target_distribution_by_split": frame.groupby("split")[TARGET].agg(["size", "mean", "median"]).to_dict("index"),
        "target_distribution_by_quarter": frame.groupby("quarter")[TARGET].mean().to_dict(),
        "reappearance_after_endpoint": history.endpoint_reappearance_audit(TRAIN_QUARTERS + VALID_QUARTERS + TEST_QUARTERS),
    }


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), 7) if np.isfinite(value) else None
    return value


def main() -> None:
    observed, source_audit = read_observed_rows(DATA / "store_panel.csv")
    history = SnapshotHistory(observed)
    dataset = history.dataset()
    frame, eligibility = prepare_frame(dataset)
    baseline, baseline_prediction, baseline_report = fit_variant(frame, BASE_FEATURES)
    augmented, history_prediction, history_report = fit_variant(frame, BASE_FEATURES + ADDED_FEATURES)
    evaluation = frame.assign(baseline_prediction=baseline_prediction, history_prediction=history_prediction)
    test = evaluation[evaluation.split.eq("test")].copy()
    bootstrap = clustered_bootstrap(test)
    persistence = by_quarter(test, "closure_rate_4q", with_mae=False)
    quality_diagnostic = json_safe(diagnose_data(history, observed, frame))
    source_audit["feature_cutoff_contract_passed"] = True
    result = json_safe({
        "plan": "docs/closure-history-validation-plan.md", "source_audit": source_audit,
        "eligibility": eligibility,
        "split": {"train": TRAIN_QUARTERS, "validation": VALID_QUARTERS, "test": TEST_QUARTERS,
                  "primary": PRIMARY_QUARTERS, "train_labels_complete_by": quarter_add(max(TRAIN_QUARTERS), HORIZON),
                  "validation_labels_complete_by": quarter_add(max(VALID_QUARTERS), HORIZON)},
        "baseline": baseline_report, "with_closure_history": history_report,
        "observed_4q_ranking_baseline": persistence, "paired_bootstrap": bootstrap,
        "directional_signal_passed": direction_gate(baseline_report, history_report, bootstrap),
        "production_ready": False,
        "production_blockers": ["snapshot_absence_not_confirmed_closure", "release_dates_unverified",
                                "tenure_definition_changed", "only_two_primary_origins", "historically_reused_data"],
    })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(OUTPUT / "dataset.csv", index=False, encoding="utf-8-sig")
    for name, model, features in [("baseline", baseline, BASE_FEATURES), ("with_closure_history", augmented, BASE_FEATURES + ADDED_FEATURES)]:
        joblib.dump({"model": model, "features": features, "source_audit": source_audit,
                     "split": result["split"], "research_only": True}, OUTPUT / f"{name}.pkl")
    (OUTPUT / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (OUTPUT / "data_quality_diagnostic.json").write_text(json.dumps(quality_diagnostic, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ["source_audit", "plan"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
