"""셀 상세 — 지도·조기경보·현장점검 세 화면의 종착지.

지금까지 화면 넷이 전부 "찾기"였고 "그래서 무엇을 할 것인가"를 보여주는 곳이 없었다.
셀 하나(행정동×업종)를 클릭하면 판단에 필요한 것이 한 페이지에 모인다.

세 영역을 섞지 않는다(CLAUDE.md 용어 규칙).
    확인된 위험 신호   관측 데이터로 직접 계산된 사실
    AI 예측 기여 요인   모델이 이 셀을 상위로 본 내부 근거. 인과 아님
    공무원 확인 필요    데이터가 없어 모델이 보지 못한 원인 후보
"""
import sys
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.dependencies import decode_token, get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    AlertCase,
    AlertContact,
    AreaPopulationQuarter,
    PolicyProgram,
    CommercialQuarter,
    DataBatch,
    IndustryCategory,
    ModelRun,
    Official,
    RiskPrediction,
)
from ..services.compare import cumulative_denominator
from ..services.risk import (
    CELL_TYPE_CLOSE_CUT_PCT,
    CELL_TYPE_OPEN_CUT_PCT,
    GRADE_NOTICE,
    WINDOW_QUARTERS,
    action_message,
    pct,
)

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ai"))
    from cumulative import CELL_TYPES  # type: ignore
except Exception:  # pragma: no cover
    CELL_TYPES = {}

router = APIRouter(prefix="/api/cells", tags=["cells"], dependencies=[Depends(get_current_official)])

# 모델이 보지 못한 원인 후보. 데이터가 없어서 못 본 것이지 중요하지 않아서가 아니다.
# 없는 걸 없다고 적는 편이 있는 척하는 것보다 방어에 유리하다.
FIELD_CHECK_ITEMS = [
    {"label": "임대료 변동", "reason": "임대료 데이터가 동탄권·병점권·경기광역 3개 그룹뿐이라 25개 행정동이 같은 값을 공유합니다."},
    {"label": "재개발·정비사업", "reason": "사업 구역 데이터를 보유하지 않았습니다."},
    {"label": "대형점포 신규 입점", "reason": "대규모점포 인허가가 영업중 15건뿐이라 통계적 의미가 없습니다."},
    {"label": "매출 변화", "reason": "카드매출 2024년 11개월치가 제공처에 존재하지 않습니다."},
    {"label": "상권 내 공사·통행 제한", "reason": "해당 데이터를 보유하지 않았습니다."},
]


# services.risk.pct를 쓴다(NULL을 0.0%로 바꾸지 않는 버전). 라우터마다 사본을 두면
# 한쪽만 고쳐졌을 때 화면끼리 다른 숫자를 보여준다 — 이 프로젝트가 이미 겪은 실수다.
_pct = pct


def _latest_quarter(db: Session) -> int | None:
    return db.query(func.max(CommercialQuarter.quarter_code)).scalar()


