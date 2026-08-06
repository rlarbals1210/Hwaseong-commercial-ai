from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import RiskIndex
from ..schemas import ClosureRiskItem, ClosureRateRankingItem, VacancyRiskItem
from ..services.risk import action_message, dong_risk_level

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_official)])


@router.get("/closure-risk", response_model=list[ClosureRiskItem])
def get_closure_risk(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """조기경보(예측) — AI 예측 폐업률로 셀 순위만 매긴다. 예측 절대값은 응답에 없음
    (예측폐업률이 실제 관측치보다 구조적으로 ~2.4배 높게 나오는 게 확인되어, 화면에 노출하면
    오해를 줌 — 순위만 신뢰할 수 있는 정보). 실제 관측 폐업률·개업률·추세는 팩트로 그대로 병기."""
    latest = db.query(func.max(RiskIndex.기준_년분기_코드)).scalar()
    if not latest:
        return []

    # 표본부족(점포수<30) 셀은 예측순위 산정에서 이미 제외됨(build_risk_index.py) — NULL 방어차 재확인
    q = db.query(RiskIndex).filter(
        RiskIndex.기준_년분기_코드 == latest,
        RiskIndex.표본부족_플래그.is_(False),
        RiskIndex.예측순위.isnot(None),
    )
    if category:
        q = q.filter(RiskIndex.통합카테고리 == category)
    rows = q.order_by(RiskIndex.예측순위.asc()).limit(limit).all()

    return [
        ClosureRiskItem(
            predicted_rank=r.예측순위,
            dong=r.행정동명,
            category=r.통합카테고리,
            actual_closure_rate_pct=r.실제폐업률_pct,
            growth_prob=r.성장확률,
            open_rate_pct=r.개업률_pct,
            trend_slope=round(r.트렌드_기울기 or 0.0, 3),
            saturation=r.업종_포화도,
            anomaly=r.이상탐지_플래그 or False,
            action=action_message(r.위험등급, r.이상탐지_플래그 or False),
        )
        for r in rows
    ]


@router.get("/closure-rate-ranking", response_model=list[ClosureRateRankingItem])
def get_closure_rate_ranking(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """상권 순위표(현황) — 실제 관측 폐업률로만 정렬. 보정·예측 관여 없음."""
    latest = db.query(func.max(RiskIndex.기준_년분기_코드)).scalar()
    if not latest:
        return []

    q = db.query(RiskIndex).filter(
        RiskIndex.기준_년분기_코드 == latest,
        RiskIndex.표본부족_플래그.is_(False),
    )
    if category:
        q = q.filter(RiskIndex.통합카테고리 == category)
    rows = q.order_by(RiskIndex.실제폐업률_pct.desc()).limit(limit).all()

    return [
        ClosureRateRankingItem(
            rank=i,
            dong=r.행정동명,
            category=r.통합카테고리,
            closure_rate_pct=r.실제폐업률_pct,
            store_count=r.점포수,
        )
        for i, r in enumerate(rows, 1)
    ]


@router.get("/vacancy-risk/map", response_model=list[VacancyRiskItem])
def get_vacancy_risk_map(db: Session = Depends(get_db)):
    """지도(현황) — 읍면동별 위험 업종 비율(실제 폐업률 기준 셀 등급의 집계). 예측값 관여 없음."""
    latest = db.query(func.max(RiskIndex.기준_년분기_코드)).scalar()
    if not latest:
        return []

    # 위험업종비율은 build_risk_index.py가 동단위로 미리 계산해 각 셀에 동일값을 채워둔 필드라
    # 동별 아무 값이나 하나(min/max/avg 무관하게 동일)만 집계하면 된다. 트렌드는 표본부족 셀의
    # 노이즈를 배제하기 위해 표본충분 셀만으로 평균낸다.
    rows = (
        db.query(
            RiskIndex.행정동명,
            func.avg(RiskIndex.위험업종비율).label("risk_ratio"),
            func.avg(RiskIndex.트렌드_기울기).label("avg_slope"),
        )
        .filter(RiskIndex.기준_년분기_코드 == latest, RiskIndex.표본부족_플래그.is_(False))
        .group_by(RiskIndex.행정동명)
        .all()
    )

    result = []
    for r in rows:
        ratio = r.risk_ratio or 0.0
        level, color = dong_risk_level(ratio)
        result.append(
            VacancyRiskItem(
                dong=r.행정동명,
                risk_ratio=round(ratio, 1),
                risk_level=level,
                color=color,
                trend=round(r.avg_slope or 0.0, 3),
            )
        )
    return result
