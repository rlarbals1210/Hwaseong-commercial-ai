"""과거 수요 피처가 폐업률 예측에 주는 증분 효과를 제한적으로 비교한다.

운영 모델의 학습·산출물은 수정하지 않는다. 수요 피처가 존재하는 7개 분기만
같은 행으로 맞춘 뒤, 기준 모델과 수요 피처 추가 모델을 별도로 학습한다.

분할은 시간순으로 고정한다.

* train: 2022Q1, 2022Q2, 2022Q4, 2023Q1
* validation: 2023Q2
* test: 2025Q1, 2025Q2

검증 분기가 한 개뿐이고 2023Q2와 2025Q1 사이가 비어 있으므로 결과는 방향성
참고용이다. 성능이 좋아도 운영 폐업모델에는 자동으로 반영하지 않는다.

    python ai/evaluate_demand_closure_ablation.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eda.paths import CELL_TRAIN_TABLE_CSV, PROCESSED_DATA_DIR

HISTORICAL_DEMAND_CSV = PROCESSED_DATA_DIR / "demand_features_historical.csv"
ABLATION_RESULTS_JSON = PROCESSED_DATA_DIR / "demand_closure_ablation_results.json"

TRAIN_QUARTERS = (20221, 20222, 20224, 20231)
VALID_QUARTERS = (20232,)
TEST_QUARTERS = (20251, 20252)

CAT_FEATURES = ["행정동명", "상권업종중분류명"]
BASELINE_NUM_FEATURES = ["평균업력_분기수", "점포수"]
# 사전에 정한 두 개만 추가한다. 여러 조합을 test에서 골라내는 것을 피한다.
DEMAND_FEATURES = ["수요공급격차_log", "수요모멘텀_3개월"]
TARGET = "폐업률"
MIN_STORES = 30
BOOTSTRAP_SAMPLES = 1000
RANDOM_SEED = 42


def quarter_string_to_code(value: str) -> int:
    year, quarter = str(value).split("Q")
    return int(year) * 10 + int(quarter)


def split_for_quarter(quarter: int) -> str | None:
    if quarter in TRAIN_QUARTERS:
        return "train"
    if quarter in VALID_QUARTERS:
        return "validation"
    if quarter in TEST_QUARTERS:
        return "test"
    return None


def regression_metrics(truth: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    truth = np.asarray(truth, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if len(truth) == 0:
        raise ValueError("평가 행이 없습니다")
    rho = float(spearmanr(prediction, truth).statistic)
    top10 = prediction >= np.quantile(prediction, 0.9)
    mean_target = float(np.mean(truth))
    lift = float(np.mean(truth[top10]) / mean_target) if mean_target > 0 else math.nan
    return {
        "n": int(len(truth)),
        "mean_closure_rate": mean_target,
        "mae": float(np.mean(np.abs(truth - prediction))),
        "spearman": rho,
        "lift_top10pct": lift,
        "top10_n": int(top10.sum()),
    }


def _model() -> lgb.LGBMRegressor:
    # 운영 셀 모델과 같은 하이퍼파라미터를 사용해 피처 추가 효과만 비교한다.
    return lgb.LGBMRegressor(
        objective="regression",
        n_estimators=1000,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        random_state=RANDOM_SEED,
        verbosity=-1,
        deterministic=True,
        force_col_wise=True,
    )


def train_variant(
    frame: pd.DataFrame,
    numeric_features: list[str],
) -> tuple[lgb.LGBMRegressor, dict]:
    features = CAT_FEATURES + numeric_features
    train = frame[frame["split"] == "train"]
    validation = frame[frame["split"] == "validation"]
    test = frame[frame["split"] == "test"]
    model = _model()
    model.fit(
        train[features],
        train[TARGET],
        eval_set=[(validation[features], validation[TARGET])],
        categorical_feature=CAT_FEATURES,
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
    )
    valid_prediction = model.predict(validation[features], num_iteration=model.best_iteration_)
    test_prediction = model.predict(test[features], num_iteration=model.best_iteration_)
    return model, {
        "features": features,
        "best_iteration": int(model.best_iteration_),
        "validation": regression_metrics(validation[TARGET], valid_prediction),
        "test": regression_metrics(test[TARGET], test_prediction),
        "test_prediction": test_prediction,
    }


def _metric_delta(
    truth: np.ndarray,
    baseline_prediction: np.ndarray,
    demand_prediction: np.ndarray,
) -> dict[str, float]:
    baseline = regression_metrics(truth, baseline_prediction)
    demand = regression_metrics(truth, demand_prediction)
    return {
        "spearman": float(demand["spearman"] - baseline["spearman"]),
        "lift_top10pct": float(demand["lift_top10pct"] - baseline["lift_top10pct"]),
        "mae": float(demand["mae"] - baseline["mae"]),
    }


def clustered_bootstrap(
    test: pd.DataFrame,
    baseline_prediction: np.ndarray,
    demand_prediction: np.ndarray,
) -> dict:
    work = test[["행정동명", TARGET]].copy().reset_index(drop=True)
    work["baseline_prediction"] = np.asarray(baseline_prediction)
    work["demand_prediction"] = np.asarray(demand_prediction)
    areas = sorted(work["행정동명"].unique())
    rng = np.random.default_rng(RANDOM_SEED)
    deltas: list[dict[str, float]] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled_areas = rng.choice(areas, size=len(areas), replace=True)
        pieces = [work[work["행정동명"] == area] for area in sampled_areas]
        sample = pd.concat(pieces, ignore_index=True)
        delta = _metric_delta(
            sample[TARGET].to_numpy(),
            sample["baseline_prediction"].to_numpy(),
            sample["demand_prediction"].to_numpy(),
        )
        if all(np.isfinite(list(delta.values()))):
            deltas.append(delta)

    result: dict[str, dict[str, float | list[float]]] = {}
    for metric in ("spearman", "lift_top10pct", "mae"):
        values = np.asarray([row[metric] for row in deltas], dtype=float)
        result[metric] = {
            "ci95": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))],
            "median": float(np.median(values)),
            "probability_positive": float(np.mean(values > 0)),
        }
    return {
        "cluster": "행정동명",
        "samples_requested": BOOTSTRAP_SAMPLES,
        "samples_valid": len(deltas),
        "delta_definition": "demand_augmented - baseline",
        "metrics": result,
    }


def load_matched_frame() -> pd.DataFrame:
    cell = pd.read_csv(CELL_TRAIN_TABLE_CSV)
    cell["기준_년분기_코드"] = cell["기준분기"].map(quarter_string_to_code)
    demand = pd.read_csv(HISTORICAL_DEMAND_CSV)
    demand = demand.rename(columns={"통합카테고리": "상권업종중분류명"})
    keys = ["행정동명", "상권업종중분류명", "기준_년분기_코드"]
    if demand.duplicated(keys).any():
        raise ValueError("과거 수요 피처 키가 중복됐습니다")

    selected = demand[keys + DEMAND_FEATURES]
    matched = cell.merge(selected, on=keys, how="inner", validate="one_to_one")
    matched["split"] = matched["기준_년분기_코드"].map(split_for_quarter)
    matched = matched[
        matched["split"].notna()
        & matched[TARGET].notna()
        & (matched["점포수"] >= MIN_STORES)
    ].copy()
    required = BASELINE_NUM_FEATURES + DEMAND_FEATURES
    matched = matched.dropna(subset=required).reset_index(drop=True)
    for column in CAT_FEATURES:
        matched[column] = matched[column].astype("category")
    return matched


def main() -> None:
    frame = load_matched_frame()
    counts = frame.groupby(["split", "기준_년분기_코드"], observed=True).size()
    for split in ("train", "validation", "test"):
        if not (frame["split"] == split).any():
            raise ValueError(f"{split} 분할이 비었습니다")

    _, baseline = train_variant(frame, BASELINE_NUM_FEATURES)
    _, demand_augmented = train_variant(frame, BASELINE_NUM_FEATURES + DEMAND_FEATURES)
    test = frame[frame["split"] == "test"].copy().reset_index(drop=True)
    baseline_prediction = baseline.pop("test_prediction")
    demand_prediction = demand_augmented.pop("test_prediction")
    overall_delta = _metric_delta(test[TARGET], baseline_prediction, demand_prediction)

    per_quarter = []
    for quarter, indexes in test.groupby("기준_년분기_코드", observed=True).groups.items():
        idx = np.asarray(list(indexes), dtype=int)
        base_metrics = regression_metrics(test.loc[idx, TARGET], baseline_prediction[idx])
        demand_metrics = regression_metrics(test.loc[idx, TARGET], demand_prediction[idx])
        per_quarter.append({
            "quarter": int(quarter),
            "baseline": base_metrics,
            "demand_augmented": demand_metrics,
            "delta": {
                "spearman": demand_metrics["spearman"] - base_metrics["spearman"],
                "lift_top10pct": demand_metrics["lift_top10pct"] - base_metrics["lift_top10pct"],
                "mae": demand_metrics["mae"] - base_metrics["mae"],
            },
        })

    bootstrap = clustered_bootstrap(test, baseline_prediction, demand_prediction)
    spearman_ci = bootstrap["metrics"]["spearman"]["ci95"]
    lift_ci = bootstrap["metrics"]["lift_top10pct"]["ci95"]
    consistent_by_quarter = all(item["delta"]["spearman"] > 0 for item in per_quarter)
    directional_signal = bool(
        overall_delta["spearman"] > 0
        and overall_delta["lift_top10pct"] > 0
        and spearman_ci[0] > 0
        and lift_ci[0] > 0
        and consistent_by_quarter
    )

    results = {
        "method_version": "demand-closure-ablation-v1",
        "research_only": True,
        "production_model_changed": False,
        "production_ready": False,
        "target": "관측 시점 기준 2분기 내 셀 폐업률",
        "matched_sample": {
            "minimum_stores": MIN_STORES,
            "rows": len(frame),
            "areas": int(frame["행정동명"].nunique()),
            "industries": int(frame["상권업종중분류명"].nunique()),
            "quarters": sorted(int(value) for value in frame["기준_년분기_코드"].unique()),
            "rows_by_split_quarter": [
                {"split": split, "quarter": int(quarter), "rows": int(value)}
                for (split, quarter), value in counts.items()
            ],
        },
        "split": {
            "train": list(TRAIN_QUARTERS),
            "validation": list(VALID_QUARTERS),
            "test": list(TEST_QUARTERS),
            "rule": "chronological, no random row split",
        },
        "baseline": baseline,
        "demand_augmented": demand_augmented,
        "test_delta": overall_delta,
        "test_by_quarter": per_quarter,
        "clustered_bootstrap": bootstrap,
        "directional_signal_passed": directional_signal,
        "directional_signal_gate": {
            "overall_spearman_delta_positive": overall_delta["spearman"] > 0,
            "overall_lift_delta_positive": overall_delta["lift_top10pct"] > 0,
            "spearman_ci95_lower_positive": spearman_ci[0] > 0,
            "lift_ci95_lower_positive": lift_ci[0] > 0,
            "spearman_delta_positive_in_both_test_quarters": consistent_by_quarter,
        },
        "limitations": [
            "수요 피처가 있는 분기가 7개뿐이며 validation은 2023Q2 한 개 분기다.",
            "2023Q2와 test 시작인 2025Q1 사이에 카드매출 결측으로 긴 시간 공백이 있다.",
            "카드 업종과 소진공 업종은 공식 일대일 대응표가 아닌 수기 프록시 매핑이다.",
            "행정동 클러스터 부트스트랩은 29개 동만 재표집하므로 시간축 불확실성을 해소하지 못한다.",
            "이 실험은 기존 운영 모델의 공식 성능 수치와 직접 비교할 수 없는 축소 표본 결과다.",
        ],
        "next_gate": [
            "연속 과거 분기 12개 이상 확보",
            "기존 운영 validation 구간에 수요 피처 2개 분기 이상 확보",
            "동일한 운영 시간 분할에서 기준 모델 대비 Spearman과 Top 10 lift 재검증",
        ],
    }
    ABLATION_RESULTS_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"matched rows: {len(frame):,}")
    print(f"baseline test: {baseline['test']}")
    print(f"demand test: {demand_augmented['test']}")
    print(f"delta: {overall_delta}")
    print(f"directional signal: {directional_signal}")
    print(f"saved: {ABLATION_RESULTS_JSON}")


if __name__ == "__main__":
    main()
