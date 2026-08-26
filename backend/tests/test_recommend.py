from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import (
    AdminArea,
    CommercialQuarter,
    DataBatch,
    IndustryCategory,
    ModelRun,
    RiskPrediction,
    StoreCluster,
)
from backend.routers.recommend import (
    recommend_areas,
    recommend_industries,
    recommend_score,
    store_clusters,
)
from backend.services.recommend import Candidate, score_candidates


def test_balanced_preset_scores_and_narrow_spread():
    candidates = [
        Candidate(1, "가동", 1, "한식", 80.0, 100, 0.4, 2.0, 2, 3.0, 20.0, None),
        Candidate(2, "나동", 1, "한식", 81.0, 50, 0.2, 3.0, 3, 4.0, 30.0, None),
        Candidate(3, "다동", 1, "한식", 82.0, 20, 0.1, 4.0, 4, 5.0, 40.0, None),
    ]

    meta = score_candidates(candidates, "균형")

    assert meta["growth_spread"] == 2.0
    assert meta["growth_spread_narrow"] is True
    assert [candidate.rank for candidate in candidates] == [3, 2, 1]
    assert candidates[-1].grade == "B"  # 3개 모집단의 1위는 상위 33.3%


def test_public_recommendation_never_returns_absolute_prediction():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            AdminArea.__table__,
            IndustryCategory.__table__,
            DataBatch.__table__,
            CommercialQuarter.__table__,
            ModelRun.__table__,
            RiskPrediction.__table__,
            StoreCluster.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    batch = DataBatch(batch_key="recommend-test", source_name="fixture", method_version="test")
    industry = IndustryCategory(
        source_system="sbiz", industry_code="M001", industry_name="한식", level="medium"
    )
    areas = [
        AdminArea(area_code=f"4159000{i}", area_name=f"테스트{i}동", area_type="동")
        for i in range(1, 5)
    ]
    run = ModelRun(
        run_key="recommend-test-run",
        model_name="fixture",
        model_version="test",
        observation_quarter=20254,
        is_active=True,
    )
    session.add_all([batch, industry, run, *areas])
    session.flush()
    session.add_all([
        StoreCluster(
            industry_id=industry.id,
            quarter_code=20254,
            grid_x=63500,
            grid_y=18600,
            center_lng=127.001,
            center_lat=37.201,
            store_count=3,
            batch_id=batch.id,
        ),
        StoreCluster(
            industry_id=industry.id,
            quarter_code=20254,
            grid_x=63501,
            grid_y=18600,
            center_lng=127.003,
            center_lat=37.201,
            store_count=1,
            batch_id=batch.id,
        ),
    ])

    for index, area in enumerate(areas, start=1):
        cell = CommercialQuarter(
            area_id=area.id,
            industry_id=industry.id,
            quarter_code=20254,
            store_count=50 + index * 10,
            saturation_rate=0.1 * index,
            closure_rate_cum4=0.01 * index,
            closure_count_cum4=index,
            opening_rate_ma4=0.02 * index,
            sample_insufficient=False,
            batch_id=batch.id,
        )
        session.add(cell)
        session.flush()
        session.add(
            RiskPrediction(
                model_run_id=run.id,
                commercial_quarter_id=cell.id,
                target_quarter_code=20262,
                predicted_closure_rate_internal=0.1 + index * 0.01,
                predicted_rank=index,
                grade="A",
                sample_insufficient=False,
            )
        )
    session.commit()

    payload = recommend_areas(industry_id=industry.id, preset="균형", limit=4, db=session)
    detail = recommend_score(
        area_id=payload["results"][0]["area_id"],
        industry_id=industry.id,
        preset="균형",
        db=session,
    )

    assert all("growth_prob" not in row for row in payload["results"])
    assert "growth_prob" not in detail
    assert payload["results"][0]["score"] == detail["score"]
    assert payload["results"][0]["grade"] == detail["grade"]
    by_industry = recommend_industries(
        area_id=payload["results"][0]["area_id"], preset="균형", limit=5, db=session
    )
    assert by_industry["results"][0]["score"] == detail["score"]
    assert "grade" not in by_industry["results"][0]
    clusters = store_clusters(industry_id=industry.id, limit=100, db=session)
    assert clusters["clusters"] == [{"lat": 37.201, "lng": 127.001, "store_count": 3}]
    assert clusters["suppressed_store_count"] == 1

    session.close()
    engine.dispose()
