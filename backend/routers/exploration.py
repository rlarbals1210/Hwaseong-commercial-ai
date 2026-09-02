"""창업 탐색 보조 자료 — 관측 요일 패턴과 외부 검색 관심도."""
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AdminArea, AreaWeekdayFlow, IndustryCategory
from ..schemas import SearchTrendResponse, WeekdayFlowResponse
from ..services.search_interest import search_interest

router = APIRouter(prefix="/api/exploration", tags=["exploration"])


@router.get("/weekday-flow", response_model=WeekdayFlowResponse)
def weekday_flow(area_id: int = Query(...), db: Session = Depends(get_db)):
    area = db.get(AdminArea, area_id)
    if area is None:
        raise HTTPException(404, "해당 읍면동을 찾을 수 없습니다")
    month = db.query(func.max(AreaWeekdayFlow.month)).scalar()
    rows = db.query(AreaWeekdayFlow).filter_by(area_id=area_id, month=month).order_by(AreaWeekdayFlow.weekday).all()
    notice = (
        "선택 읍면동 전체의 요일 패턴이며 업종별 방문객이 아닙니다. 요일별 일평균 7개의 평균=100입니다. "
        "원본 측정 기준이 달라 과거 연도와의 절대 증감 비교에는 사용하지 않습니다."
    )
    base = dict(area_id=area_id, area_name=area.area_name, month=month, notice=notice)
    if ([row.weekday for row in rows] != list(range(7))
            or any(not math.isfinite(row.relative_index) or row.relative_index <= 0 for row in rows)):
        return dict(base, status="no_data", notice="최신 적재 월의 검증된 요일 자료가 없습니다. " + notice)
    work = sum(row.relative_index for row in rows[:5]) / 5
    weekend = sum(row.relative_index for row in rows[5:]) / 2
    return dict(base, status="ready", weekend_vs_weekday_pct=round((weekend / work - 1) * 100, 1),
                points=[dict(weekday=row.weekday, label="월화수목금토일"[row.weekday],
                             index=round(row.relative_index, 1)) for row in rows])


@router.get("/search-trend", response_model=SearchTrendResponse)
def search_trend(industry_id: int = Query(...), db: Session = Depends(get_db)):
    industry = db.get(IndustryCategory, industry_id)
    if industry is None:
        raise HTTPException(404, "해당 업종을 찾을 수 없습니다")
    return search_interest(industry_id, industry.industry_name)
