"""실행: python -m ai.evaluate_permit_labels. 운영 파이프라인과 분리된 회고적 검증."""
from __future__ import annotations

import argparse
import hashlib
import json

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from ai.evaluate_closure_history import (BASE_FEATURES, ADDED_FEATURES, PRIMARY_QUARTERS,
                                         encode_categories, json_safe, metrics, split_for_quarter)
from ai.permit_matching import aggregate_labels, label_links, link_candidates, quarter_end
from ai.permit_sources import OUTPUT, load_permits, load_snapshots
from ai.pit_closure_dataset import FEATURES, KEY, SnapshotHistory, quarter_code, read_observed_rows
from eda import paths

MODEL_FEATURES = BASE_FEATURES + ADDED_FEATURES
REGISTRY_TARGET = "target_registry_h2"
ABSENCE_TARGET = "target_absence_h2"
SEED = 42


def confusion(frame: pd.DataFrame) -> dict:
    return {f"registry_{r}_absence_{a}": int((frame[REGISTRY_TARGET].eq(r) & frame[ABSENCE_TARGET].eq(a)).sum())
            for r in [0, 1] for a in [0, 1]}


def label_audit(snapshots: pd.DataFrame, links: pd.DataFrame, labelled: pd.DataFrame) -> dict:
    paired = labelled[labelled.label_status.eq("paired")]
    by_industry = []
    mature = snapshots[snapshots.quarter.le(20252)]
    for industry, group in mature.groupby("industry"):
        subset = paired[paired.industry.eq(industry)]
        by_industry.append({"industry": industry, "origin_rows": len(group), "paired_rows": len(subset),
                            "coverage_pct": len(subset) / len(group) * 100, **confusion(subset)})
    # 폐업일 이후 관측은 사후 진단에만 쓰며 정답이나 학습 표본을 다시 고르지 않는다.
    close_links = links[links.close_date.notna()][["store_id", "permit_key", "close_date"]].drop_duplicates()
    later = close_links.merge(snapshots[["store_id", "quarter"]], on="store_id")
    later["after_closure"] = pd.to_datetime(later.quarter.map(quarter_end)).gt(later.close_date)
    return {"unique_linked_stores": int(links.store_id.nunique()),
            "label_status_counts": labelled.label_status.value_counts().to_dict(),
            "paired_store_quarters": len(paired), "unique_paired_stores": int(paired.store_id.nunique()),
            "confusion_all_mature": confusion(paired), "by_industry": by_industry,
            "by_quarter": {int(q): {"paired_rows": len(g), **confusion(g)} for q, g in paired.groupby("quarter")},
            "posthoc_closed_link_count": len(close_links),
            "posthoc_closed_links_with_later_snapshot": int(later[later.after_closure][["store_id", "permit_key"]].drop_duplicates().shape[0]),
            "posthoc_changed_selection": False}


def saved_label_diagnostic(labelled: pd.DataFrame) -> dict:
    """운영 학습 원천의 전 기간 갭필링 정답도 대조하되 시간 검증 모델에는 넣지 않는다."""
    legacy = pd.read_csv(paths.STORE_LABELS_CSV, usecols=["상가업소번호", "기준분기", "is_filled", "label_h2"],
                         dtype={"상가업소번호": str})
    legacy = legacy[legacy.is_filled.eq(0)].rename(columns={"상가업소번호": "store_id", "기준분기": "quarter"})
    legacy["quarter"] = legacy.quarter.map(quarter_code)
    paired = labelled[labelled.label_status.eq("paired")].merge(legacy, on=["store_id", "quarter"],
                                                                  how="left", validate="one_to_one")
    if paired.label_h2.isna().any() or not paired.label_h2.isin([0, 1]).all():
        raise ValueError("연결 표본의 저장된 학습 정답이 누락되거나 이진값이 아닙니다")
    diagnostic = paired.drop(columns=ABSENCE_TARGET).rename(columns={"label_h2": ABSENCE_TARGET})
    return {"posthoc_only": True, "used_for_fitting_or_selection": False,
            "source": paths.STORE_LABELS_CSV.name, "definition": "saved full-history gap-filled label_h2",
            "paired_rows": len(paired), "confusion": confusion(diagnostic),
            "by_quarter": {int(q): {"paired_rows": len(g), **confusion(g)} for q, g in diagnostic.groupby("quarter")}}


