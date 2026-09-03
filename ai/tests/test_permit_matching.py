import numpy as np
import pandas as pd

from ai.permit_matching import (address_parts, aggregate_labels, label_links, link_candidates,
                                name_key, quarter_end)


def snapshot(**updates):
    row = dict(store_id="store-1", name="테스트카페", branch="", area="가상동", industry="비알코올 ",
               small_industry="카페", road="경기도 화성시 가상로 12", lot="경기도 화성시 가상동 5",
               floor="1", unit="101", quarter=20243)
    return row | updates


def permit(**updates):
    row = dict(permit_key="permit-1", permit_id="1", name="테스트카페", source="식품_휴게음식점_경기화성시.csv",
               road="경기도 화성시 동탄구 가상로 12, 1층 101호", lot="경기도 화성시 가상동 5",
               open_date=pd.Timestamp("2020-01-01"), close_date=pd.NaT, status="영업/정상", detail_status="영업",
               invalid_date=False, pause_start=pd.NaT, pause_end=pd.NaT, reopen_date=pd.NaT,
               followup_date=pd.Timestamp("2026-07-01"))
    return row | updates


def link(rows=None, permits=None):
    return link_candidates(pd.DataFrame(rows or [snapshot()]), pd.DataFrame(permits or [permit()]))[0]


def test_name_address_and_new_district():
    assert name_key("테스트 카페!") == "테스트카페"
    assert len(link()) == 1
    assert address_parts("경기도 화성시 동탄구 가상로 12, 지하1층 101호", "road") == (
        "경기도화성시가상로12", "b1", "101")


def test_same_building_different_business_not_linked():
    assert link(permits=[permit(name="다른가게")]).empty
    assert link(rows=[snapshot(name="", road="", lot="")]).empty
    assert link(permits=[permit(source="생활_미용업_경기화성시.csv")]).empty


def test_floor_and_unit_conflicts_rejected():
    assert link(rows=[snapshot(unit="102")]).empty
    assert link(rows=[snapshot(floor="2")]).empty
    assert link(rows=[snapshot(lot="경기도 화성시 가상동 6")]).empty


def test_branch_must_match():
    assert link(rows=[snapshot(branch="가상점")]).empty
    assert len(link(rows=[snapshot(branch="가상점")], permits=[permit(name="테스트카페 가상점")])) == 1


def test_multiple_permits_and_shared_permit_are_unknown():
    assert link(permits=[permit(), permit(permit_key="permit-2", permit_id="2")]).empty
    assert link(rows=[snapshot(), snapshot(store_id="store-2")]).empty


def test_business_must_operate_at_origin():
    assert link(permits=[permit(open_date=pd.Timestamp("2024-10-01"))]).empty
    assert link(permits=[permit(close_date=pd.Timestamp("2024-09-30"))]).empty


def test_label_boundaries_and_citywide_presence():
    p = permit(close_date=quarter_end(20251), status="폐업", detail_status="폐업")
    result = label_links(link(permits=[p]), {20251: {"store-1"}}).iloc[0]
    assert result.target_registry_h2 == 1 and result.target_absence_h2 == 0
    p["close_date"] += pd.Timedelta(days=1)
    assert label_links(link(permits=[p]), {20251: set()}).iloc[0].target_registry_h2 == 0


def test_missing_endpoint_not_imputed():
    result = label_links(link(), {}).iloc[0]
    assert result.label_status == "snapshot_endpoint_missing"
    assert np.isnan(result.target_absence_h2)


def test_uncertain_status_and_dates_not_imputed():
    for changes in [dict(status="휴업"), dict(reopen_date=pd.Timestamp("2024-01-01")),
                    dict(close_date=pd.Timestamp("2025-01-01")), dict(invalid_date=True),
                    dict(status="취소/말소/만료/정지/중지", detail_status="직권말소")]:
        result = label_links(link(permits=[permit(**changes)]), {20251: set()}).iloc[0]
        assert result.label_status == "status_or_dates_uncertain"
        assert np.isnan(result.target_registry_h2)


def test_followup_required_for_both_outcomes():
    for changes in [{}, dict(status="폐업", detail_status="폐업", close_date=pd.Timestamp("2025-01-01"))]:
        p = permit(followup_date=pd.Timestamp("2025-02-01"), **changes)
        result = label_links(link(permits=[p]), {20251: set()}).iloc[0]
        assert result.label_status == "followup_incomplete"
        assert np.isnan(result.target_registry_h2)


def test_paired_denominator_and_unknown_cell():
    links = link(rows=[snapshot(), snapshot(store_id="store-2", name="다른카페")],
                 permits=[permit(), permit(permit_key="permit-2", name="다른카페", status="휴업")])
    labels = label_links(links, {20251: set()})
    features = pd.DataFrame([dict(area="가상동", industry="비알코올 ", quarter=20243, store_count=2),
                             dict(area="나동", industry="한식", quarter=20243, store_count=50)])
    result = aggregate_labels(labels, features)
    assert result.iloc[0].matched_count == 1 and result.iloc[0].coverage == .5
    assert result.iloc[0].target_absence_h2 == 1 and result.iloc[0].target_registry_h2 == 0
    assert result.iloc[1].matched_count == 0 and np.isnan(result.iloc[1].target_registry_h2)


def test_future_snapshot_does_not_change_origin_links():
    before = link()
    after = link(rows=[snapshot(), snapshot(quarter=20251)])
    pd.testing.assert_frame_equal(before, after[after.quarter.eq(20243)].reset_index(drop=True))


def test_empty_links_keep_unknown_outcome_columns():
    labels = label_links(link(rows=[snapshot(name="미등록업체")]), {20251: set()})
    assert labels.empty
    assert {"target_registry_h2", "target_absence_h2", "label_status"}.issubset(labels.columns)
