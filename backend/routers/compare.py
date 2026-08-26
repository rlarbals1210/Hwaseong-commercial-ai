"""상권 비교 — 두 셀(행정동 x 업종)을 나란히 놓고 차이를 판정한다.

노다지(서울 프로젝트)의 지역 비교/업종 비교를 하나로 합친 화면이다. 노다지 비교 카드는 두 값을
나란히 놓고 끝냈지만, 여기서는 "그 차이를 말해도 되는가"를 먼저 따진다 — 자세한 근거는
backend/services/compare.py 상단 주석 참조.

용어 규칙(CLAUDE.md)을 따른다. 어느 쪽이 "지원 우선"이라고 말하지 않고 "현장 확인 우선순위"로만
말한다. 모델 내부의 예측 절대값은 응답에 넣지 않는다.
"""
import math
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    AreaPopulationQuarter,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    RiskPrediction,
)
from ..schemas import (
    CompareCellItem,
    CompareContextResponse,
    CompareDiff,
    CompareDistributionItem,
    ComparePeerItem,
    CompareResponse,
    CompareTrendPoint,
)
from ..services.compare import (
    build_verdict,
    closure_interval_pct,
    rates_distinguishable,
    two_proportion_z,
)
from ..services.risk import (
    CELL_TYPE_CLOSE_CUT_PCT,
    CELL_TYPE_OPEN_CUT_PCT,
    GRADE_NOTICE,
    PROVISIONAL_NOTICE,
    WINDOW_QUARTERS,
    pct,
    quarter_label,
)

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
    # 평균 업력. 폐업률이 같아도 점포가 젊은 곳과 오래된 곳은 손댈 지점이 다르다.
    # 실측: 한식 기준 새솔동 26.6분기 vs 화산동 60.1분기(2.3배).
    ("avg_tenure_quarters", "평균 업력", "분기", 1, "rate"),
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
        "avg_tenure_quarters": round(cell.avg_tenure_quarters, 1) if cell.avg_tenure_quarters else None,
        **_population_summary(db, area_id),
    }




# 배후인구 비교 구간. 3년(12분기)이면 신도시 입주나 구도심 이탈이 드러날 만큼 길고,
# 행정구역 개편의 영향을 덜 탄다.
POPULATION_WINDOW_QUARTERS = 12


def _population_summary(db: Session, area_id: int) -> dict:
    """배후 읍면동 등록인구와 3년 증감.

    상권의 성적이 아니라 그 상권이 놓인 조건이다. 등급·유형 판정에는 관여하지 않는다 —
    인구증감과 폐업률의 순위상관은 +0.238로 약하고 부호도 직관과 반대다.
    같은 폐업률이라도 배후 수요가 느는 곳과 주는 곳은 원인이 다르다는 것만 말한다.
    """
    rows = (
        db.query(AreaPopulationQuarter)
        .filter(
            AreaPopulationQuarter.area_id == area_id,
            AreaPopulationQuarter.total_population.isnot(None),
        )
        .order_by(AreaPopulationQuarter.quarter_code)
        .all()
    )
    if not rows:
        return {}
    window = rows[-(POPULATION_WINDOW_QUARTERS + 1):]
    first, last = window[0], window[-1]
    change = None
    if first.total_population:
        change = round((last.total_population - first.total_population) / first.total_population * 100, 1)
    return {
        "population": last.total_population,
        "population_change_pct": change,
        "population_from_label": quarter_label(first.quarter_code),
        "population_to_label": quarter_label(last.quarter_code),
    }



# 설명 후보로 볼 최소선. 표본이 업종당 9~27곳뿐이라 상관값 자체가 흔들리므로 느슨하게 잡고,
# 화면에는 상관과 표본 수를 함께 적어 담당자가 스스로 깎아 읽게 한다.
EXPLAIN_MIN_CORRELATION = 0.4
EXPLAIN_MIN_SIGMA = 0.8


