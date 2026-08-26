"""규칙 기반 공개 상권 요약 보고서."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import RuleReportResponse
from ..services.report import build_report
from .public import get_public_cell
from .recommend import recommend_score


router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/summary", response_model=RuleReportResponse)
def report_summary(
    area_id: int = Query(...),
    industry_id: int = Query(...),
    preset: str | None = Query(None),
    db: Session = Depends(get_db),
):
    score = recommend_score(
        area_id=area_id,
        industry_id=industry_id,
        preset=preset,
        db=db,
    )
    observed = get_public_cell(area_id=area_id, industry_id=industry_id, db=db)
    return build_report(score, observed)
