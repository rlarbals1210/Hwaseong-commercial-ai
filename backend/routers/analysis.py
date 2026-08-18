from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..database import get_db
from ..models import AdminArea, CommercialQuarter, IndustryCategory, ModelRun, RiskPrediction
from ..schemas import AnalysisDongResponse, ScoreResponse
from ..services.risk import risk_level

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/dongs")
def list_dongs(db: Session = Depends(get_db)):
    dongs = (
        db.query(AdminArea.area_name)
        .join(CommercialQuarter, CommercialQuarter.area_id == AdminArea.id)
        .filter(AdminArea.is_current.is_(True))
        .distinct()
        .order_by(AdminArea.area_name)
        .all()
    )
    return {"dongs": [d[0] for d in dongs]}


@router.get("/dong", response_model=AnalysisDongResponse)
def get_dong_analysis(
    dong: str = Query(...),
    category: Optional[str] = Query(None),
    quarter: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(AdminArea.area_name == dong)
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    if quarter:
        q = q.filter(CommercialQuarter.quarter_code == quarter)
    else:
        latest = (
            db.query(func.max(CommercialQuarter.quarter_code))
            .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
            .filter(AdminArea.area_name == dong)
            .scalar()
        )
        q = q.filter(CommercialQuarter.quarter_code == latest)

    result = q.order_by(IndustryCategory.industry_name).first()
    if not result:
        raise HTTPException(status_code=404, detail="데이터 없음")
    row, area_name, industry_name = result

    return AnalysisDongResponse(
        dong=area_name,
        category=industry_name,
        quarter=row.quarter_code,
        sales=None,
        store_count=row.store_count,
        population=None,
        closure_rate=row.closure_rate,
        open_rate=row.opening_rate,
        saturation=row.saturation_rate,
        competition=row.competition_index,
    )


@router.get("/score", response_model=ScoreResponse)
def get_score(
    dong: str = Query(...),
    category: str = Query(...),
    db: Session = Depends(get_db),
):
    result = (
        db.query(RiskPrediction, CommercialQuarter)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .join(CommercialQuarter, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            ModelRun.is_active.is_(True),
            AdminArea.area_name == dong,
            IndustryCategory.industry_name == category,
        )
        .order_by(ModelRun.created_at.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="점수 데이터 없음")
    prediction, commercial = result

    actual_rate = (commercial.closure_rate or 0.0) * 100
    sample_insufficient = prediction.sample_insufficient
    level = "표본부족" if sample_insufficient else risk_level(actual_rate)[0]

    return ScoreResponse(
        dong=dong,
        category=category,
        growth_prob=round((1 - prediction.predicted_closure_rate_internal) * 100, 1),
        grade=prediction.grade,
        rank=prediction.industry_rank,
        total_dongs=prediction.industry_total_areas,
        top_pct=prediction.top_percent,
        actual_closure_rate_pct=round(actual_rate, 1),
        risk_level=level,
        predicted_rank=prediction.predicted_rank,
        sample_insufficient=sample_insufficient,
    )


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = (
        db.query(IndustryCategory.industry_name)
        .join(CommercialQuarter, CommercialQuarter.industry_id == IndustryCategory.id)
        .distinct()
        .order_by(IndustryCategory.industry_name)
        .all()
    )
    return {"categories": [c[0] for c in cats]}


@router.get("/quarters")
def list_quarters(dong: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(CommercialQuarter.quarter_code).join(
        AdminArea, CommercialQuarter.area_id == AdminArea.id
    ).distinct()
    if dong:
        q = q.filter(AdminArea.area_name == dong)
    quarters = sorted([r[0] for r in q.all()], reverse=True)
    return {"quarters": quarters}
