from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import AdminArea, CommercialQuarter, IndustryCategory, ModelRun, RiskPrediction
from ..schemas import ClosureRiskItem, ClosureRateRankingItem, VacancyRiskItem
from ..services.risk import DANGER_THRESHOLD_PCT, action_message, dong_risk_level, risk_level

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
    q = (
        db.query(RiskPrediction, CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .join(CommercialQuarter, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            ModelRun.is_active.is_(True),
            RiskPrediction.sample_insufficient.is_(False),
            RiskPrediction.predicted_rank.isnot(None),
        )
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    rows = q.order_by(RiskPrediction.predicted_rank.asc()).limit(limit).all()

    result = []
    for prediction, commercial, dong, industry in rows:
        actual_pct = (commercial.closure_rate or 0.0) * 100
        level = risk_level(actual_pct)[0]
        result.append(ClosureRiskItem(
            predicted_rank=prediction.predicted_rank,
            dong=dong,
            category=industry,
            actual_closure_rate_pct=round(actual_pct, 2),
            growth_prob=round((1 - prediction.predicted_closure_rate_internal) * 100, 1),
            open_rate_pct=round((commercial.opening_rate or 0.0) * 100, 2),
            trend_slope=round(commercial.trend_slope or 0.0, 3),
            saturation=commercial.saturation_rate or 0.0,
            anomaly=commercial.anomaly_flag,
            action=action_message(level, commercial.anomaly_flag),
        ))
    return result


@router.get("/closure-rate-ranking", response_model=list[ClosureRateRankingItem])
def get_closure_rate_ranking(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """상권 순위표(현황) — 실제 관측 폐업률로만 정렬. 보정·예측 관여 없음."""
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return []

    q = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(CommercialQuarter.quarter_code == latest, CommercialQuarter.store_count >= 30)
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    rows = q.order_by(CommercialQuarter.closure_rate.desc()).limit(limit).all()

    return [
        ClosureRateRankingItem(
            rank=i,
            dong=dong,
            category=industry,
            closure_rate_pct=round((commercial.closure_rate or 0.0) * 100, 2),
            store_count=commercial.store_count,
        )
        for i, (commercial, dong, industry) in enumerate(rows, 1)
    ]


@router.get("/vacancy-risk/map", response_model=list[VacancyRiskItem])
def get_vacancy_risk_map(db: Session = Depends(get_db)):
    """지도(현황) — 읍면동별 위험 업종 비율(실제 폐업률 기준 셀 등급의 집계). 예측값 관여 없음."""
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return []

    rows = (
        db.query(
            AdminArea.area_name,
            CommercialQuarter.closure_rate,
            CommercialQuarter.trend_slope,
        )
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .filter(CommercialQuarter.quarter_code == latest, CommercialQuarter.store_count >= 30)
        .all()
    )

    grouped: dict[str, list[tuple[float, float]]] = {}
    for dong, closure_rate, trend_slope in rows:
        grouped.setdefault(dong, []).append(((closure_rate or 0.0) * 100, trend_slope or 0.0))

    result = []
    for dong, values in grouped.items():
        ratio = round(sum(rate >= DANGER_THRESHOLD_PCT for rate, _ in values) / len(values) * 100, 1)
        avg_slope = sum(slope for _, slope in values) / len(values)
        level, color = dong_risk_level(ratio)
        result.append(
            VacancyRiskItem(
                dong=dong,
                risk_ratio=ratio,
                risk_level=level,
                color=color,
                trend=round(avg_slope, 3),
            )
        )
    return sorted(result, key=lambda item: item.dong)