def _rank(values: list[float]) -> list[float]:
    """동순위는 평균 순위로. 스피어만 상관에 쓴다."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 6:
        return None
    rx, ry = _rank(xs), _rank(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def _metric_columns() -> dict:
    """지표 이름 -> 셀에서 값을 꺼내는 함수. 시그마·상관이 같은 정의를 쓰게 한 곳에 둔다."""
    return {
        "cumulative_closure_rate_pct": lambda c: pct(c.closure_rate_cum4),
        "cumulative_closure_count": lambda c: c.closure_count_cum4,
        "store_count": lambda c: c.store_count,
        "opening_rate_pct": lambda c: pct(c.opening_rate_ma4),
        "saturation_rate": lambda c: c.saturation_rate,
        "competition_index": lambda c: c.competition_index,
        "trend_slope": lambda c: c.trend_slope,
        "avg_tenure_quarters": lambda c: c.avg_tenure_quarters,
    }


def _industry_profile(db: Session, industry_id: int, quarter: int) -> dict:
    """업종 안에서의 지표별 표준편차와 폐업률 상관을 한 번에 낸다.

    표준편차는 "얼마나 다른가"를 재고, 상관은 "그 차이가 이 업종에서 의미가 있는가"를 잰다.
    둘은 다른 질문이다 — 기타 간이는 모든 지표의 상관이 0.17 이하라, 어떤 지표가 크게
    벌어져 있어도 폐업률을 설명할 후보가 아니다(2026-08-26 실측).
    """
    rows = (
        db.query(CommercialQuarter)
        .filter(
            CommercialQuarter.quarter_code == quarter,
            CommercialQuarter.industry_id == industry_id,
            CommercialQuarter.sample_insufficient.is_(False),
        )
        .all()
    )
    if len(rows) < 3:
        return {"sigmas": {}, "correlations": {}, "cells": len(rows)}

    columns = _metric_columns()
    sigmas: dict[str, float] = {}
    correlations: dict[str, float] = {}
    closure = [pct(c.closure_rate_cum4) for c in rows]

    for metric, getter in columns.items():
        values = [getter(c) for c in rows]
        present = [v for v in values if v is not None]
        if len(present) >= 3:
            mean = sum(present) / len(present)
            variance = sum((v - mean) ** 2 for v in present) / (len(present) - 1)
            std = math.sqrt(variance)
            if std > 0:
                sigmas[metric] = std
        if metric == "cumulative_closure_rate_pct":
            continue
        pairs = [(v, c) for v, c in zip(values, closure) if v is not None and c is not None]
        if len(pairs) >= 6:
            rho = _spearman([a for a, _ in pairs], [b for _, b in pairs])
            if rho is not None:
                correlations[metric] = round(rho, 2)
    return {"sigmas": sigmas, "correlations": correlations, "cells": len(rows)}


def _compare_trend(db: Session, left: tuple[int, int], right: tuple[int, int]) -> list[CompareTrendPoint]:
    """두 상권의 분기별 누적 폐업률을 같은 축에 올린다.

    최신 분기만 보면 「원래 나쁜 곳」과 「최근 나빠진 곳」이 구분되지 않는다. 후자면 개입
    시점이 지금이라 담당자의 판단이 갈린다.
    누적 4분기가 채워지기 전 분기는 None으로 남긴다 — 0.0으로 채우면 폐업이 없었다고 읽힌다.
    """
    series: dict[int, dict[str, float | None]] = {}
    for side, (area_id, industry_id) in (("left_pct", left), ("right_pct", right)):
        rows = (
            db.query(CommercialQuarter)
            .filter(
                CommercialQuarter.area_id == area_id,
                CommercialQuarter.industry_id == industry_id,
            )
            .order_by(CommercialQuarter.quarter_code)
            .all()
        )
        for row in rows:
            series.setdefault(row.quarter_code, {})[side] = pct(row.closure_rate_cum4)

    return [
        CompareTrendPoint(
            quarter_code=code,
            label=quarter_label(code),
            left_pct=values.get("left_pct"),
            right_pct=values.get("right_pct"),
        )
        for code, values in sorted(series.items())
    ]


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


# ────────────────────────────────────────────────────────────────────────────
# 비교 대상 찾기
#
# 담당자가 비교할 두 곳을 이미 알고 있어야 쓸 수 있는 도구는 도구가 아니다. 실제 질문은
# "이 상권이 왜 나쁜지 알아보려면 어디를 보면 되는가"이고, 그 답을 화면이 내야 한다.
#
# 후보는 같은 업종 + 비슷한 규모로 좁힌다. 점포 99곳짜리 한식을 점포 458곳짜리 한식과
# 비교하면 차이의 절반이 규모에서 온다. ±50%는 후보가 남을 만큼 넓고 규모가 섞이지 않을
# 만큼 좁은 선이고, 그 이상의 통계적 근거는 없다.

PEER_RATIO = 0.5
PEER_LIMIT = 12
PEER_NOTICE = (
    "같은 업종에서 점포 수가 비슷한 상권만 후보로 냅니다. 규모가 크게 다르면 "
    "차이의 상당 부분이 규모에서 오기 때문입니다."
)


def _peer_row(cell, area_name: str, base_count: int, base_denominator: int) -> ComparePeerItem:
    interval = closure_interval_pct(cell) or {}
    denominator = interval.get("denominator") or 0
    count = cell.closure_count_cum4 or 0
    z = two_proportion_z(count, denominator, base_count, base_denominator) if denominator else None
    base_rate = base_count / base_denominator if base_denominator else None
    rate = count / denominator if denominator else None
    # two_proportion_z는 절대값을 돌려준다. 후보가 더 낮으면 음수로 뒤집는다.
    if z is not None and rate is not None and base_rate is not None and rate < base_rate:
        z = -z
    left = _pct(cell.closure_rate_cum4)
    return ComparePeerItem(
        area_id=cell.area_id,
        industry_id=cell.industry_id,
        area_name=area_name,
        store_count=cell.store_count,
        cumulative_closure_rate_pct=left,
        cumulative_closure_count=count,
        z=round(z, 2) if z is not None else None,
        significant=bool(z is not None and abs(z) >= 1.96),
    )


@router.get("/context", response_model=CompareContextResponse)
def compare_context(
    cell: str = Query(..., description="area_id:industry_id"),
    db: Session = Depends(get_db),
):
    area_id, industry_id = _parse_cell(cell, "cell")
    quarter = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not quarter:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")

    rows = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == quarter,
            CommercialQuarter.industry_id == industry_id,
        )
        .all()
    )
    mine = next((r for r in rows if r[0].area_id == area_id), None)
    if mine is None:
        raise HTTPException(status_code=404, detail=f"해당 상권을 찾을 수 없습니다 ({cell})")
    my_cell, my_area, industry_name = mine

    # 분포·순위는 표본 기준을 넘은 상권만으로 낸다. 표본부족 셀의 비율을 같은 축에 찍으면
    # 점포 4곳짜리 0.0%가 가장 안전한 상권처럼 보인다.
    eligible = [
        (c, name) for c, name, _ in rows
        if not c.sample_insufficient and c.closure_rate_cum4 is not None
    ]
    eligible.sort(key=lambda item: item[0].closure_rate_cum4, reverse=True)

    distribution = [
        CompareDistributionItem(
            area_id=c.area_id,
            area_name=name,
            store_count=c.store_count,
            cumulative_closure_rate_pct=_pct(c.closure_rate_cum4),
            opening_rate_pct=_pct(c.opening_rate_ma4),
            cell_type=c.cell_type,
            rank=index,
            is_self=c.area_id == area_id,
        )
        for index, (c, name) in enumerate(eligible, 1)
    ]
    rank = next((i for i, (c, _) in enumerate(eligible, 1) if c.area_id == area_id), None)
    rates = sorted(_pct(c.closure_rate_cum4) for c, _ in eligible)
    median = None
    if rates:
        mid = len(rates) // 2
        median = rates[mid] if len(rates) % 2 else round((rates[mid - 1] + rates[mid]) / 2, 2)

    # 비교 후보 — 같은 업종, 점포 수 ±PEER_RATIO
    my_interval = closure_interval_pct(my_cell) or {}
    my_denominator = my_interval.get("denominator") or 0
    my_count = my_cell.closure_count_cum4 or 0
    low = int(my_cell.store_count * (1 - PEER_RATIO))
    high = int(my_cell.store_count * (1 + PEER_RATIO))

    peers = [
        _peer_row(c, name, my_count, my_denominator)
        for c, name in eligible
        if c.area_id != area_id and low <= c.store_count <= high
    ]
    for peer in peers:
        if peer.cumulative_closure_rate_pct is not None and my_cell.closure_rate_cum4 is not None:
            peer.delta_pp = round(peer.cumulative_closure_rate_pct - _pct(my_cell.closure_rate_cum4), 2)

    scored = [p for p in peers if p.z is not None]
    # 대조군은 "유의하게 다르면서 가장 멀리 떨어진 곳". 유의하지 않은 차이를 대조군으로
    # 내세우면 담당자가 없는 차이를 설명하러 현장에 간다.
    contrast = min((p for p in scored if p.significant), key=lambda p: p.z, default=None)
    if contrast is None:
        contrast = max((p for p in scored if p.significant), key=lambda p: p.z, default=None)
    similar = min(scored, key=lambda p: abs(p.z), default=None)

    peers.sort(key=lambda p: (p.z if p.z is not None else 0))
    return CompareContextResponse(
        quarter_code=quarter,
        quarter_label=quarter_label(quarter),
        area_id=area_id,
        industry_id=industry_id,
        area_name=my_area,
        industry_name=industry_name,
        store_count=my_cell.store_count,
        cumulative_closure_rate_pct=_pct(my_cell.closure_rate_cum4),
        sample_insufficient=my_cell.sample_insufficient,
        industry_eligible_cells=len(eligible),
        industry_rank=rank,
        industry_median_pct=median,
        distribution=distribution,
        type_open_cut_pct=CELL_TYPE_OPEN_CUT_PCT,
        type_close_cut_pct=CELL_TYPE_CLOSE_CUT_PCT,
        cell_type=my_cell.cell_type,
        peer_store_min=low,
        peer_store_max=high,
        peer_ratio_pct=int(PEER_RATIO * 100),
        peers=peers[:PEER_LIMIT],
        contrast=contrast,
        similar=similar,
        notice=PEER_NOTICE,
    )


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

    # 지표별 「업종 내 표준편차」. 지표 7개를 그냥 나열하면 어느 차이가 큰 차이인지
    # 담당자가 스스로 판단해야 한다. 단위가 제각각이라(폐업률 %, 경쟁강도 지수, 점포 수)
    # 절대 차이로는 서로 비교되지 않는다. 같은 업종 분포의 표준편차로 나눠 같은 자로 잰다.
    # 업종이 서로 다른 두 셀을 비교하는 경우에는 기준이 하나로 정해지지 않으므로 내지 않는다.
    profile = {"sigmas": {}, "correlations": {}, "cells": 0}
    if l_industry == r_industry:
        profile = _industry_profile(db, l_industry, quarter)
    sigmas = profile["sigmas"]
    correlations = profile["correlations"]

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
        sigma = None
        std = sigmas.get(metric)
        if comparable and delta is not None and std:
            sigma = round(delta / std, 2)
        rho = correlations.get(metric)
        # 차이가 크다는 것과 그 차이가 이 업종에서 의미 있다는 것은 다르다. 둘 다 넘어야
        # 설명 후보로 표시한다 — 상관만 높고 차이가 없으면 볼 것이 없고, 차이만 크고
        # 상관이 0에 가까우면 그 지표로는 폐업률을 설명할 수 없다.
        explains = bool(
            rho is not None
            and abs(rho) >= EXPLAIN_MIN_CORRELATION
            and sigma is not None
            and abs(sigma) >= EXPLAIN_MIN_SIGMA
        )
        diffs.append(CompareDiff(
            metric=metric, label=label, unit=unit, decimals=decimals, kind=kind,
            left=lv, right=rv, delta=delta, comparable=comparable, reason=reason, note=note,
            sigma=sigma, industry_correlation=rho, explains=explains,
        ))

    return CompareResponse(
        left=CompareCellItem(**l),
        right=CompareCellItem(**r),
        diffs=diffs,
        trend=_compare_trend(db, (l_area, l_industry), (r_area, r_industry)),
        industry_cells=profile["cells"],
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
