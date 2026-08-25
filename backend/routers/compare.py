"""상권 비교 — 두 셀(행정동 x 업종)을 나란히 놓고 차이를 판정한다.

노다지(서울 프로젝트)의 지역 비교/업종 비교를 하나로 합친 화면이다. 노다지 비교 카드는 두 값을
나란히 놓고 끝냈지만, 여기서는 "그 차이를 말해도 되는가"를 먼저 따진다 — 자세한 근거는
backend/services/compare.py 상단 주석 참조.

용어 규칙(CLAUDE.md)을 따른다. 어느 쪽이 "지원 우선"이라고 말하지 않고 "현장 확인 우선순위"로만
말한다. 예측값(predicted_closure_rate_internal)은 응답에 넣지 않는다.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    RiskPrediction,
)
from ..schemas import CompareCellItem, CompareDiff, CompareResponse
from ..services.compare import build_verdict, closure_interval_pct, rates_distinguishable
from ..services.risk import GRADE_NOTICE, PROVISIONAL_NOTICE, WINDOW_QUARTERS, quarter_label

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ai"))
    from cumulative import CELL_TYPES  # type: ignore
except Exception:  # pragma: no cover
    CELL_TYPES = {}

router = APIRouter(prefix="/api/compare", tags=["compare"], dependencies=[Depends(get_current_official)])

# 차이를 숫자로 보여줄 지표. 등급·유형·순위는 크기 비교가 성립하지 않으므로 여기 넣지 않고
# 좌우 카드에서 값 그대로 보여준다.
DIFF_METRICS = [
    ("cumulative_closure_rate_pct", f"{WINDOW_QUARTERS}분기 누적 폐업률", "%", 2),
    ("cumulative_closure_count", "누적 폐업 건수", "건", 0),
    ("store_count", "점포수", "개", 0),
    ("opening_rate_pct", "보정 개업률", "%", 2),
    ("saturation_rate", "업종 포화도", "", 2),
    ("competition_index", "경쟁강도", "", 2),
    ("trend_slope", "트렌드 기울기", "", 3),
]


def _pct(value) -> float:
    return round((value or 0.0) * 100, 2)


def _parse_cell(raw: str, side: str) -> tuple[int, int]:
    """'12:34' -> (12, 34)"""
    try:
        area_id, industry_id = raw.split(":")
        return int(area_id), int(industry_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"{side} 형식이 올바르지 않습니다. 'area_id:industry_id' 형태여야 합니다 (예: 3:17)",
        )


def _load_cell(db: Session, area_id: int, industry_id: int, quarter: int) -> dict:
    row = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == quarter,
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"해당 상권을 찾을 수 없습니다 ({area_id}:{industry_id})")
    cell, area_name, industry_name = row

    prediction = (
        db.query(RiskPrediction)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .filter(ModelRun.is_active.is_(True), RiskPrediction.commercial_quarter_id == cell.id)
        .first()
    )
    type_info = CELL_TYPES.get(cell.cell_type or "", {})

    return {
        "area_id": area_id,
        "industry_id": industry_id,
        "area_name": area_name,
        "industry_name": industry_name,
        "quarter_code": quarter,
        "store_count": cell.store_count,
        "cumulative_closure_rate_pct": _pct(cell.closure_rate_cum4),
        "cumulative_closure_count": cell.closure_count_cum4,
        "confidence_lower_pct": _pct(cell.closure_rate_lower4),
        "interval": closure_interval_pct(cell),
        "opening_rate_pct": _pct(cell.opening_rate),
        "saturation_rate": cell.saturation_rate,
        "competition_index": cell.competition_index,
        "trend_slope": round(cell.trend_slope or 0.0, 3),
        "anomaly": cell.anomaly_flag,
        "risk_grade": cell.risk_grade,
        "cell_type": cell.cell_type,
        "cell_type_summary": type_info.get("summary"),
        # 표본부족 셀은 등급 산정에서 빠지므로 순위도 의미가 없다 — 그대로 None이 나온다
        "industry_rank": prediction.industry_rank if prediction else None,
        "industry_total_areas": prediction.industry_total_areas if prediction else None,
        "sample_insufficient": cell.sample_insufficient,
    }


@router.get("/options")
def compare_options(db: Session = Depends(get_db)):
    """비교 화면의 선택지. 프론트에 행정동·업종 목록을 하드코딩하지 않기 위한 것이다.

    /api/analysis/dongs·categories는 이름만 돌려주는데 비교는 id가 필요하고, 무엇보다
    (행정동 x 업종) 조합이 전부 존재하지는 않는다. 없는 조합을 고르면 404가 나므로
    동마다 실제로 존재하는 업종 id만 함께 내려서 프론트가 2단계로 좁히게 한다.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")

    rows = (
        db.query(
            AdminArea.id, AdminArea.area_name,
            IndustryCategory.id, IndustryCategory.industry_name,
            CommercialQuarter.sample_insufficient,
        )
        .join(CommercialQuarter, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(CommercialQuarter.quarter_code == latest)
        .order_by(AdminArea.area_name, IndustryCategory.industry_name)
        .all()
    )

    areas: dict[int, dict] = {}
    industries: dict[int, str] = {}
    for area_id, area_name, industry_id, industry_name, short in rows:
        industries.setdefault(industry_id, industry_name)
        a = areas.setdefault(area_id, {"id": area_id, "name": area_name, "industries": []})
        # 표본부족 셀도 목록에 남긴다 — 사각지대 트랙과 같은 원칙이다. 판단을 보류할 뿐 지우지 않는다.
        a["industries"].append({"id": industry_id, "sample_insufficient": short})

    return {
        "quarter_code": latest,
        "quarter_label": quarter_label(latest),
        "areas": sorted(areas.values(), key=lambda a: a["name"]),
        "industries": [{"id": i, "name": n} for i, n in sorted(industries.items(), key=lambda kv: kv[1])],
    }


@router.get("", response_model=CompareResponse)
def compare_cells(
    left: str = Query(..., description="area_id:industry_id (예: 3:17)"),
    right: str = Query(..., description="area_id:industry_id"),
    db: Session = Depends(get_db),
):
    l_area, l_industry = _parse_cell(left, "left")
    r_area, r_industry = _parse_cell(right, "right")
    if (l_area, l_industry) == (r_area, r_industry):
        raise HTTPException(status_code=400, detail="서로 다른 두 상권을 지정해야 합니다")

    quarter = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not quarter:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")

    l = _load_cell(db, l_area, l_industry, quarter)
    r = _load_cell(db, r_area, r_industry, quarter)

    distinguishable = rates_distinguishable(
        l["interval"], r["interval"],
        l["cumulative_closure_count"] or 0, r["cumulative_closure_count"] or 0,
    )
    either_short = l["sample_insufficient"] or r["sample_insufficient"]

    diffs = []
    for metric, label, unit, decimals in DIFF_METRICS:
        lv, rv = l.get(metric), r.get(metric)
        delta = round(lv - rv, 3) if lv is not None and rv is not None else None
        # 신뢰구간 판정은 폐업률에만 적용한다. 점포수 같은 관측 카운트는 표본오차 개념이 없다.
        if metric == "cumulative_closure_rate_pct":
            comparable = distinguishable and not either_short
            note = None
            if either_short:
                note = "표본부족 상권이 포함돼 통계 비교를 보류합니다"
            elif not distinguishable:
                note = "이 차이는 표본 크기로 설명될 수 있습니다 (두 비율 z검정, α=0.05)"
        else:
            comparable, note = True, None
        diffs.append(CompareDiff(
            metric=metric, label=label, unit=unit, decimals=decimals,
            left=lv, right=rv, delta=delta, comparable=comparable, note=note,
        ))

    return CompareResponse(
        left=CompareCellItem(**l),
        right=CompareCellItem(**r),
        diffs=diffs,
        verdict=build_verdict(l, r, distinguishable),
        notice=f"{GRADE_NOTICE} {PROVISIONAL_NOTICE}",
        basis={
            "quarter_code": quarter,
            "quarter_label": quarter_label(quarter),
            "window_quarters": WINDOW_QUARTERS,
            "confidence_level": "95%",
            "method": "two-proportion z-test (판정) + Wilson score interval (표시)",
        },
    )
