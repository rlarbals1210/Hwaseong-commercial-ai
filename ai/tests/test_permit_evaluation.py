import numpy as np
import pandas as pd
import pytest

from ai.evaluate_permit_labels import evaluate, prepare_paired_frame
from ai.permit_sources import parse_dates


def cell(quarter, **changes):
    year, q = divmod(quarter, 10)
    target = (year + (q + 1) // 4) * 10 + (q + 1) % 4 + 1
    return dict(area="가상동", industry="한식", quarter=quarter, feature_cutoff_quarter=quarter,
                target_quarter=target, store_count=60, observed_tenure_quarters=5,
                closure_rate_1q=.1, closure_rate_4q=.15, matched_count=30, coverage=.5,
                target_registry_h2=.05, target_absence_h2=.1) | changes


def test_insufficient_coverage_unknown_label_and_small_sample_do_not_train():
    data = pd.DataFrame([cell(20214), cell(20221, matched_count=29), cell(20222, coverage=.49),
                         cell(20223, target_registry_h2=np.nan), cell(20224, closure_rate_4q=np.nan)])
    frame, audit = prepare_paired_frame(data)
    assert frame.quarter.tolist() == [20214]
    assert not audit["minimum_sample_gate"]


def test_event_window_must_end_before_next_split():
    data = pd.DataFrame([cell(20224, target_quarter=20234), cell(20233), cell(20243)])
    with pytest.raises(ValueError, match="사건 창"):
        prepare_paired_frame(data)


def test_both_predictions_are_evaluated_against_registry_truth():
    frame = pd.DataFrame([cell(20243, target_registry_h2=.1, target_absence_h2=.9),
                          cell(20243, target_registry_h2=.2, target_absence_h2=.8)])
    report = evaluate(frame, np.array([.1, .2]))[20243]
    assert report["mae_pp"] == 0 and report["spearman"] > .99


def test_unknown_industry_is_not_dropped_from_evaluation():
    frame, audit = prepare_paired_frame(pd.DataFrame([cell(20214), cell(20243, industry="새업종")]))
    assert len(frame) == 2 and audit["unknown_category_rows"] == 1
    assert frame.iloc[1].industry_original == "새업종"


def test_date_formats_and_missing_values():
    parsed = parse_dates(pd.Series(["2024-06-30", "20240630120000", "", "20249999"]))
    assert parsed.iloc[0] == parsed.iloc[1] == pd.Timestamp("2024-06-30")
    assert parsed.iloc[2:].isna().all()
