from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..database import get_db
from ..models import CommercialData, ScoreData, RiskIndex
from ..schemas import AnalysisDongResponse, ScoreResponse
from ..services.risk import risk_level

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/dongs")
def list_dongs(db: Session = Depends(get_db)):
    dongs = db.query(CommercialData.행정동명).distinct().order_by(CommercialData.행정동명).all()
    return {"dongs": [d[0] for d in dongs]}


@router.get("/dong", response_model=AnalysisDongResponse)
def get_dong_analysis(
    dong: str = Query(...),
    category: Optional[str] = Query(None),
    quarter: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(CommercialData).filter(CommercialData.행정동명 == dong)
    if category:
        q = q.filter(CommercialData.통합카테고리 == category)
    if quarter:
        q = q.filter(CommercialData.기준_년분기_코드 == quarter)
    else:
        latest = db.query(func.max(CommercialData.기준_년분기_코드)).filter(CommercialData.행정동명 == dong).scalar()
        q = q.filter(CommercialData.기준_년분기_코드 == latest)

    row = q.first()
    if not row:
        raise HTTPException(status_code=404, detail="데이터 없음")

    return AnalysisDongResponse(
        dong=row.행정동명,
        category=row.통합카테고리,
        quarter=row.기준_년분기_코드,
        sales=row.당월매출합,
        store_count=row.점포수,
        population=row.총_유동인구_수,
        closure_rate=row.폐업_률_평균,
        open_rate=row.개업_율_평균,
        saturation=row.업종_포화도,
        competition=row.경쟁강도,
    )


@router.get("/score", response_model=ScoreResponse)
def get_score(
    dong: str = Query(...),
    category: str = Query(...),
    db: Session = Depends(get_db),
):
    score_row = (
        db.query(ScoreData)
        .filter(ScoreData.행정동명 == dong, ScoreData.통합카테고리 == category)
        .order_by(ScoreData.기준_년분기_코드.desc())
        .first()
    )
    if not score_row:
        raise HTTPException(status_code=404, detail="점수 데이터 없음")

    risk_row = (
        db.query(RiskIndex)
        .filter(RiskIndex.행정동명 == dong, RiskIndex.통합카테고리 == category)
        .order_by(RiskIndex.기준_년분기_코드.desc())
        .first()
    )
    actual_rate = risk_row.실제폐업률_pct if risk_row else 0.0
    sample_insufficient = bool(risk_row.표본부족_플래그) if risk_row else False
    if risk_row and risk_row.위험등급:
        level = risk_row.위험등급
    else:
        level, _ = risk_level(actual_rate)

    return ScoreResponse(
        dong=dong,
        category=category,
        growth_prob=score_row.성장확률,
        grade=score_row.등급,
        rank=score_row.업종내_순위,
        total_dongs=score_row.업종내_전체동수,
        top_pct=score_row.상위_퍼센트,
        actual_closure_rate_pct=round(actual_rate, 1),
        risk_level=level,
        predicted_rank=risk_row.예측순위 if risk_row else None,
        sample_insufficient=sample_insufficient,
    )


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(CommercialData.통합카테고리).distinct().order_by(CommercialData.통합카테고리).all()
    return {"categories": [c[0] for c in cats]}


@router.get("/quarters")
def list_quarters(dong: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(CommercialData.기준_년분기_코드).distinct()
    if dong:
        q = q.filter(CommercialData.행정동명 == dong)
    quarters = sorted([r[0] for r in q.all()], reverse=True)
    return {"quarters": quarters}
