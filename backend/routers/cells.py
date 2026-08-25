"""셀 상세 — 지도·조기경보·현장점검 세 화면의 종착지.

지금까지 화면 넷이 전부 "찾기"였고 "그래서 무엇을 할 것인가"를 보여주는 곳이 없었다.
셀 하나(행정동×업종)를 클릭하면 판단에 필요한 것이 한 페이지에 모인다.

세 영역을 섞지 않는다(CLAUDE.md 용어 규칙).
    확인된 위험 신호   관측 데이터로 직접 계산된 사실
    AI 예측 기여 요인   모델이 이 셀을 상위로 본 내부 근거. 인과 아님
    공무원 확인 필요    데이터가 없어 모델이 보지 못한 원인 후보
"""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    CommercialQuarter,
    DataBatch,
    IndustryCategory,
    ModelRun,
    RiskPrediction,
)
from ..services.risk import GRADE_NOTICE, WINDOW_QUARTERS, action_message

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


def _pct(value) -> float:
    return round((value or 0.0) * 100, 2)


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
        return _pct(value) if value is not None else None

    prediction = (
        db.query(RiskPrediction)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .filter(ModelRun.is_active.is_(True), RiskPrediction.commercial_quarter_id == cell.id)
        .first()
    )
    batch = db.get(DataBatch, cell.batch_id) if cell.batch_id else None
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
        "confidence_lower_pct": _pct(cell.closure_rate_lower4),
        "quarter_closure_rate_pct": _pct(cell.closure_rate),
        "opening_rate_pct": _pct(cell.opening_rate),
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
            "opening_rate_pct": _pct(r.opening_rate),
        }
        for r in rows
    ]
