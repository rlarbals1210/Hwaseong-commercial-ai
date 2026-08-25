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
    x축은 예측값이 아니라 실제 관측 폐업률이고, 표본부족 셀은 제외한다.

    2026-08-20: x축을 단일 분기에서 4분기 누적으로 바꿨다. 등급(risk_grade)은 이미 누적
    기준인데 x축만 단일 분기라 사분면 분류가 두 기준을 섞어 쓰고 있었다. 같은 상권이
    조기경보에서는 6.2%, 여기서는 1.5%로 보이는 상태이기도 했다.
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
            CommercialQuarter.closure_rate_cum4.isnot(None),
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

    # x축 기준을 등급이 아니라 누적 폐업률 중위값으로 잡는다.
    # 이전에는 high_risk = (risk_grade == "위험")이었는데, 등급은 위험/주의/안정 3단계인 반면
    # 사분면은 2단계라 "주의" 등급이 통째로 하위 사분면(Q3/Q4)으로 떨어졌다.
    # Q4 설명이 "안정적 상권"이라 조기경보에서 주의로 뜬 상권이 여기서는 안전해 보이는
    # 모순이 실제로 발생했다(동탄9동 한식).
    # 중위값 기준으로 바꾸면 위험(상위 10%)·주의(상위 30%) 등급은 반드시 중위값 위에 있으므로
    # 항상 Q1 또는 Q2로 간다. 사분면 본래 의미(연속 변수 두 개를 중위값으로 자르기)와도 맞다.
    rates = [(commercial.closure_rate_cum4 or 0.0) * 100 for commercial, _, _ in risks]
    median_rate = statistics.median(rates) if rates else 0.0

    result: dict[str, list] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for commercial, dong, industry in risks:
        store_count = commercial.store_count
        risk = (commercial.closure_rate_cum4 or 0.0) * 100

        high_risk = risk >= median_rate
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
                cumulative_closure_count=commercial.closure_count_cum4 or 0,
                cell_type=commercial.cell_type,
                risk_grade=commercial.risk_grade or "안정",
                store_count=store_count,
                quadrant=quadrant,
                sample_insufficient=False,
            )
        )

    for key in result:
        result[key] = sorted(result[key], key=lambda x: x.actual_closure_rate_pct, reverse=True)

    return result