def prepare_paired_frame(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    work = dataset.copy()
    work["split"] = work.quarter.map(split_for_quarter)
    selected = work.split.notna()
    eligible = (selected & work.store_count.ge(30) & work.matched_count.ge(30) & work.coverage.ge(.5)
                & work[FEATURES + [REGISTRY_TARGET, ABSENCE_TARGET]].notna().all(axis=1))
    frame = work[eligible].copy().reset_index(drop=True)
    frame["area_cluster"] = frame.area.astype(str)
    frame["industry_original"] = frame.industry.astype(str)
    frame, levels = encode_categories(frame)
    counts = frame.groupby("quarter", observed=True).size().to_dict()
    ready = int(frame.split.eq("train").sum()) >= 100
    for q in [20233, 20234, *PRIMARY_QUARTERS]:
        ready &= counts.get(q, 0) >= 20
    for earlier, later in [("train", "validation"), ("validation", "test")]:
        before, after = frame[frame.split.eq(earlier)], frame[frame.split.eq(later)]
        if not before.empty and not after.empty and before.target_quarter.max() >= after.quarter.min():
            raise ValueError("앞 구간의 사건 창이 다음 구간 예측 시점 전에 끝나지 않습니다")
    audit = {"rows_in_fixed_periods": int(selected.sum()), "paired_cells": len(frame),
             "by_split": frame.groupby("split", observed=True).size().to_dict(),
             "by_original_industry": frame.industry_original.value_counts().to_dict(),
             "by_quarter": {int(q): {"n": len(g), "matched_stores": int(g.matched_count.sum()),
                                     "mean_coverage_pct": float(g.coverage.mean()*100),
                                     "registry_rate_pct": float(g[REGISTRY_TARGET].mean()*100),
                                     "absence_rate_pct": float(g[ABSENCE_TARGET].mean()*100)}
                            for q, g in frame.groupby("quarter", observed=True)},
             "minimum_sample_gate": bool(ready), "train_category_levels": levels,
             "unknown_category_rows": int(frame[KEY].isna().any(axis=1).sum())}
    return frame, audit


def evaluate(frame: pd.DataFrame, prediction: np.ndarray) -> dict:
    work = frame.assign(prediction=prediction)
    return {int(q): metrics(g[REGISTRY_TARGET], g.prediction) for q, g in work.groupby("quarter", observed=True)}


def macro(report: dict) -> dict:
    return {name: float(np.mean([report[q][name] for q in PRIMARY_QUARTERS]))
            for name in ["spearman", "lift_top10pct", "mae_pp"]}


def fit_variant(frame: pd.DataFrame, train_target: str) -> tuple:
    train, valid = frame[frame.split.eq("train")], frame[frame.split.eq("validation")]
    model = lgb.LGBMRegressor(objective="regression", n_estimators=1000, learning_rate=.05,
                             num_leaves=31, min_child_samples=20, random_state=SEED,
                             deterministic=True, force_col_wise=True, n_jobs=2, verbosity=-1)
    model.fit(train[MODEL_FEATURES], train[train_target],
              eval_set=[(valid[MODEL_FEATURES], valid[REGISTRY_TARGET])], categorical_feature=KEY,
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
    prediction = np.clip(model.predict(frame[MODEL_FEATURES]), 0, 1)
    test_mask = frame.split.eq("test")
    report = evaluate(frame[test_mask], prediction[test_mask])
    return model, prediction, {"training_target": train_target, "best_iteration": int(model.best_iteration_),
                                "test": report, "primary_macro": macro(report)}


def bootstrap(frame: pd.DataFrame, samples: int = 1000) -> dict:
    primary = frame[frame.quarter.isin(PRIMARY_QUARTERS)].reset_index(drop=True)
    groups = [g.index.to_numpy() for _, g in primary.groupby("area_cluster", observed=True)]
    rng = np.random.default_rng(SEED)
    deltas = []
    for _ in range(samples):
        indexes = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        sample = primary.iloc[indexes]
        if not set(PRIMARY_QUARTERS).issubset(sample.quarter.unique()):
            continue
        before, after = [macro(evaluate(sample, sample[name].to_numpy())) for name in ["absence_prediction", "registry_prediction"]]
        delta = {m: after[m] - before[m] for m in before}
        if np.isfinite(list(delta.values())).all():
            deltas.append(delta)
    return {"samples_requested": samples, "samples_valid": len(deltas), "cluster": "area",
            "delta": "registry-label model minus absence-label model, evaluated against registry labels",
            "ci95": {m: np.quantile([d[m] for d in deltas], [.025, .975]).tolist()
                     for m in ["spearman", "lift_top10pct", "mae_pp"]} if deltas else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels-only", action="store_true")
    args = parser.parse_args()
    snapshots, sources = load_snapshots()
    permits, inventory = load_permits()
    observed, _ = read_observed_rows(paths.STORE_PANEL_CSV)
    keys = ["store_id", "quarter", *KEY]
    left = snapshots[keys].sort_values(["quarter", "store_id"]).reset_index(drop=True)
    right = observed[keys].sort_values(["quarter", "store_id"]).reset_index(drop=True)
    if not left.equals(right):
        raise ValueError("SSD 원본과 기존 실제 관측 패널의 키/업종이 일치하지 않습니다")
    history = SnapshotHistory(observed)
    feature_parts = [history.features_at(i) for i in range(len(history.quarters))]
    features = pd.concat(feature_parts, ignore_index=True)
    prefix_checks = {}
    for q in PRIMARY_QUARTERS:
        prefix = SnapshotHistory(observed[observed.quarter.le(q)])
        prefix_checks[q] = prefix.features_at(len(prefix.quarters)-1).equals(feature_parts[history.quarters.index(q)])
    if not all(prefix_checks.values()):
        raise ValueError("미래 자료 제거 시 입력이 달라집니다")
    print(json.dumps({"source_rows_verified": len(left), "prefix_checks": prefix_checks}), flush=True)
    links, matching = link_candidates(snapshots, permits)
    labelled = label_links(links, dict(zip(history.quarters, history.ids)))
    dataset = aggregate_labels(labelled, features)
    frame, eligibility = prepare_paired_frame(dataset)
    report = {"plan": "docs/permit-label-validation-plan.md", "research_only": True, "production_ready": False,
              "retrospective_registry_vintage": True, "actual_label_availability_verified": False,
              "sources": sources, "permit_inventory": inventory, "prefix_checks": prefix_checks,
              "matching": matching, "label_quality": label_audit(snapshots, links, labelled),
              "posthoc_saved_gap_filled_label_audit": saved_label_diagnostic(labelled),
              "eligibility": eligibility, "models_run": False}
    dataset.to_csv(OUTPUT / "cell_dataset.csv", index=False, encoding="utf-8-sig")
    labelled.to_pickle(OUTPUT / "linked_labels.pkl")
    if eligibility["minimum_sample_gate"] and not args.labels_only:
        reports = {}
        for variant, target in [("absence", ABSENCE_TARGET), ("registry", REGISTRY_TARGET)]:
            model, prediction, result = fit_variant(frame, target)
            reports[variant] = result
            frame[f"{variant}_prediction"] = prediction
            joblib.dump({"model": model, "features": MODEL_FEATURES, "research_only": True,
                         "train_category_levels": eligibility["train_category_levels"], "sources": sources},
                        OUTPUT / f"{variant}_label_model.pkl")
        ci = bootstrap(frame)
        consistent = all(reports["registry"]["test"][q][m] > reports["absence"]["test"][q][m]
                         for q in PRIMARY_QUARTERS for m in ["spearman", "lift_top10pct"])
        signal = (consistent and ci["ci95"] is not None
                  and all(ci["ci95"][m][0] > 0 for m in ["spearman", "lift_top10pct"])
                  and reports["registry"]["primary_macro"]["mae_pp"] <= reports["absence"]["primary_macro"]["mae_pp"])
        report.update(models_run=True, models=reports, bootstrap=ci, directional_signal_passed=signal)
        test = frame[frame.split.eq("test")]
        constant = frame.loc[frame.split.eq("train"), REGISTRY_TARGET].mean()
        constant_report = evaluate(test, np.full(len(test), constant))
        report["posthoc_constant_benchmark"] = {
            "reason": "separate changing target level from useful ranking; not used for model selection",
            "fitted_on": "training registry labels only", "test": constant_report,
            "primary_macro": macro(constant_report),
        }
        frame.to_pickle(OUTPUT / "model_evaluation.pkl")
    report["plan_sha256"] = hashlib.sha256((paths.PROJECT_ROOT / report["plan"]).read_bytes()).hexdigest()
    output = json_safe(report)
    (OUTPUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: output[k] for k in ["matching", "eligibility", "models_run"]}, ensure_ascii=False), flush=True)
    if report["models_run"]:
        print(json.dumps({k: output[k] for k in ["models", "bootstrap", "directional_signal_passed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
