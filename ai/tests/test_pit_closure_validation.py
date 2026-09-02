import numpy as np
import pandas as pd
import pytest

from ai.pit_closure_dataset import SnapshotHistory, quarter_add, read_observed_rows
from ai.evaluate_closure_history import (
    PRIMARY_QUARTERS, TARGET, assert_temporal_contract, clustered_bootstrap,
    direction_gate, encode_categories, metrics,
)


def snapshots(presence=(0, 2, 3, 5, 7), count=8):
    rows = []
    for i in range(count):
        for store in (["always", "returning"] if i in presence else ["always"]):
            rows.append({"store_id": store, "quarter": quarter_add(20214, i),
                         "area": "가동", "industry": "한식"})
    return pd.DataFrame(rows)


def test_future_rows_cannot_change_past_features_even_when_a_store_returns():
    full = snapshots()
    for origin in [1, 4]:
        prefix = full[full.quarter <= quarter_add(20214, origin)]
        expected = SnapshotHistory(prefix).features_at(origin)
        actual = SnapshotHistory(full).features_at(origin)
        pd.testing.assert_frame_equal(actual, expected)
        mutated = full.copy()
        future = mutated.quarter > quarter_add(20214, origin)
        mutated.loc[future, "store_id"] = "new-" + mutated.loc[future, "store_id"]
        mutated.loc[future, "area"] = "미래동"
        pd.testing.assert_frame_equal(SnapshotHistory(mutated).features_at(origin), expected)


def test_one_quarter_gap_is_only_corrected_after_the_return_is_known():
    history = SnapshotHistory(snapshots())
    assert history.features_at(1).iloc[0].closure_rate_1q == 0.5
    assert history.features_at(2).iloc[0].closure_rate_1q == 0.0
    # 시점 4의 이탈을 다음 분기 재등장으로 미리 없애면 안 된다.
    assert history.features_at(4).iloc[0].closure_rate_1q == 0.5
    assert len(history.known_groups(1, 1)[("가동", "한식")]) == 1
    assert len(history.known_groups(1, 2)[("가동", "한식")]) == 2
    with pytest.raises(ValueError, match="미래"):
        history.known_groups(3, 2)


def test_four_quarter_rate_uses_exposure_denominators_and_missing_stays_missing():
    history = SnapshotHistory(snapshots())
    row = history.features_at(4).iloc[0]
    # 시점 4에서 보이는 분기 0~4의 보정 집합 크기 = 2,2,2,2,1.
    assert row.closure_rate_4q == 1 / 8
    assert row.store_count == 1
    assert row.observed_tenure_quarters == 5
    assert np.isnan(history.features_at(3).iloc[0].closure_rate_4q)


def test_label_requires_endpoint_and_is_not_revised_after_endpoint():
    full = snapshots(presence=(0, 3))
    prefix = full[full.quarter <= quarter_add(20214, 2)]
    actual = SnapshotHistory(full).labels_at(0)
    pd.testing.assert_frame_equal(actual, SnapshotHistory(prefix).labels_at(0))
    assert actual.iloc[0].target_absence_h2 == 0.5
    assert SnapshotHistory(full).labels_at(6).target_absence_h2.isna().all()
    assert SnapshotHistory(full).labels_at(7).target_absence_h2.isna().all()


def test_reappearance_diagnostic_does_not_turn_incomplete_followup_into_zero():
    history = SnapshotHistory(snapshots(presence=(0, 3), count=5))
    report = history.endpoint_reappearance_audit((20214, 20221))
    assert report[20214]["returned_share_pct"] == 100.0
    assert report[20221]["returned_share_pct"] is None
    assert not report[20221]["two_quarter_followup_complete"]


def test_moving_to_another_cell_is_not_citywide_disappearance():
    frame = snapshots(presence=(0, 2), count=3)
    frame.loc[(frame.store_id == "returning") & frame.quarter.eq(20222), "area"] = "나동"
    assert SnapshotHistory(frame).labels_at(0).iloc[0].target_absence_h2 == 0


