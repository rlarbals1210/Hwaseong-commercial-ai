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


@router.get("/inspection-priority")
def get_inspection_priority(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """현장점검 우선순위 — 실제 관측 폐업률(x축) × 영향 점포 수(y축) 4사분면.

    이 API는 정책자금 배분 대상을 결정하지 않는다. 담당자가 '어디부터 현장을 확인할지'
    순서를 좁히는 보조 자료이며, 최종 판단과 지원 결정은 공무원이 한다.
    x축은 예측값이 아니라 실제 관측 폐업률(4분기 누적)이고, 표본부족 셀은 제외한다
    (기준은 risk_thresholds.json의 sample_min. 2026-08-29 현재 30).

    주의 — 사분면의 두 축은 기준이 다르다. y축(영향 점포 수)은 결과셋 내 중위값이고,
    x축은 중위값이 아니라 등급(위험 = 화성시 상위 10%)이다. 화면 문구도 그렇게 쓸 것.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return {
            "Q1": [], "Q2": [], "Q3": [], "Q4": [],
            "meta": {
                "danger_threshold_pct": DANGER_THRESHOLD_PCT,
                "median_store_count": None,
            },
        }

    # 표본부족 셀은 소표본 노이즈로 사분면 배정을 왜곡하므로 제외 (alerts.py와 동일 원칙)
    q = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.sample_insufficient.is_(False),
            # 누적값이 없는 셀(4분기 미충족)은 or 0.0을 타고 "0.0%"로 사분면에 들어간다.
            # 현재 데이터엔 해당 셀이 없지만 분기가 넘어가면 생길 수 있어 여기서 막는다.
            CommercialQuarter.closure_rate_cum4.isnot(None),
        )
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    risks = q.all()
    if not risks:
        return {
            "Q1": [], "Q2": [], "Q3": [], "Q4": [],
            "meta": {
                "danger_threshold_pct": DANGER_THRESHOLD_PCT,
                "median_store_count": None,
            },
        }

    # y축 = 영향 점포 수(파급 규모). 성장확률을 재사용하면 x축(위험도)과 자기모순적 음의 상관관계가
    # 생기므로, 결과셋 내 점포수 중위값 기준 상/하위 분류로 대체함.
    store_counts = [commercial.store_count for commercial, _, _ in risks]
    median_stores = statistics.median(store_counts) if store_counts else 0

    result: dict[str, list] = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    for commercial, dong, industry in risks:
        store_count = commercial.store_count
        # 4분기 누적을 쓴다. 단일 분기(closure_rate)를 쓰면 등급은 누적 기준인데 표시값만
        # 단일 분기가 되어 '위험 등급인데 폐업률 1.12%'가 화면에 뜬다(2026-08-25 감사:
        # 위험 24셀 중 19셀이 화성시 평균 5.9%보다 낮게 표시되고 있었다).
        # analysis.py는 같은 이유로 이미 누적으로 고쳐져 있었고 이 라우터만 남아 있었다.
        risk = (commercial.closure_rate_cum4 or 0.0) * 100

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
                area_id=commercial.area_id,
                industry_id=commercial.industry_id,
                dong=dong,
                category=industry,
                # 좌표형 사분면은 이 값을 실제 x좌표로 쓴다. 한 자리로 반올림하면 9.72%가
                # 9.7%가 되어 위험 기준선(9.71%) 왼쪽에 그려지는 모순이 생긴다.
                actual_closure_rate_pct=round(risk, 2),
                # 아래 세 개를 넘기지 않으면 스키마 기본값("안정" / None / 0)이 그대로 응답에
                # 실린다. 화면 배지가 안 뜨는 데서 그치지 않고, 내려받는 CSV의 등급 열이
                # 위험·주의 셀까지 전부 "안정"으로 찍혀 나갔다(2026-08-25 감사).
                risk_grade=commercial.risk_grade or "안정",
                cell_type=commercial.cell_type,
                cumulative_closure_count=commercial.closure_count_cum4 or 0,
                store_count=store_count,
                quadrant=quadrant,
                sample_insufficient=False,
            )
        )

    for key in result:
        result[key] = sorted(result[key], key=lambda x: x.actual_closure_rate_pct, reverse=True)

    return {
        **result,
        # 화면의 실제 좌표선이 서버의 판정선과 반드시 같아야 한다. 프론트에서 배열을 보고
        # 경계를 다시 추정하면 필터·동률 처리에 따라 점과 사분면 배경이 어긋난다.
        "meta": {
            "danger_threshold_pct": DANGER_THRESHOLD_PCT,
            "median_store_count": median_stores,
        },
    }
