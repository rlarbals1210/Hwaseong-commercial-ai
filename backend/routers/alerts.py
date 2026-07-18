from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, tuple_
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import ScoreData, CommercialData, RiskIndex
from ..schemas import ClosureRiskItem, VacancyRiskItem
from ..services.risk import action_message, risk_level

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_official)])


@router.get("/closure-risk", response_model=list[ClosureRiskItem])
def get_closure_risk(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    latest = db.query(func.max(RiskIndex.기준_년분기_코드)).scalar()
    if not latest:
        return []

    q = db.query(RiskIndex).filter(RiskIndex.기준_년분기_코드 == latest)
    if category:
        q = q.filter(RiskIndex.통합카테고리 == category)
    rows = q.order_by(RiskIndex.폐업위험점수.desc()).limit(limit).all()
    if not rows:
        return []

    pairs = [(r.행정동명, r.통합카테고리) for r in rows]

    all_scores = (
        db.query(ScoreData)
        .filter(tuple_(ScoreData.행정동명, ScoreData.통합카테고리).in_(pairs))
        .order_by(ScoreData.기준_년분기_코드.desc())
        .all()
    )
    score_map: dict = {}
    for s in all_scores:
        key = (s.행정동명, s.통합카테고리)
        if key not in score_map:
            score_map[key] = s

    all_comms = (
        db.query(CommercialData)
        .filter(
            tuple_(CommercialData.행정동명, CommercialData.통합카테고리).in_(pairs),
            CommercialData.기준_년분기_코드 == latest,
        )
        .all()
    )
    comm_map = {(c.행정동명, c.통합카테고리): c for c in all_comms}

    result = []
    for i, r in enumerate(rows, 1):
        key = (r.행정동명, r.통합카테고리)
        score_row = score_map.get(key)
        comm_row = comm_map.get(key)
        result.append(
            ClosureRiskItem(
                rank=i,
                dong=r.행정동명,
                category=r.통합카테고리,
                risk_score=round(r.폐업위험점수, 1),
                growth_prob=score_row.성장확률 if score_row else 0.0,
                closure_rate=comm_row.폐업_률_평균 if comm_row else 0.0,
                anomaly=r.이상탐지_플래그 or False,
                action=action_message(r.폐업위험점수, r.이상탐지_플래그 or False),
            )
        )
    return result


@router.get("/vacancy-risk/map", response_model=list[VacancyRiskItem])
def get_vacancy_risk_map(db: Session = Depends(get_db)):
    latest = db.query(func.max(RiskIndex.기준_년분기_코드)).scalar()
    if not latest:
        return []

    rows = (
        db.query(
            RiskIndex.행정동명,
            func.avg(RiskIndex.폐업위험점수).label("avg_risk"),
            func.avg(RiskIndex.트렌드_기울기).label("avg_slope"),
        )
        .filter(RiskIndex.기준_년분기_코드 == latest)
        .group_by(RiskIndex.행정동명)
        .all()
    )

    result = []
    for r in rows:
        score = r.avg_risk or 0.0
        level, color = risk_level(score)
        result.append(
            VacancyRiskItem(
                dong=r.행정동명,
                score=round(score, 1),
                risk_level=level,
                color=color,
                trend=round(r.avg_slope or 0.0, 3),
            )
        )
    return result
