import numpy as np
import pandas as pd
import pytest

from ai.audit_recommendation_scores import (
    apply_variants, observed_window, paired_interval, quarter_add, score_frame, select_top,
)


def observed_fixture():
    return pd.DataFrame({
        "area": ["가동"] * 5, "industry": ["한식"] * 5,
        "quarter": [20234, 20241, 20242, 20243, 20244],
        "stores": [100, 200, 400, 800, 1600],
        "observed_rate": [0.1, 0.1, 0.2, 0.3, 0.4],
    })


def test_observed_rate_uses_previous_quarter_denominator_not_current_stores():
    row = observed_window(observed_fixture(), 20244).iloc[0]
    assert row.denominator == 100 + 200 + 400 + 800
    assert row.closures == pytest.approx(10 + 40 + 120 + 320)
    assert row.rate == pytest.approx(490 / 1500 * 100)


@pytest.mark.parametrize("missing", [20234, 20242])
def test_missing_exact_quarter_is_not_bridged_or_treated_as_zero(missing):
    frame = observed_fixture()
    result = observed_window(frame[frame.quarter != missing], 20244)
    assert result.rate.isna().all()
    assert result.denominator.isna().all()


def test_missing_outcome_is_unknown_and_duplicate_quarter_rejected():
    frame = observed_fixture()
    frame.loc[frame.quarter == 20244, "observed_rate"] = np.nan
    assert observed_window(frame, 20244).rate.isna().all()
    with pytest.raises(ValueError, match="중복"):
        observed_window(pd.concat([frame, frame.iloc[:1]]), 20244)
    assert quarter_add(20244, 2) == 20252
    assert quarter_add(20241, -1) == 20234


def score_fixture():
    return pd.DataFrame({
        "area": ["가동", "나동", "다동"], "industry": ["한식"] * 3,
        "stores": [60, 80, 100], "saturation": [0.1, 0.2, 0.3],
        "model_safety": [80.0, 81.0, 82.0],
    })


def test_scoring_keeps_industry_reference_and_constant_demand():
    original = score_fixture()
    separate = original.copy().assign(industry="다른 업종", model_safety=[0, 50, 100])
    expected = score_frame(original)
    combined = score_frame(pd.concat([original, separate], ignore_index=True)).iloc[:3]
    assert combined.baseline.tolist() == expected.baseline.tolist()
    assert (combined.demand == 50).all()
    assert combined.baseline.tolist() == [50.0, 50.0, 50.0]
    # 극단 간 폭 2%p는 3%p 기준에 의해 완화된다. 공급 축과의 상쇄도 드러난다.
    assert combined.narrow_spread.tolist() == [55.8, 50.0, 44.2]
    assert combined.no_saturation.tolist() == [42.5, 50.0, 57.5]


def test_ablation_preserves_removed_weight_as_neutral():
    frame = score_frame(score_fixture())
    frame["saturation"] = 50.0
    result = apply_variants(frame)
    expected = (frame.growth * 0.35 + 50 * 0.30 + frame.competition * 0.20 + 50 * 0.15)
    assert result.no_saturation.tolist() == [round(v, 1) for v in expected]


def test_candidate_selection_does_not_peek_at_future_or_refill_risk_candidates():
    frame = pd.DataFrame({
        "area": ["가동", "나동", "다동", "라동"], "industry": ["한식"] * 4,
        "baseline": [90, 80, 70, 60], "separate_observed_risk": [90, 80, 70, 60],
        "observed_danger": [True, True, False, False],
        "future_rate": [np.nan, 50, 0, 1],
    })
    before = select_top(frame, "baseline").area.tolist()
    assert before == ["가동", "나동", "다동"]
    frame["future_rate"] = [100, 0, np.nan, 0]
    assert select_top(frame, "baseline").area.tolist() == before
    assert select_top(frame, "separate_observed_risk").area.tolist() == ["다동", "라동"]


def test_paired_uncertainty_is_reproducible_and_zero_for_identical_choices():
    assert paired_interval(np.array([0, 0, 0]))["descriptive_ci95"] == [0.0, 0.0]
    assert paired_interval(np.array([-1, 0, 2])) == paired_interval(np.array([-1, 0, 2]))
