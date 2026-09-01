from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import (
    AdminArea,
    CommercialQuarter,
    DataBatch,
    IndustryCategory,
)
from backend.models import AreaQuarterSummary, RiskThresholdSet, StoreCluster
from backend.services.operational_data import (
    batch_detail,
    current_data_summary,
    operational_batches,
    quarter_label_ko,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            AdminArea.__table__,
            IndustryCategory.__table__,
            DataBatch.__table__,
            CommercialQuarter.__table__,
            RiskThresholdSet.__table__,
            StoreCluster.__table__,
            AreaQuarterSummary.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _seed(session):
    batch = DataBatch(batch_key="summary-test", source_name="fixture", method_version="test")
    areas = [
        AdminArea(area_code=f"415900{index}", area_name=f"테스트{index}동", area_type="동")
        for index in range(1, 4)
    ]
    industries = [
        IndustryCategory(
            source_system="sbiz",
            industry_code=f"M00{index}",
            industry_name=f"업종{index}",
            level="medium",
        )
        for index in range(1, 3)
    ]
    session.add_all([batch, *areas, *industries])
    session.flush()

    def cell(area, industry, quarter, *, sufficient=True):
        return CommercialQuarter(
            area_id=area.id,
            industry_id=industry.id,
            quarter_code=quarter,
            store_count=40 if sufficient else 5,
            sample_insufficient=not sufficient,
            batch_id=batch.id,
        )

    # 20253: 동 2 x 업종 2 = 4셀, 20254: 동 3 x 업종 1 + 동 1 x 업종 2 = 4셀
    session.add_all([
        cell(areas[0], industries[0], 20253),
        cell(areas[0], industries[1], 20253),
        cell(areas[1], industries[0], 20253),
        cell(areas[1], industries[1], 20253),
        cell(areas[0], industries[0], 20254),
        cell(areas[1], industries[0], 20254),
        cell(areas[2], industries[0], 20254, sufficient=False),
        cell(areas[0], industries[1], 20254, sufficient=False),
    ])
    session.commit()


def test_quarter_label_ko_formats_and_rejects_bad_codes():
    assert quarter_label_ko(20254) == "2025년 4분기"
    assert quarter_label_ko(20261) == "2026년 1분기"
    assert quarter_label_ko(20255) is None
    assert quarter_label_ko(None) is None


def test_summary_counts_latest_quarter_only():
    session = _session()
    _seed(session)

    summary = current_data_summary(session)

    assert summary["latest_quarter_code"] == 20254
    assert summary["latest_quarter_label"] == "2025년 4분기"
    assert summary["quarter_count"] == 2
    assert summary["area_count"] == 3
    assert summary["industry_count"] == 2
    assert summary["analysis_cell_count"] == 4
    # 표본부족 2건은 총 레코드 수에는 들어가지만 표본충분 모수에서는 빠진다.
    assert summary["sample_sufficient_cell_count"] == 2


def test_summary_on_empty_database_returns_null_and_zeroes():
    session = _session()

    summary = current_data_summary(session)

    assert summary == {
        "latest_quarter_code": None,
        "latest_quarter_label": None,
        "quarter_count": 0,
        "area_count": 0,
        "industry_count": 0,
        "analysis_cell_count": 0,
        "sample_sufficient_cell_count": 0,
    }


def test_manual_upload_does_not_change_operational_summary(tmp_path):
    """업로드는 파일 시스템에만 쌓이므로 운영 집계가 움직이면 안 된다."""
    import csv
    from datetime import datetime, timezone

    from backend.services.manual_uploads import store_validated_upload

    session = _session()
    _seed(session)
    before = current_data_summary(session)

    temp_root = tmp_path / ".tmp"
    temp_root.mkdir()
    source = temp_root / "incoming"
    with source.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["STD_YM", "ADMDONG_CD", "MDCLASS_INDUTYPE_CD", "SALES_AMT"]
        )
        writer.writeheader()
        for index in range(1, 81):
            writer.writerow({
                "STD_YM": "202608",
                "ADMDONG_CD": "4159059000",
                "MDCLASS_INDUTYPE_CD": f"Q{index:02d}",
                "SALES_AMT": str(index * 1000),
            })

    store_validated_upload(
        "card_sales",
        "card_sales_hwaseong.csv",
        source,
        uploaded_by="official1",
        root=tmp_path,
        now=datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert current_data_summary(session) == before


def test_operational_batches_report_real_import_time_and_range():
    """이력표 시각은 화면을 여는 시각이 아니라 배치가 적재된 시각이어야 한다."""
    from datetime import datetime, timezone

    session = _session()
    imported = datetime(2026, 8, 24, 16, 32, tzinfo=timezone.utc)
    session.add_all([
        DataBatch(
            batch_key="sbiz-gapfill-t11-20254",
            source_name="소상공인시장진흥공단 분기 스냅샷",
            method_version="gapfill-t11-trailing-stats-v1",
            source_start_quarter=20181,
            source_end_quarter=20254,
            row_count=35513,
            quality_notes="2023Q1 원천 결함 보정",
            imported_at=imported,
        ),
        DataBatch(
            batch_key="older-batch",
            source_name="이전 스냅샷",
            method_version="v0",
            source_start_quarter=20181,
            source_end_quarter=20253,
            row_count=100,
            imported_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        ),
    ])
    session.commit()

    batches = operational_batches(session)

    assert [b["batch_key"] for b in batches] == ["sbiz-gapfill-t11-20254", "older-batch"]
    latest = batches[0]
    assert latest["imported_at"].startswith("2026-08-24T16:32")
    assert latest["quarter_start_label"] == "2018년 1분기"
    assert latest["quarter_end_label"] == "2025년 4분기"
    assert latest["row_count"] == 35513


def test_operational_batches_empty_when_nothing_imported():
    assert operational_batches(_session()) == []


def _seeded_batch(session):
    """_seed와 같은 셀 구성을 쓰되 배치 상세용 부속 행을 더 넣는다."""
    _seed(session)
    batch = session.query(DataBatch).one()
    session.add(
        RiskThresholdSet(
            batch_id=batch.id,
            quarter_code=20254,
            avg_closure_rate_pct=5.56,
            danger_threshold_pct=9.71,
            caution_threshold_pct=6.9,
            area_ratio_avg_pct=10.84,
            area_ratio_danger_pct=25.46,
            sample_min=30,
            window_quarters=4,
            method="cumulative_quantile",
        )
    )
    session.commit()
    return batch


def test_batch_detail_reports_thresholds_and_quarter_breakdown():
    session = _session()
    _seeded_batch(session)

    detail = batch_detail(session, "summary-test")

    assert detail["batch_key"] == "summary-test"
    assert detail["quarter_count"] == 2
    assert detail["latest_quarter_label"] == "2025년 4분기"
    assert detail["area_count"] == 3
    assert detail["industry_count"] == 2
    # 최신 분기가 먼저, 표본충분 수도 분기별로 갈린다.
    assert detail["quarters"][0]["quarter_code"] == 20254
    assert detail["quarters"][0]["cell_count"] == 4
    assert detail["quarters"][0]["sample_sufficient_cell_count"] == 2
    assert detail["quarters"][1]["cell_count"] == 4
    assert detail["thresholds"]["danger_threshold_pct"] == 9.71
    assert detail["thresholds"]["method"] == "cumulative_quantile"


def test_batch_detail_never_exposes_prediction_fields():
    session = _session()
    _seeded_batch(session)

    detail = batch_detail(session, "summary-test")

    blocked = {"predicted_closure_rate_internal", "predicted_rank", "grade", "top_percent"}
    assert blocked.isdisjoint(detail.keys())
    assert all(blocked.isdisjoint(quarter.keys()) for quarter in detail["quarters"])


def test_batch_detail_returns_none_for_unknown_key():
    assert batch_detail(_session(), "does-not-exist") is None
