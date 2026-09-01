from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import (
    AdminArea,
    CommercialQuarter,
    DataBatch,
    IndustryCategory,
)
from backend.services.operational_data import current_data_summary, quarter_label_ko


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            AdminArea.__table__,
            IndustryCategory.__table__,
            DataBatch.__table__,
            CommercialQuarter.__table__,
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

    def cell(area, industry, quarter):
        return CommercialQuarter(
            area_id=area.id,
            industry_id=industry.id,
            quarter_code=quarter,
            store_count=10,
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
        cell(areas[2], industries[0], 20254),
        cell(areas[0], industries[1], 20254),
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
