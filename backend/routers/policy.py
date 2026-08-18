import statistics

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import AdminArea, CommercialQuarter, IndustryCategory
from ..schemas import PolicyPriorityItem

router = APIRouter(prefix="/api/policy", tags=["policy"], dependencies=[Depends(get_current_official)])


@router.get("/inspection-priority")
def get_inspection_priority(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """현장점검 우선순위 — 실제 관측 폐업률(x축) × 영향 점포 수(y축) 4사분면.

    이 API는 정책자금 배분 대상을 결정하지 않는다. 담당자가 '어디부터 현장을 확인할지'
    순서를 좁히는 보조 자료이며, 최종 판단과 지원 결정은 공무원이 한다.
    x축은 예측값이 아니라 실제 관측 폐업률이고, 표본부족(점포수<30) 셀은 제외한다.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    # 표본부족(점포수<30) 셀은 소표본 노이즈로 사분면 배정을 왜곡하므로 제외 (alerts.py와 동일 원칙)
    q = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.sample_insufficient.is_(False),
        )
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    risks = q.all()
    if not risks:
        return {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    # y축 = 영향 점포 수(파급 규모). 성장확률을 재사용하면 x축(위험도)과 자기모순적 음의 상관관계가
    # 생기므로, 결과셋 내 점포수 중위값 기준 상/하위 분류로 대체함.
    store_counts = [commercial.store_count for commercial, _, _ in risks]
    median_stores = statistics.median(store_counts) if store_counts else 0

    result: dict[str, list] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for commercial, dong, industry in risks:
        store_count = commercial.store_count
        risk = (commercial.closure_rate or 0.0) * 100

        high_risk = commercial.risk_grade == "위험"
        high_impact = store_count >= median_stores
        if high_risk and high_impact:
            quadrant = 1
        elif high_risk:
            quadrant = 2
        elif high_impact:
            quadrant = 3
        else:
            quadrant = 4

        result[f"Q{quadrant}"].append(
            PolicyPriorityItem(
                dong=dong,
                category=industry,
                actual_closure_rate_pct=round(risk, 1),
                store_count=store_count,
                quadrant=quadrant,
                sample_insufficient=False,
            )
        )

    for key in result:
        result[key] = sorted(result[key], key=lambda x: x.actual_closure_rate_pct, reverse=True)

    return result
