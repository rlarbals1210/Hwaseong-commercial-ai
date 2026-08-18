import statistics

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import AdminArea, CommercialQuarter, IndustryCategory
from ..schemas import PolicyPriorityItem
from ..services.risk import DANGER_THRESHOLD_PCT

router = APIRouter(prefix="/api/policy", tags=["policy"], dependencies=[Depends(get_current_official)])


@router.get("/fund-priority")
def get_fund_priority(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """폐업위험도(x축, 실제 관측 폐업률) × 정책잠재력(y축, 점포수) 4사분면."""
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    # 표본부족(점포수<30) 셀은 소표본 노이즈로 사분면 배정을 왜곡하므로 제외 (alerts.py와 동일 원칙)
    q = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(CommercialQuarter.quarter_code == latest, CommercialQuarter.store_count >= 30)
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    risks = q.all()
    if not risks:
        return {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    # 정책잠재력(y축) = 점포수(수혜규모). 성장확률 재사용 시 x축(위험도)과 자기모순적 음의 상관관계가
    # 생겨 결과셋 내 점포수 중위값 기준 상/하위 분류로 대체함.
    store_counts = [commercial.store_count for commercial, _, _ in risks]
    median_stores = statistics.median(store_counts) if store_counts else 0

    result: dict[str, list] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for commercial, dong, industry in risks:
        benefit_scale = commercial.store_count
        risk = (commercial.closure_rate or 0.0) * 100

        high_risk = risk >= DANGER_THRESHOLD_PCT
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
                dong=dong,
                category=industry,
                actual_closure_rate_pct=round(risk, 1),
                growth_prob=benefit_scale,
                quadrant=quadrant,
                sample_insufficient=False,
            )
        )

    for key in result:
        result[key] = sorted(result[key], key=lambda x: x.actual_closure_rate_pct, reverse=True)

    return result
