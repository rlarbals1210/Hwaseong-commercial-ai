"""공개 상권 트렌드 — 관측값만 사용한다.

여섯 엔드포인트 모두 `commercial_quarters`를 단일 원천으로 삼는다. 개업률은 원본의
수록 지연 결함을 피하기 위해 반드시 `opening_rate_ma4`만 사용하며, 예측값과 위험등급은
조회하지 않는다. 표본부족 셀도 비율 집계에서 제외한다.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AdminArea, CommercialQuarter, IndustryCategory
from ..schemas import (
    TrendCellResponse,
    TrendComparisonResponse,
    TrendOverviewResponse,
    TrendAreaRankResponse,
    TrendIndustryRankResponse,
)
from ..services.risk import SAMPLE_MIN, quarter_label


router = APIRouter(prefix="/api/trends", tags=["trends"])
TREND_QUARTERS = 12
CHANGE_QUARTERS = 5


def _latest(db: Session) -> int:
    value = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not value:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")
    return int(value)


def _quarters(db: Session, limit: int = TREND_QUARTERS) -> list[int]:
    rows = (
        db.query(CommercialQuarter.quarter_code)
        .distinct()
        .order_by(CommercialQuarter.quarter_code.desc())
        .limit(limit)
        .all()
    )
    return sorted(int(row[0]) for row in rows)


def _rows(
    db: Session,
    quarters: list[int],
    *,
    area_id: int | None = None,
    industry_id: int | None = None,
):
    query = (
        db.query(
            CommercialQuarter,
            AdminArea.area_name,
            AdminArea.area_type,
            IndustryCategory.industry_name,
        )
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code.in_(quarters),
            CommercialQuarter.sample_insufficient.is_(False),
        )
    )
    if area_id is not None:
        query = query.filter(CommercialQuarter.area_id == area_id)
    if industry_id is not None:
        query = query.filter(CommercialQuarter.industry_id == industry_id)
    return query.all()


def _weighted(cells, attr: str) -> float | None:
    pairs = [
        (float(getattr(cell, attr)), int(cell.store_count))
        for cell in cells
        if getattr(cell, attr) is not None and cell.store_count > 0
    ]
    denominator = sum(weight for _, weight in pairs)
    if not denominator:
        return None
    return round(sum(value * weight for value, weight in pairs) / denominator * 100, 2)


def _point(quarter: int, cells) -> dict:
    return {
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "closure_rate_pct": _weighted(cells, "closure_rate_cum4"),
        # 원본 opening_rate를 쓰지 않는다. 수록 지연을 보정한 4분기 이동평균만 사용한다.
        "opening_rate_pct": _weighted(cells, "opening_rate_ma4"),
        "store_count": sum(int(cell.store_count) for cell in cells),
        "cell_count": len(cells),
    }


def _series(rows, quarters: list[int]) -> list[dict]:
    by_quarter: dict[int, list] = defaultdict(list)
    for cell, *_ in rows:
        by_quarter[int(cell.quarter_code)].append(cell)
    return [_point(quarter, by_quarter[quarter]) for quarter in quarters if by_quarter[quarter]]


def _grouped_series(rows, quarters: list[int], key_fn) -> list[dict]:
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    return [
        {"key": key, "label": key, "series": _series(group_rows, quarters)}
        for key, group_rows in sorted(grouped.items())
    ]


def _change(series: list[dict]) -> float | None:
    values = [point for point in series if point["closure_rate_pct"] is not None]
    if len(values) < 2:
        return None
    return round(values[-1]["closure_rate_pct"] - values[0]["closure_rate_pct"], 2)


@router.get("/overview", response_model=TrendOverviewResponse)
def overview(db: Session = Depends(get_db)):
    quarters = _quarters(db)
    rows = _rows(db, quarters)
    return {
        "latest_quarter": _latest(db),
        "series": _series(rows, quarters),
        "method_notice": (
            f"점포 {SAMPLE_MIN}곳 이상인 읍면동 x 업종 셀을 점포 수로 가중한 관측 추이입니다. "
            "폐업률은 최근 4분기 누적, 개업률은 수록 지연을 보정한 4분기 이동평균입니다."
        ),
    }


@router.get("/areas", response_model=TrendAreaRankResponse)
def area_trends(
    industry_id: int = Query(...),
    db: Session = Depends(get_db),
):
    quarters = _quarters(db, CHANGE_QUARTERS)
    rows = _rows(db, quarters, industry_id=industry_id)
    if not rows:
        raise HTTPException(status_code=404, detail="해당 업종의 추이 자료가 없습니다")
    industry_name = rows[0][3]
    grouped = _grouped_series(rows, quarters, lambda row: row[1])
    for item in grouped:
        item["closure_change_pct"] = _change(item["series"])
    grouped.sort(
        key=lambda item: (
            item["closure_change_pct"] is None,
            -(item["closure_change_pct"] or 0),
            item["label"],
        )
    )
    return {"industry_id": industry_id, "industry_name": industry_name, "results": grouped}


@router.get("/industries", response_model=TrendIndustryRankResponse)
def industry_trends(
    area_id: int = Query(...),
    db: Session = Depends(get_db),
):
    quarters = _quarters(db, CHANGE_QUARTERS)
    rows = _rows(db, quarters, area_id=area_id)
    if not rows:
        raise HTTPException(status_code=404, detail="해당 읍면동의 추이 자료가 없습니다")
    area_name = rows[0][1]
    grouped = _grouped_series(rows, quarters, lambda row: row[3])
    for item in grouped:
        item["closure_change_pct"] = _change(item["series"])
    grouped.sort(
        key=lambda item: (
            item["closure_change_pct"] is None,
            -(item["closure_change_pct"] or 0),
            item["label"],
        )
    )
    return {"area_id": area_id, "area_name": area_name, "results": grouped}


@router.get("/cell", response_model=TrendCellResponse)
def cell_trend(
    area_id: int = Query(...),
    industry_id: int = Query(...),
    db: Session = Depends(get_db),
):
    quarters = _quarters(db)
    rows = _rows(db, quarters, area_id=area_id, industry_id=industry_id)
    if not rows:
        raise HTTPException(status_code=404, detail="해당 상권의 추이 자료가 없습니다")
    return {
        "area_id": area_id,
        "area_name": rows[0][1],
        "industry_id": industry_id,
        "industry_name": rows[0][3],
        "series": _series(rows, quarters),
    }


@router.get("/area-types", response_model=TrendComparisonResponse)
def area_type_trends(db: Session = Depends(get_db)):
    quarters = _quarters(db)
    rows = _rows(db, quarters)
    return {
        "title": "읍·면·동별 흐름",
        "description": "도농복합도시인 화성시의 행정구역 유형별 관측 추이입니다.",
        "groups": _grouped_series(rows, quarters, lambda row: row[2]),
    }


@router.get("/dongtan", response_model=TrendComparisonResponse)
def dongtan_trends(db: Session = Depends(get_db)):
    quarters = _quarters(db)
    rows = _rows(db, quarters)
    return {
        "title": "동탄권과 비동탄권",
        "description": (
            "동탄1~9동과 그 밖의 읍면동을 같은 관측 기준으로 비교합니다. "
            "지역 우열이나 인과를 뜻하지 않습니다."
        ),
        "groups": _grouped_series(
            rows,
            quarters,
            lambda row: "동탄권" if row[1].startswith("동탄") else "비동탄권",
        ),
    }
