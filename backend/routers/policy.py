from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, tuple_
from typing import Optional
from ..database import get_db
from ..models import RiskIndex, ScoreData
from ..schemas import PolicyPriorityItem

router = APIRouter(prefix="/api/policy", tags=["policy"])


@router.get("/fund-priority")
def get_fund_priority(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    latest = db.query(func.max(RiskIndex.기준_년분기_코드)).scalar()
    if not latest:
        return {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    q = db.query(RiskIndex).filter(RiskIndex.기준_년분기_코드 == latest)
    if category:
        q = q.filter(RiskIndex.통합카테고리 == category)
    risks = q.all()
    if not risks:
        return {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    pairs = [(r.행정동명, r.통합카테고리) for r in risks]

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

    result: dict[str, list] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for r in risks:
        key = (r.행정동명, r.통합카테고리)
        score_row = score_map.get(key)
        growth = score_row.성장확률 if score_row else 50.0
        risk = r.폐업위험점수

        high_risk = risk >= 50
        high_growth = growth >= 50
        if high_risk and high_growth:
            quadrant = 1
        elif high_risk:
            quadrant = 2
        elif high_growth:
            quadrant = 3
        else:
            quadrant = 4

        result[f"Q{quadrant}"].append(
            PolicyPriorityItem(
                dong=r.행정동명,
                category=r.통합카테고리,
                risk_score=round(risk, 1),
                growth_prob=round(growth, 1),
                quadrant=quadrant,
            )
        )

    for key in result:
        result[key] = sorted(result[key], key=lambda x: x.risk_score, reverse=True)

    return result
