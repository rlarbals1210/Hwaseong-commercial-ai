from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import AdminArea, CommercialQuarter, DataBatch, IndustryCategory
from backend.routers.trends import (
    area_trends,
    area_type_trends,
    cell_trend,
    dongtan_trends,
    industry_trends,
    overview,
)
from backend.services.risk import SAMPLE_MIN


def test_six_trend_views_use_corrected_opening_rate():
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
    session = sessionmaker(bind=engine)()
    batch = DataBatch(batch_key="trend-test", source_name="fixture", method_version="test")
    areas = [
        AdminArea(area_code="41590001", area_name="동탄1동", area_type="동"),
        AdminArea(area_code="41590002", area_name="봉담읍", area_type="읍"),
    ]
    industries = [
        IndustryCategory(source_system="sbiz", industry_code="M1", industry_name="한식", level="medium"),
        IndustryCategory(source_system="sbiz", industry_code="M2", industry_name="일식", level="medium"),
    ]
    session.add_all([batch, *areas, *industries])
    session.flush()

    for quarter, offset in [(20253, 0), (20254, 1)]:
        for area_index, area in enumerate(areas):
            for industry_index, industry in enumerate(industries):
                session.add(
                    CommercialQuarter(
                        area_id=area.id,
                        industry_id=industry.id,
                        quarter_code=quarter,
                        store_count=100,
                        opening_rate=0.99,
                        opening_rate_ma4=0.02 + 0.01 * (offset + area_index + industry_index),
                        closure_rate_cum4=0.03 + 0.01 * (offset + area_index + industry_index),
                        sample_insufficient=False,
                        batch_id=batch.id,
                    )
                )
    session.commit()

    city = overview(db=session)
    by_area = area_trends(industry_id=industries[0].id, db=session)
    by_industry = industry_trends(area_id=areas[0].id, db=session)
    cell = cell_trend(area_id=areas[0].id, industry_id=industries[0].id, db=session)
    area_types = area_type_trends(db=session)
    dongtan = dongtan_trends(db=session)

    assert city["series"][-1]["opening_rate_pct"] == 4.0
    assert city["series"][-1]["opening_rate_pct"] != 99.0
    assert f"점포 {SAMPLE_MIN}곳 이상" in city["method_notice"]
    assert len(by_area["results"]) == 2
    assert len(by_industry["results"]) == 2
    assert cell["series"][-1]["opening_rate_pct"] == 3.0
    assert {group["label"] for group in area_types["groups"]} == {"동", "읍"}
    assert {group["label"] for group in dongtan["groups"]} == {"동탄권", "비동탄권"}

    session.close()
    engine.dispose()
