"""규칙 기반 공개 상권 요약 보고서."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from urllib.parse import quote

from ..database import get_db
from ..schemas import RuleReportResponse
from ..services.report import build_report
from ..services.report_pdf import build_report_pdf
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


@router.get("/summary.pdf", response_class=Response)
def report_pdf(
    area_id: int = Query(..., gt=0),
    industry_id: int = Query(..., gt=0),
    preset: str | None = Query(None),
    download: bool = Query(True),
    db: Session = Depends(get_db),
):
    report = report_summary(area_id=area_id, industry_id=industry_id, preset=preset, db=db)
    filename = f"상권보고서_{report['area_name']}_{report['industry_name']}_{report['quarter_label']}.pdf"
    disposition = "attachment" if download else "inline"
    return Response(
        content=build_report_pdf(report),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename=\"commercial-area-report.pdf\"; filename*=UTF-8''{quote(filename, safe='')}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