@router.get("/{area_id}/{industry_id}")
def get_cell_detail(area_id: int, industry_id: int, db: Session = Depends(get_db)):
    latest = _latest_quarter(db)
    if not latest:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")

    row = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")
    cell, dong, industry = row

    # 3중 비교 — 숫자 하나만 보면 "6.2%, 그래서 뭐?"다. 세 방향으로 비교하면 원인의 위치가 좁혀진다.
    #   같은 업종 다른 동도 높다  -> 업종 전반의 문제
    #   같은 동 다른 업종도 높다  -> 지역의 문제
    #   이 조합만 높다            -> 여기만 특이. 현장 확인 1순위
    def _avg(*conditions) -> float | None:
        value = (
            db.query(func.avg(CommercialQuarter.closure_rate_cum4))
            .filter(
                CommercialQuarter.quarter_code == latest,
                CommercialQuarter.sample_insufficient.is_(False),
                CommercialQuarter.closure_rate_cum4.isnot(None),
                *conditions,
            )
            .scalar()
        )
        return _pct(value)

    prediction = (
        db.query(RiskPrediction)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .filter(ModelRun.is_active.is_(True), RiskPrediction.commercial_quarter_id == cell.id)
        .first()
    )
    batch = db.get(DataBatch, cell.batch_id) if cell.batch_id else None
    # 누적값 자체가 없는 셀(4분기 미충족)은 분모도 내리지 않는다. cumulative_denominator는
    # 그런 셀에 대해 '현재 점포수 x 4' 근사를 돌려주는데, 비율이 없는 자리에 분모만
    # 있으면 화면이 없는 값을 계산해 보여주게 된다.
    if cell.closure_rate_cum4 is None:
        _denominator, _denom_estimated = None, False
    else:
        _denominator, _denom_estimated = cumulative_denominator(cell)
    type_info = CELL_TYPES.get(cell.cell_type or "", {})

    return {
        "area_id": area_id,
        "industry_id": industry_id,
        "quarter_code": latest,
        "dong": dong,
        "category": industry,
        "store_count": cell.store_count,
        "sample_insufficient": cell.sample_insufficient,
        "window_quarters": WINDOW_QUARTERS,
        "grade_notice": GRADE_NOTICE,

        # ① 확인된 위험 신호 — 전부 관측값이다
        "risk_grade": cell.risk_grade,
        "cumulative_closure_rate_pct": _pct(cell.closure_rate_cum4),
        "cumulative_closure_count": cell.closure_count_cum4,
        # 누적 폐업률의 분모는 "4개 분기 직전점포수의 합"이지 현재 분기 점포수가 아니다.
        # 이걸 안 내려주면 화면이 건수 옆에 현재 점포수를 병기하게 되고, 읽는 사람이 눈으로
        # 나눈 값과 큰 숫자가 4배쯤 어긋난다 — 동탄8동 일반 교육이 "16.04%"인데 그 아래
        # "47곳 닫힘 / 전체 53곳"(89%)으로 보였다(2026-08-25 감사, 표본충분 231셀 전부 해당).
        "cumulative_denominator": _denominator,
        "denominator_estimated": _denom_estimated,
        "confidence_lower_pct": _pct(cell.closure_rate_lower4),
        "quarter_closure_rate_pct": _pct(cell.closure_rate),
        # 유형 판정과 같은 컬럼을 쓴다. 원본(opening_rate)은 수록 지연 결함이 남아 있어
        # 표본충분 셀의 26.8%가 0.0%로 나온다. 원본은 아래 provenance 옆에 참고로만 둔다.
        "opening_rate_pct": _pct(cell.opening_rate_ma4),
        "opening_rate_raw_pct": _pct(cell.opening_rate),
        "trend_slope": round(cell.trend_slope or 0.0, 3),
        "anomaly": cell.anomaly_flag,
        "saturation_rate": cell.saturation_rate,
        "comparison": {
            "industry_avg_pct": _avg(CommercialQuarter.industry_id == industry_id),
            "area_avg_pct": _avg(CommercialQuarter.area_id == area_id),
            "city_avg_pct": _avg(),
        },

        # ② 유형 판정과 처방
        "cell_type": cell.cell_type,
        "cell_type_summary": type_info.get("summary"),
        "cell_type_advice": type_info.get("advice"),
        "cell_type_avoid": type_info.get("avoid") or None,
        # 판정 근거. 유형은 개업률·폐업률을 각각 표본충분 셀의 중위값으로 가른 결과다.
        # 절단선을 함께 내려야 화면이 "왜 쇠퇴인가"를 그 자리에서 보여줄 수 있다 —
        # 근거 없이 이름만 뜨면 유형은 그냥 라벨로 읽힌다.
        "cell_type_open_cut_pct": CELL_TYPE_OPEN_CUT_PCT,
        "cell_type_close_cut_pct": CELL_TYPE_CLOSE_CUT_PCT,
        "action": action_message(cell.risk_grade or "안정", cell.anomaly_flag),

        # ③ AI 예측 — 순위만. 절대값은 노출하지 않는다
        "prediction_id": prediction.id if prediction else None,
        "predicted_rank": prediction.predicted_rank if prediction else None,
        "industry_rank": prediction.industry_rank if prediction else None,
        "industry_total": prediction.industry_total_areas if prediction else None,

        # ④ 공무원 확인 필요 항목
        "field_check_items": FIELD_CHECK_ITEMS,

        # ⑤ 근거·출처 — 감사·의회 대응용
        "provenance": {
            "source_name": batch.source_name if batch else None,
            "method_version": batch.method_version if batch else None,
            "source_start_quarter": batch.source_start_quarter if batch else None,
            "source_end_quarter": batch.source_end_quarter if batch else None,
            "row_count": batch.row_count if batch else None,
            "quality_notes": batch.quality_notes if batch else None,
        },
    }


