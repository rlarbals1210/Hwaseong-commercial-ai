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
)
from backend.routers.analysis import list_categories


def test_category_filters_match_each_page_eligibility():
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
        ],
    )
    session = sessionmaker(bind=engine)()

    area = AdminArea(area_code="41590001", area_name="테스트동", area_type="동")
    categories = {
        name: IndustryCategory(
            source_system="sbiz",
            industry_code=f"I{index}",
            industry_name=name,
            level="medium",
        )
        for index, name in enumerate(["경보가능", "정책만가능", "표본부족"], 1)
    }
    batch = DataBatch(
        batch_key="test-batch",
        source_name="fixture",
        method_version="test",
    )
    session.add_all([area, *categories.values(), batch])
    session.flush()

    facts = {
        "경보가능": CommercialQuarter(
            area_id=area.id,
            industry_id=categories["경보가능"].id,
            quarter_code=20254,
            store_count=40,
            sample_insufficient=False,
            batch_id=batch.id,
        ),
        "정책만가능": CommercialQuarter(
            area_id=area.id,
            industry_id=categories["정책만가능"].id,
            quarter_code=20254,
            store_count=35,
            sample_insufficient=False,
            batch_id=batch.id,
        ),
        "표본부족": CommercialQuarter(
            area_id=area.id,
            industry_id=categories["표본부족"].id,
            quarter_code=20254,
            store_count=10,
            sample_insufficient=True,
            batch_id=batch.id,
        ),
    }
    run = ModelRun(
        run_key="test-run",
        model_name="fixture",
        model_version="test",
        observation_quarter=20254,
        is_active=True,
    )
    session.add_all([*facts.values(), run])
    session.flush()
    session.add_all([
        RiskPrediction(
            model_run_id=run.id,
            commercial_quarter_id=facts["경보가능"].id,
            target_quarter_code=20262,
            predicted_closure_rate_internal=0.1,
            predicted_rank=1,
            grade="A",
            sample_insufficient=False,
        ),
        RiskPrediction(
            model_run_id=run.id,
            commercial_quarter_id=facts["표본부족"].id,
            target_quarter_code=20262,
            predicted_closure_rate_internal=0.2,
            predicted_rank=None,
            grade="D",
            sample_insufficient=True,
        ),
    ])
    session.commit()

    assert list_categories(purpose=None, db=session) == {
        "categories": ["경보가능", "정책만가능", "표본부족"]
    }
    assert list_categories(purpose="alert", db=session) == {"categories": ["경보가능"]}
    assert list_categories(purpose="policy", db=session) == {
        "categories": ["경보가능", "정책만가능"]
    }

    session.close()
    engine.dispose()
