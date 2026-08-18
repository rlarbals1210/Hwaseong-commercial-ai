from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    AreaQuarterSummary,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    PredictionContribution,
    RiskPrediction,
)
from ..schemas import (
    ClosureRiskItem,
    ClosureRateRankingItem,
    PredictionExplanationResponse,
    VacancyRiskItem,
)
from ..services.explain import EXPLANATION_NOTICE
from ..services.risk import action_message

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
            CommercialQuarter.sample_insufficient.is_(False),
            RiskPrediction.predicted_rank.isnot(None),
        )
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    rows = q.order_by(RiskPrediction.predicted_rank.asc()).limit(limit).all()

    result = []
    for prediction, commercial, dong, industry in rows:
        actual_pct = (commercial.closure_rate or 0.0) * 100
        level = commercial.risk_grade or "안정"
        result.append(ClosureRiskItem(
            prediction_id=prediction.id,
            predicted_rank=prediction.predicted_rank,
            dong=dong,
            category=industry,
            actual_closure_rate_pct=round(actual_pct, 2),
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
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.sample_insufficient.is_(False),
        )
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
    """지도(현황) — 저장된 동×분기 집계를 조회한다. 예측값 관여 없음."""
    latest = db.query(func.max(AreaQuarterSummary.quarter_code)).scalar()
    if not latest:
        return []

    rows = (
        db.query(
            AreaQuarterSummary,
            AdminArea.area_name,
        )
        .join(AdminArea, AreaQuarterSummary.area_id == AdminArea.id)
        .filter(AreaQuarterSummary.quarter_code == latest)
        .all()
    )

    colors = {"안정": "#10B981", "주의": "#F59E0B", "위험": "#D51B4C"}
    result = [
            VacancyRiskItem(
                dong=dong,
                risk_ratio=summary.risk_industry_ratio_pct,
                risk_level=summary.area_risk_grade or "안정",
                color=colors.get(summary.area_risk_grade, "#10B981"),
                trend=round(summary.avg_trend_slope or 0.0, 3),
                total_cells=summary.total_cells,
                sample_sufficient_cells=summary.sample_sufficient_cells,
                coverage_pct=round(
                    summary.sample_sufficient_cells / summary.total_cells * 100, 1
                ) if summary.total_cells else 0.0,
            )
            for summary, dong in rows
        ]
    return sorted(result, key=lambda item: item.dong)


@router.get(
    "/{prediction_id}/contributions",
    response_model=PredictionExplanationResponse,
)
def get_prediction_contributions(
    prediction_id: int,
    db: Session = Depends(get_db),
):
    prediction = db.get(RiskPrediction, prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="예측 결과가 없습니다")
    rows = (
        db.query(PredictionContribution)
        .filter(PredictionContribution.prediction_id == prediction_id)
        .order_by(PredictionContribution.rank)
        .all()
    )
    return PredictionExplanationResponse(
        notice=EXPLANATION_NOTICE,
        contributions=rows,
    )