@router.get("/{area_id}/{industry_id}/trend")
def get_cell_trend(area_id: int, industry_id: int, db: Session = Depends(get_db)):
    """분기별 추이. 누적값을 쓰므로 곡선이 매끄럽다.

    단일 분기 값도 함께 준다 — 담당자가 "원래 이렇게 튀는 동네인가"를 눈으로 볼 수 있게.
    다만 판정은 누적으로만 한다.
    """
    rows = (
        db.query(CommercialQuarter)
        .filter(
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .order_by(CommercialQuarter.quarter_code)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")
    return [
        {
            "quarter_code": r.quarter_code,
            "label": f"{r.quarter_code // 10}Q{r.quarter_code % 10}",
            "store_count": r.store_count,
            "cumulative_closure_rate_pct": _pct(r.closure_rate_cum4),
            "quarter_closure_rate_pct": _pct(r.closure_rate),
            "opening_rate_pct": _pct(r.opening_rate_ma4),
        }
        for r in rows
    ]


# ────────────────────────────────────────────────────────────────────────────
# 배후인구 추이
#
# 등급·상권유형 판정에 관여하지 않는다. 인구증감과 폐업률의 순위상관이 +0.238로 약하고
# 부호도 직관과 반대다(정남면 인구 -9.8%인데 폐업률 0.04, 봉담읍 +25.9%인데 0.05).
# 판정 축으로 넣으면 근거 없는 가중치가 된다.
#
# 그럼에도 붙이는 이유: 같은 "쇠퇴·위험"이라도 배후인구가 늘고 있으면 원인이 수요 부족이
# 아니라는 뜻이라 담당자가 현장에서 볼 것이 갈린다. 그 목적의 설명 근거다.

POPULATION_SOURCE = "KOSIS 주민등록 등록인구"
POPULATION_NOTICE = (
    "배후인구는 등급·상권 유형 판정에 쓰지 않습니다. 화성시 29개 읍면동 기준 인구증감과 "
    "폐업률의 순위상관은 +0.238로 약하고 부호도 직관과 반대여서 판정 축으로 쓸 근거가 없습니다. "
    "원인의 방향을 좁히는 참고 자료로만 보시기 바랍니다."
)

# 직전 분기 대비 이 폭을 넘는 변동은 자연 증감으로 보기 어렵다. 실측상 분기 등락률 절대값은
# 중위 0.43%, 90분위 1.75%다. 실제로 걸리는 사례는 두 종류이고 자료만으로는 구분되지 않는다 —
#   · 행정구역 조정: 동탄7동 2023Q3 -40.1% (같은 분기에 동탄9동 39,046명이 새로 생겼다)
#   · 대규모 택지 입주: 비봉면 2025Q1 +49.6%
# 그래서 어느 쪽인지 단정하지 않고 "자연 증감으로 읽지 말 것"만 표시한다.
POPULATION_BREAK_PCT = 15.0
POPULATION_BREAK_NOTE = (
    "직전 분기 대비 변동이 커서 행정구역 조정(분동·편입)이나 대규모 택지 입주로 보입니다. "
    "자연 증감으로 읽으면 안 됩니다."
)

# 방향을 말할 최소 폭. 이보다 작으면 "큰 변화 없음"으로 둔다.
POPULATION_FLAT_PCT = 3.0
POPULATION_WINDOW_QUARTERS = 12  # 3년

# 유형 x 인구방향. 유형은 "가게가 어떻게 드나드는가", 인구는 "손님이 느는가"라서
# 둘이 어긋날 때 현장에서 볼 것이 갈린다. 어긋나는 칸이 이 기능의 존재 이유다.
_POPULATION_READINGS = {
    ("쇠퇴", "증가"): "사람은 느는데 나간 자리가 채워지지 않고 있습니다. 배후 수요 부족이 아닌 다른 원인(임대료·업종 과밀·접근성)을 현장에서 확인해주세요.",
    ("쇠퇴", "감소"): "배후 수요 자체가 줄고 있습니다. 창업 유도보다 기존 점포 유지와 상권 환경 개선을 먼저 검토하시기 바랍니다.",
    ("고회전", "증가"): "배후 수요는 늘고 있는데 점포가 자주 바뀝니다. 수요보다 업종 과밀 쪽을 먼저 보시기 바랍니다.",
    ("고회전", "감소"): "점포가 자주 바뀌는데 배후 수요도 줄고 있습니다. 창업 사전상담에서 이 점을 알릴 필요가 있습니다.",
    ("성장", "증가"): "배후 수요와 신규 진입이 같은 방향입니다. 당장 개입할 근거는 약합니다.",
    ("성장", "감소"): "배후 수요는 줄고 있는데 신규 진입이 이어집니다. 과열 조짐인지 관찰해주세요.",
    ("정체", "증가"): "사람은 느는데 드나듦이 없습니다. 신규 유입 여지를 검토해볼 수 있습니다.",
    ("정체", "감소"): "배후 수요가 줄면서 드나듦도 멈춰 있습니다.",
}


def _population_direction(change_pct: float | None) -> str | None:
    if change_pct is None:
        return None
    if change_pct >= POPULATION_FLAT_PCT:
        return "증가"
    if change_pct <= -POPULATION_FLAT_PCT:
        return "감소"
    return "보합"


@router.get("/{area_id}/{industry_id}/population")
def get_cell_population(area_id: int, industry_id: int, db: Session = Depends(get_db)):
    """셀의 배후인구(읍면동 등록인구) 분기 추이.

    industry_id는 값 자체에 쓰이지 않는다 — 배후인구는 읍면동 단위라 업종과 무관하다.
    그래도 받는 이유는 셀이 실재하는지 확인해 형제 엔드포인트(trend/programs/notice)와
    404 동작을 맞추기 위해서다. 없는 셀에 대해 인구만 돌려주면 화면이 빈 셀을 실재하는
    것처럼 보여준다.
    """
    cell = (
        db.query(CommercialQuarter)
        .filter(
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .order_by(CommercialQuarter.quarter_code.desc())
        .first()
    )
    if cell is None:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")

    area = db.query(AdminArea).filter(AdminArea.id == area_id).one_or_none()
    rows = (
        db.query(AreaPopulationQuarter)
        .filter(
            AreaPopulationQuarter.area_id == area_id,
            AreaPopulationQuarter.total_population.isnot(None),
        )
        .order_by(AreaPopulationQuarter.quarter_code)
        .all()
    )

    series = []
    previous = None
    for row in rows:
        qoq = None
        if previous:
            qoq = round((row.total_population - previous) / previous * 100, 2)
        series.append({
            "quarter_code": row.quarter_code,
            "label": f"{row.quarter_code // 10}Q{row.quarter_code % 10}",
            "population": row.total_population,
            "qoq_pct": qoq,
            # 자연 증감으로 읽으면 안 되는 지점. 화면이 이 분기를 표시한다.
            "is_break": qoq is not None and abs(qoq) >= POPULATION_BREAK_PCT,
        })
        previous = row.total_population

    if not series:
        return {
            "area_name": area.area_name if area else None,
            "source": POPULATION_SOURCE,
            "notice": POPULATION_NOTICE,
            "series": [],
            "change": None,
            "reading": "이 읍면동의 등록인구 자료가 없습니다.",
        }

    window = series[-(POPULATION_WINDOW_QUARTERS + 1):]
    first, last = window[0], window[-1]
    has_break = any(point["is_break"] for point in window[1:])
    change_pct = round((last["population"] - first["population"]) / first["population"] * 100, 1)

    change = {
        "from_label": first["label"],
        "to_label": last["label"],
        "from_population": first["population"],
        "to_population": last["population"],
        "quarters": len(window) - 1,
        "change_pct": change_pct,
        "has_break": has_break,
        "break_note": POPULATION_BREAK_NOTE if has_break else None,
    }

    if has_break:
        # 경계 조정이 섞인 구간에서 방향을 말하면 없는 인구 이동을 있다고 하는 셈이 된다.
        direction = None
        reading = "구간 안에 급변 분기가 있어 증감 방향을 판단하지 않습니다. " + POPULATION_BREAK_NOTE
    else:
        direction = _population_direction(change_pct)
        if direction == "보합":
            reading = f"배후인구는 {first['label']} 이후 큰 변화가 없습니다({change_pct:+.1f}%)."
        else:
            reading = _POPULATION_READINGS.get(
                (cell.cell_type, direction),
                f"배후인구가 {first['label']} 이후 {change_pct:+.1f}% {direction}했습니다.",
            )
    change["direction"] = direction
    return {
        "area_name": area.area_name if area else None,
        "source": POPULATION_SOURCE,
        "notice": POPULATION_NOTICE,
        "series": series,
        "change": change,
        "reading": reading,
    }


# ────────────────────────────────────────────────────────────────────────────
# 지원사업 연결
#
# "확인 순서"에서 끝나면 담당자가 현장에 다녀온 뒤 할 수 있는 게 화면에 없다.
# AI가 지원 대상을 결정하지 않는다는 원칙은 그대로 두고, 담당자가 판단할 재료만 준다.
#
# 매칭은 상권 유형·등급 기반이다(우리 처방 로직이라 근거가 있다).
# 자격 요건(업력·한도·신청 기간)은 실제 공고문에서 확인해야 하므로 비어 있으면
# requires_verification 플래그로 "요건 확인 필요"를 그대로 노출한다. 추정해서 채우지 않는다.

PROGRAM_NOTICE = (
    "상권 유형과 등급으로 추린 후보입니다. 지원 대상 결정이 아니며, "
    "개별 점포의 신청 자격은 소관 부서 공고문으로 확인해야 합니다."
)


@router.get("/{area_id}/{industry_id}/programs")
def get_cell_programs(area_id: int, industry_id: int, db: Session = Depends(get_db)):
    latest = _latest_quarter(db)
    cell = (
        db.query(CommercialQuarter)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .first()
    )
    if not cell:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")

    grade = cell.risk_grade or "안정"
    cell_type = cell.cell_type or ""
    matched, discouraged, others = [], [], []

    for program in db.query(PolicyProgram).filter(PolicyProgram.is_active.is_(True)).all():
        item = {
            "program_code": program.program_code,
            "program_name": program.program_name,
            "description": program.description,
            "match_reason": program.match_reason,
            "owner_department": program.owner_department,
            "legal_basis": program.legal_basis,
            "apply_period": program.apply_period,
            "support_limit_text": program.support_limit_text,
            "exclusion_note": program.exclusion_note,
            "requires_verification": program.requires_verification,
        }
        if cell_type and cell_type in (program.discouraged_cell_types or []):
            # 제외하지 않고 이유와 함께 보여준다 — "왜 이건 안 되나"도 담당자에게 필요한 정보다
            item["reason"] = f"{cell_type} 상권에는 효과가 상권 단위에서 상쇄될 수 있습니다"
            discouraged.append(item)
            continue
        type_ok = not program.target_cell_types or cell_type in program.target_cell_types
        grade_ok = not program.target_risk_grades or grade in program.target_risk_grades
        if type_ok and grade_ok:
            matched.append(item)
        else:
            missed = []
            if not type_ok:
                missed.append(f"대상 유형 {', '.join(program.target_cell_types or [])}")
            if not grade_ok:
                missed.append(f"대상 등급 {', '.join(program.target_risk_grades or [])}")
            item["reason"] = " · ".join(missed)
            others.append(item)

    return {
        "notice": PROGRAM_NOTICE,
        "cell_type": cell.cell_type,
        "risk_grade": grade,
        "matched": matched,
        "discouraged": discouraged,
        "not_matched": others,
        "verification_pending": sum(1 for p in matched if p["requires_verification"]),
    }


@router.get("/{area_id}/{industry_id}/notice")
def get_cell_notice(area_id: int, industry_id: int, db: Session = Depends(get_db)):
    """접촉 대상에게 발송할 안내문 초안.

    문구 원칙 — 경고가 아니라 안내다. "폐업 위험이 높습니다"가 아니라
    "신청 가능한 지원이 있습니다"로 쓴다. 개별 점포의 위험도를 말하지 않는다
    (판정은 상권 단위이고, 점포 단위 예측 성능은 방어할 수 없다).
    """
    detail = get_cell_detail(area_id, industry_id, db)
    programs = get_cell_programs(area_id, industry_id, db)
    names = [p["program_name"] for p in programs["matched"]]

    lines = [
        f"{detail['dong']} {detail['category']} 사업장 안내",
        "",
        f"{detail['dong']} 지역의 {detail['category']} 업종을 대상으로 "
        "소상공인 지원사업을 안내드립니다.",
        "",
    ]
    if names:
        lines.append("신청을 검토하실 수 있는 사업은 다음과 같습니다.")
        lines += [f"  · {n}" for n in names]
        lines.append("")
        lines.append("신청 자격과 기간은 사업별로 다르므로 소관 부서로 문의해 주시기 바랍니다.")
    else:
        lines.append(
            "현재 이 상권 조건에 맞는 지원사업이 확인되지 않았습니다. "
            "필요하신 사항이 있으시면 담당 부서로 문의해 주시기 바랍니다."
        )
    lines += ["", "화성시 소상공인 담당 부서"]

    return {
        "text": "\n".join(lines),
        "program_count": len(names),
        "notice": "발송 전 담당자가 내용을 확인하고 수정해 주세요. 자동 발송 기능은 제공하지 않습니다.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 접촉 이력
#
# 안내문을 만들 수 있게 됐으니 "보냈는지"를 남길 곳이 필요하다. 기록이 없으면
# 같은 상권에 두 부서가 각각 연락하거나, 아무도 연락하지 않은 채 넘어간다.
#
# 기록 단위는 셀(행정동×업종)이다. 개별 점포 참조(store_refs)는 노출 원칙이
# 확정되기 전까지 API에서 입력받지 않는다(models.py의 같은 주석 참조).
#
# 이력은 분기를 넘어 이어진다. 예측(risk_predictions)은 분기마다 새로 생기지만
# 조회할 때 그 셀의 모든 분기 예측에 달린 사건을 모아서 보여준다.
# 그렇게 하지 않으면 파이프라인을 돌릴 때마다 접촉 이력이 사라진 것처럼 보인다.
# ─────────────────────────────────────────────────────────────────────────────

CONTACT_CHANNELS = {
    "visit": "현장 방문",
    "phone": "전화",
    "sms": "문자",
    "email": "이메일",
    "meeting": "간담회",
    "other": "기타",
}
CONTACT_OUTCOMES = {
    "connected": "연락됨",
    "no_answer": "부재·무응답",
    "declined": "거절",
    "applied": "지원 신청",
    "pending": "진행 중",
}
CONTACT_NOTICE = (
    "이 기록은 상권 단위입니다. 개별 점포의 위험도를 근거로 접촉했다는 뜻이 아니며, "
    "기록 자체가 지원 대상 선정이나 배제의 근거가 되지 않습니다."
)


class ContactCreate(BaseModel):
    """접촉 1건 등록. 개별 점포 식별정보는 받지 않는다."""

    contacted_on: date
    channel: Literal["visit", "phone", "sms", "email", "meeting", "other"]
    outcome: Literal["connected", "no_answer", "declined", "applied", "pending"]
    contacted_store_count: Optional[int] = Field(default=None, ge=0, le=10000)
    note: Optional[str] = Field(default=None, max_length=2000)


def _cell_quarter_ids(db: Session, area_id: int, industry_id: int) -> list[int]:
    """해당 셀의 모든 분기 행 id. 분기를 넘어 이력을 잇기 위해 쓴다."""
    return [
        row[0]
        for row in db.query(CommercialQuarter.id).filter(
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
    ]


def _official_id(payload: dict) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="인증 정보에 담당자 식별자가 없습니다")


@router.get("/{area_id}/{industry_id}/contacts")
def list_cell_contacts(
    area_id: int,
    industry_id: int,
    db: Session = Depends(get_db),
    payload: dict = Depends(decode_token),
):
    # 삭제 버튼을 본인 기록에만 띄우기 위해 소유 여부를 함께 내린다.
    # 남의 기록을 지울 수 있으면 접촉 이력 자체를 증빙으로 못 쓴다.
    viewer_id = _official_id(payload)
    quarter_ids = _cell_quarter_ids(db, area_id, industry_id)
    items = []
    if quarter_ids:
        rows = (
            db.query(AlertContact, Official.name, Official.username)
            .join(AlertCase, AlertContact.alert_id == AlertCase.id)
            .join(RiskPrediction, AlertCase.prediction_id == RiskPrediction.id)
            .outerjoin(Official, AlertContact.official_id == Official.id)
            .filter(RiskPrediction.commercial_quarter_id.in_(quarter_ids))
            .order_by(AlertContact.contacted_on.desc(), AlertContact.id.desc())
            .all()
        )
        for contact, official_name, username in rows:
            items.append({
                "id": contact.id,
                "contacted_on": contact.contacted_on.isoformat(),
                "channel": contact.channel,
                "channel_label": CONTACT_CHANNELS.get(contact.channel, contact.channel),
                "outcome": contact.outcome,
                "outcome_label": CONTACT_OUTCOMES.get(contact.outcome, contact.outcome),
                "contacted_store_count": contact.contacted_store_count,
                "note": contact.note,
                "official": official_name or username or "미상",
                "mine": contact.official_id == viewer_id,
            })

    outcome_counts: dict[str, int] = {}
    for item in items:
        outcome_counts[item["outcome_label"]] = outcome_counts.get(item["outcome_label"], 0) + 1

    last_on = items[0]["contacted_on"] if items else None
    days_since = None
    if last_on:
        days_since = (date.today() - date.fromisoformat(last_on)).days

    return {
        "notice": CONTACT_NOTICE,
        "channels": [{"value": k, "label": v} for k, v in CONTACT_CHANNELS.items()],
        "outcomes": [{"value": k, "label": v} for k, v in CONTACT_OUTCOMES.items()],
        "items": items,
        "total": len(items),
        "last_contacted_on": last_on,
        "days_since_last_contact": days_since,
        "outcome_counts": outcome_counts,
    }


@router.post("/{area_id}/{industry_id}/contacts", status_code=201)
def create_cell_contact(
    area_id: int,
    industry_id: int,
    body: ContactCreate = Body(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(decode_token),
):
    official_id = _official_id(payload)
    if not db.get(Official, official_id):
        raise HTTPException(status_code=401, detail="담당자 계정을 찾을 수 없습니다")
    if body.contacted_on > date.today():
        raise HTTPException(status_code=400, detail="미래 날짜로는 기록할 수 없습니다")

    latest = _latest_quarter(db)
    cell = (
        db.query(CommercialQuarter)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .first()
    )
    if not cell:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")

    prediction = (
        db.query(RiskPrediction)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .filter(ModelRun.is_active.is_(True), RiskPrediction.commercial_quarter_id == cell.id)
        .first()
    )
    if not prediction:
        # 예측이 없으면 사건을 만들 자리가 없다. 조용히 넘기지 않고 원인을 말한다.
        raise HTTPException(
            status_code=409,
            detail="이 상권에 활성 모델 예측이 없어 기록할 수 없습니다. 파이프라인 적재 상태를 확인해 주세요.",
        )

    case = db.query(AlertCase).filter(AlertCase.prediction_id == prediction.id).first()
    if not case:
        case = AlertCase(prediction_id=prediction.id, status="new")
        db.add(case)
        db.flush()

    contact = AlertContact(
        alert_id=case.id,
        official_id=official_id,
        contacted_on=body.contacted_on,
        channel=body.channel,
        outcome=body.outcome,
        target_scope="cell",
        contacted_store_count=body.contacted_store_count,
        note=body.note,
    )
    db.add(contact)

    # 첫 접촉이 들어오면 사건 상태를 올린다. 목록에서 "손대지 않은 것"과 구분되게.
    # 값은 workflow.py의 ALERT_STATUSES 어휘를 따른다 — 여기서만 쓰는 값을 넣으면
    # 그 케이스를 workflow API로 갱신할 때 400이 나고 상태 필터에도 안 걸린다.
    if case.status == "new":
        case.status = "reviewing"
        case.reviewed_at = func.now()

    db.commit()
    return {"id": contact.id, "alert_case_id": case.id, "status": case.status}


@router.delete("/{area_id}/{industry_id}/contacts/{contact_id}", status_code=204)
def delete_cell_contact(
    area_id: int,
    industry_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    payload: dict = Depends(decode_token),
):
    """접촉 기록 1건 삭제.

    **본인이 남긴 기록만 지울 수 있다.** 이 기록은 "어느 상권에 행정이 접촉했는가"의 증빙이라
    남의 기록을 지울 수 있으면 이력 자체를 믿을 수 없게 된다.

    지금은 실제로 행을 지운다(soft delete 아님). 잘못 입력한 기록을 남겨두면 목록이 오염되고,
    현재 이 이력을 인용하는 산출물이 없어서다. 이력이 보고서·감사 자료로 쓰이기 시작하면
    deleted_at 컬럼을 두는 쪽으로 바꿔야 한다 — 그때는 이 주석을 근거로 삼을 것.
    """
    official_id = _official_id(payload)
    quarter_ids = _cell_quarter_ids(db, area_id, industry_id)
    if not quarter_ids:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")

    contact = (
        db.query(AlertContact)
        .join(AlertCase, AlertContact.alert_id == AlertCase.id)
        .join(RiskPrediction, AlertCase.prediction_id == RiskPrediction.id)
        .filter(
            AlertContact.id == contact_id,
            RiskPrediction.commercial_quarter_id.in_(quarter_ids),
        )
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="해당 접촉 기록을 찾을 수 없습니다")
    if contact.official_id != official_id:
        raise HTTPException(
            status_code=403,
            detail="본인이 남긴 기록만 삭제할 수 있습니다. 다른 담당자의 기록은 그 담당자에게 요청해 주세요.",
        )

    db.delete(contact)
    db.commit()
    return None