def test_invalid_snapshot_keys_and_missing_quarter_are_rejected():
    frame = snapshots()
    with pytest.raises(ValueError, match="중복"):
        SnapshotHistory(pd.concat([frame, frame.iloc[:1]], ignore_index=True))
    with pytest.raises(ValueError, match="연속"):
        SnapshotHistory(frame[frame.quarter != 20221])


def test_reader_removes_retrospective_fills_before_using_observations(tmp_path):
    path = tmp_path / "panel.csv"
    pd.DataFrame({
        "상가업소번호": ["original", "future-fill"], "기준분기": ["2021Q4"] * 2,
        "행정동명": ["가동"] * 2, "상권업종중분류명": ["한식"] * 2,
        "is_filled": [0, 1], "label_h2": [1, 0], "지번주소": ["unused", "unused"],
    }).to_csv(path, index=False)
    frame, metadata = read_observed_rows(path)
    assert frame.store_id.tolist() == ["original"]
    assert set(frame.columns) == {"store_id", "quarter", "area", "industry"}
    assert metadata["removed_filled_rows"] == 1


def temporal_frame(quarters=(20224, 20234, 20243)):
    return pd.DataFrame({
        "quarter": quarters, "feature_cutoff_quarter": quarters,
        "target_quarter": [quarter_add(q, 2) for q in quarters],
        "label_available_quarter": [quarter_add(q, 2) for q in quarters],
        "split": ["train", "validation", "test"],
    })


def test_labels_must_mature_before_later_split_and_features_cannot_look_ahead():
    assert_temporal_contract(temporal_frame())
    with pytest.raises(ValueError, match="완성"):
        assert_temporal_contract(temporal_frame((20224, 20242, 20243)))
    frame = temporal_frame()
    frame.loc[0, "feature_cutoff_quarter"] = 20231
    with pytest.raises(ValueError, match="입력 시점"):
        assert_temporal_contract(frame)


def test_category_vocabulary_comes_only_from_training_data():
    frame = pd.DataFrame({"area": ["가동", "미래동"], "industry": ["한식", "새업종"],
                          "split": ["train", "test"]})
    encoded, levels = encode_categories(frame)
    assert levels == {"area": ["가동"], "industry": ["한식"]}
    assert encoded.loc[1, ["area", "industry"]].isna().all()


def test_bootstrap_keeps_areas_unknown_to_training_in_evaluation():
    frame = pd.DataFrame({
        "quarter": [PRIMARY_QUARTERS[0]] * 3 + [PRIMARY_QUARTERS[1]] * 3,
        "area": [np.nan] * 6, "area_cluster": ["새지역"] * 6,
        TARGET: [0.1, 0.2, 0.3] * 2,
        "baseline_prediction": [0.1, 0.2, 0.3] * 2,
        "history_prediction": [0.1, 0.2, 0.3] * 2,
    })
    result = clustered_bootstrap(frame, samples=5)
    assert result["samples_valid"] == 5
    assert result["ci95"]["spearman"] == [0.0, 0.0]


def test_gate_requires_both_primary_origins_and_uncertainty():
    base = {"test": {q: {"spearman": 0.1, "lift_top10pct": 1.0} for q in PRIMARY_QUARTERS},
            "primary_macro": {"mae_pp": 2.0}}
    added = {"test": {q: {"spearman": 0.2, "lift_top10pct": 1.2} for q in PRIMARY_QUARTERS},
             "primary_macro": {"mae_pp": 1.9}}
    intervals = {"ci95": {"spearman": [0.01, 0.2], "lift_top10pct": [0.01, 0.4]}}
    assert direction_gate(base, added, intervals)
    intervals["ci95"]["lift_top10pct"][0] = -0.01
    assert not direction_gate(base, added, intervals)
    intervals["ci95"]["lift_top10pct"][0] = 0.01
    added["test"][PRIMARY_QUARTERS[1]]["spearman"] = 0.0
    assert not direction_gate(base, added, intervals)


def test_ranking_metrics_keep_quantile_ties_visible():
    result = metrics([0.1, 0.2, 0.3], [0.1, 0.1, 0.1])
    assert result["top10_n"] == 3
    assert result["lift_top10pct"] == 1.0
