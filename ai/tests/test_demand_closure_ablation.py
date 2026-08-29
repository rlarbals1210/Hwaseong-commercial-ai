import numpy as np

from ai.evaluate_demand_closure_ablation import (
    quarter_string_to_code,
    regression_metrics,
    split_for_quarter,
)


def test_quarter_conversion_and_split_are_chronological() -> None:
    assert quarter_string_to_code("2022Q4") == 20224
    assert split_for_quarter(20221) == "train"
    assert split_for_quarter(20232) == "validation"
    assert split_for_quarter(20251) == "test"
    assert split_for_quarter(20233) is None


def test_regression_metrics_reward_correct_ranking() -> None:
    truth = np.array([0.01, 0.02, 0.04, 0.08, 0.16])
    correct = regression_metrics(truth, truth)
    reversed_metrics = regression_metrics(truth, truth[::-1])
    assert np.isclose(correct["spearman"], 1.0)
    assert np.isclose(reversed_metrics["spearman"], -1.0)
    assert correct["lift_top10pct"] > reversed_metrics["lift_top10pct"]
    assert correct["mae"] == 0.0
