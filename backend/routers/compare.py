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
from ..services.risk import pct, GRADE_NOTICE, PROVISIONAL_NOTICE, WINDOW_QUARTERS, quarter_label

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ai"))
    from cumulative import CELL_TYPES  # type: ignore
except Exception:  # pragma: no cover
    CELL_TYPES = {}

router = APIRouter(prefix="/api/compare", tags=["compare"], dependencies=[Depends(get_current_official)])

# 차이를 숫자로 보여줄 지표. 등급·유형·순위는 크기 비교가 성립하지 않으므로 여기 넣지 않고
# 좌우 카드에서 값 그대로 보여준다.
#
# kind가 판단을 가른다. 표본부족 상권(점포 4곳짜리 셀이 실제로 있다)에서 비율은 아무 말도
# 하지 못한다 — 폐업 0건이 "0.00%"로 찍히면 옆의 4.14%보다 안전해 보이지만 판단 자체가
# 불가능한 표본이다. 반면 건수는 표본이 작아도 사실이고 행정이 움직일 근거가 된다.
# 사각지대 화면이 폐업률이 아니라 폐업 건수로 정렬하는 것과 같은 원칙이다.
# 라벨과 자릿수 규칙 —
#   폐업률 이름은 화면 전체에서 "최근 1년 누적 폐업률" 하나로 통일한다. 예전에는 화면마다
#   7가지로 불렸고, 현장점검 한 화면 안에서만 세 번 다르게 나왔다(2026-08-25 감사).
#   비율 표시는 소수 1자리. 2자리로 두면 같은 상권이 대시보드 7.1%, 여기 7.14%로 보인다.
#   폐업률 둘째 자리는 폐업 1건이 못 만드는 정밀도라 정보가 아니라 잡음이다.
DIFF_METRICS = [
    ("cumulative_closure_rate_pct", "최근 1년 누적 폐업률", "%", 1, "rate"),
    ("cumulative_closure_count", "누적 폐업 건수", "건", 0, "count"),
    ("store_count", "점포 수", "개", 0, "count"),
    # 보정 개업률(4분기 이동평균). 상권유형 판정이 쓰는 값과 같은 컬럼이라
    # 이 화면의 배지와 숫자가 같은 근거 위에 선다(2026-08-26 마이그레이션 0006).
    ("opening_rate_pct", "개업률", "%", 1, "rate"),
    ("saturation_rate", "업종 포화도", "", 2, "rate"),
    ("competition_index", "경쟁강도", "", 2, "rate"),
    ("trend_slope", "트렌드 기울기", "", 3, "rate"),
]


# services.risk.pct 사용(NULL 보존). 라우터마다 사본을 두면 한쪽만 고쳐졌을 때
# 같은 셀이 화면에 따라 "—"와 "0.00%"로 다르게 뜬다.
_pct = pct


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
        "opening_rate_pct": _pct(cell.opening_rate_ma4),
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
    for metric, label, unit, decimals, kind in DIFF_METRICS:
        lv, rv = l.get(metric), r.get(metric)
        delta = round(lv - rv, 3) if lv is not None and rv is not None else None
        comparable, reason, note = True, None, None
        if kind == "rate" and either_short:
            # 표본부족이 한쪽이라도 끼면 비율은 판단 재료가 아니다. 값은 그대로 내리되
            # (감추면 왜 안 보이냐는 질문이 생긴다) 차이는 말하지 않는다.
            comparable, reason = False, "sample"
            note = "표본부족 상권이 포함돼 비율 지표로는 판단하지 않습니다"
        elif metric == "cumulative_closure_rate_pct" and not distinguishable:
            comparable, reason = False, "noise"
            note = "이 차이는 표본 크기로 설명될 수 있습니다 (두 비율 z검정, α=0.05)"
        diffs.append(CompareDiff(
            metric=metric, label=label, unit=unit, decimals=decimals, kind=kind,
            left=lv, right=rv, delta=delta, comparable=comparable, reason=reason, note=note,
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
