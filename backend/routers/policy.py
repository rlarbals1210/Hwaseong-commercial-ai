import statistics

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, tuple_
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import CommercialData, RiskIndex, ScoreData
from ..schemas import PolicyPriorityItem

router = APIRouter(prefix="/api/policy", tags=["policy"], dependencies=[Depends(get_current_official)])


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

    all_comms = (
        db.query(CommercialData)
        .filter(tuple_(CommercialData.행정동명, CommercialData.통합카테고리).in_(pairs))
        .order_by(CommercialData.기준_년분기_코드.desc())
        .all()
    )
    commercial_map: dict = {}
    for c in all_comms:
        key = (c.행정동명, c.통합카테고리)
        if key not in commercial_map:
            commercial_map[key] = c

    # 정책잠재력(y축) = 점포수(수혜규모). 성장확률 재사용 시 x축(폐업위험점수, 성장확률 60% 반영)과
    # 자기모순적 음의 상관관계가 생겨 결과셋 내 점포수 중위값 기준 상/하위 분류로 대체함.
    store_counts = [c.점포수 or 0 for c in commercial_map.values()]
    median_stores = statistics.median(store_counts) if store_counts else 0

    result: dict[str, list] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for r in risks:
        key = (r.행정동명, r.통합카테고리)
        comm_row = commercial_map.get(key)
        benefit_scale = comm_row.점포수 if comm_row and comm_row.점포수 else 0
        risk = r.폐업위험점수

        high_risk = risk >= 50
        high_growth = benefit_scale >= median_stores
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
                growth_prob=benefit_scale,
                quadrant=quadrant,
            )
        )

    for key in result:
        result[key] = sorted(result[key], key=lambda x: x.risk_score, reverse=True)

    return result
