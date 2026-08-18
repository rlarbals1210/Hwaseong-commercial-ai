from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AlertCase,
    AlertEvidence,
    CommercialQuarter,
    PolicyAction,
    PolicyOutcome,
    PolicyProgram,
    RiskPrediction,
)
from ..schemas import (
    AlertCaseResponse,
    AlertCaseUpdate,
    AlertEvidenceCreate,
    AlertEvidenceResponse,
    PolicyActionCreate,
    PolicyActionResponse,
    PolicyOutcomeCreate,
    PolicyOutcomeResponse,
    PolicyProgramResponse,
)
from ..services.risk import AVG_CLOSURE_RATE_PCT


router = APIRouter(prefix="/api/workflow", tags=["workflow"])
ALERT_STATUSES = {"new", "reviewing", "confirmed", "dismissed", "actioned", "closed"}
EVIDENCE_TYPES = {
    "OBSERVED_SIGNAL",
    "MODEL_CONTRIBUTION",
    "CONTEXT_INDICATOR",
    "OFFICIAL_CONFIRMATION",
}


def _official_id(payload: dict) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="공무원 식별정보가 유효하지 않습니다")


def _initial_evidence(alert_id: int, prediction: RiskPrediction, cell: CommercialQuarter) -> list[AlertEvidence]:
    return [
        AlertEvidence(
            alert_id=alert_id,
            evidence_type="OBSERVED_SIGNAL",
            metric_code="actual_closure_rate_pct",
            observed_value=round((cell.closure_rate or 0.0) * 100, 2),
            baseline_value=AVG_CLOSURE_RATE_PCT,
            direction="above" if (cell.closure_rate or 0.0) * 100 >= AVG_CLOSURE_RATE_PCT else "below",
            source_quarter_code=cell.quarter_code,
            description="최근 관측 폐업률과 화성시 평균 비교",
        ),
        AlertEvidence(
            alert_id=alert_id,
            evidence_type="OBSERVED_SIGNAL",
            metric_code="opening_rate_pct",
            observed_value=round((cell.opening_rate or 0.0) * 100, 2),
            source_quarter_code=cell.quarter_code,
            description="최근 관측 개업률",
        ),
        AlertEvidence(
            alert_id=alert_id,
            evidence_type="OBSERVED_SIGNAL",
            metric_code="trend_slope",
            observed_value=cell.trend_slope or 0.0,
            direction="up" if (cell.trend_slope or 0.0) > 0 else "flat_or_down",
            source_quarter_code=cell.quarter_code,
            description="최근 4분기 폐업률 추세",
        ),
        AlertEvidence(
            alert_id=alert_id,
            evidence_type="CONTEXT_INDICATOR",
            metric_code="predicted_risk_rank",
            observed_value=prediction.predicted_rank,
            quality_flag="model_rank_only",
            source_quarter_code=cell.quarter_code,
            description="모델 예측 절대값이 아닌 상대 위험 순위",
        ),
    ]


@router.post("/alerts/{prediction_id}", response_model=AlertCaseResponse)
def create_alert_case(
    prediction_id: int,
    db: Session = Depends(get_db),
    official: dict = Depends(get_current_official),
):
    existing = db.query(AlertCase).filter(AlertCase.prediction_id == prediction_id).first()
    if existing:
        return existing

    result = (
        db.query(RiskPrediction, CommercialQuarter)
        .join(CommercialQuarter, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .filter(RiskPrediction.id == prediction_id)
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="예측 결과가 없습니다")
    prediction, cell = result
    alert = AlertCase(prediction_id=prediction_id, assigned_official_id=_official_id(official))
    db.add(alert)
    db.flush()
    db.add_all(_initial_evidence(alert.id, prediction, cell))
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/alerts", response_model=list[AlertCaseResponse])
def list_alert_cases(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_official),
):
    q = db.query(AlertCase)
    if status:
        q = q.filter(AlertCase.status == status)
    return q.order_by(AlertCase.created_at.desc()).all()


@router.patch("/alerts/{alert_id}", response_model=AlertCaseResponse)
def update_alert_case(
    alert_id: int,
    body: AlertCaseUpdate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_official),
):
    alert = db.get(AlertCase, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="경보 검토 건이 없습니다")
    if body.status is not None:
        if body.status not in ALERT_STATUSES:
            raise HTTPException(status_code=400, detail="지원하지 않는 경보 상태입니다")
        alert.status = body.status
        alert.reviewed_at = datetime.now(timezone.utc)
        if body.status == "closed":
            alert.closed_at = datetime.now(timezone.utc)
    if body.confirmed_cause_code is not None:
        alert.confirmed_cause_code = body.confirmed_cause_code
    if body.decision_note is not None:
        alert.decision_note = body.decision_note
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/alerts/{alert_id}/evidence", response_model=list[AlertEvidenceResponse])
def list_evidence(
    alert_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_official),
):
    return (
        db.query(AlertEvidence)
        .filter(AlertEvidence.alert_id == alert_id)
        .order_by(AlertEvidence.created_at)
        .all()
    )


@router.post("/alerts/{alert_id}/evidence", response_model=AlertEvidenceResponse)
def add_evidence(
    alert_id: int,
    body: AlertEvidenceCreate,
    db: Session = Depends(get_db),
    official: dict = Depends(get_current_official),
):
    if not db.get(AlertCase, alert_id):
        raise HTTPException(status_code=404, detail="경보 검토 건이 없습니다")
    if body.evidence_type not in EVIDENCE_TYPES:
        raise HTTPException(status_code=400, detail="지원하지 않는 근거 유형입니다")
    evidence = AlertEvidence(
        alert_id=alert_id,
        verified_by_official_id=_official_id(official),
        **body.model_dump(),
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.get("/programs", response_model=list[PolicyProgramResponse])
def list_policy_programs(
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_official),
):
    return db.query(PolicyProgram).filter(PolicyProgram.is_active.is_(True)).order_by(PolicyProgram.id).all()


@router.post("/actions", response_model=PolicyActionResponse)
def create_policy_action(
    body: PolicyActionCreate,
    db: Session = Depends(get_db),
    official: dict = Depends(get_current_official),
):
    alert = db.get(AlertCase, body.alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="경보 검토 건이 없습니다")
    program = db.query(PolicyProgram).filter(PolicyProgram.program_code == body.program_code).first()
    if not program:
        raise HTTPException(status_code=404, detail="정책 프로그램이 없습니다")
    action = PolicyAction(
        alert_id=body.alert_id,
        program_id=program.id,
        official_id=_official_id(official),
        status=body.status,
        decision_reason=body.decision_reason,
        budget_amount=body.budget_amount,
        target_store_count=body.target_store_count,
    )
    alert.status = "actioned"
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.post("/actions/{action_id}/outcomes", response_model=PolicyOutcomeResponse)
def create_policy_outcome(
    action_id: int,
    body: PolicyOutcomeCreate,
    db: Session = Depends(get_db),
    _: dict = Depends(get_current_official),
):
    if not db.get(PolicyAction, action_id):
        raise HTTPException(status_code=404, detail="정책 실행 건이 없습니다")
    existing = (
        db.query(PolicyOutcome)
        .filter(
            PolicyOutcome.action_id == action_id,
            PolicyOutcome.evaluation_quarter_code == body.evaluation_quarter_code,
        )
        .first()
    )
    if existing:
        for key, value in body.model_dump().items():
            setattr(existing, key, value)
        outcome = existing
    else:
        outcome = PolicyOutcome(action_id=action_id, **body.model_dump())
        db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return outcome
