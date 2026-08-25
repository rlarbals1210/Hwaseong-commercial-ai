import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    AreaQuarterSummary,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    PredictionContribution,
    RiskPrediction,
)
from ..schemas import (
    BlindspotItem,
    BlindspotResponse,
    ClosureRiskItem,
    ClosureRateRankingItem,
    PredictionExplanationResponse,
    VacancyRiskItem,
)
from ..services.explain import EXPLANATION_NOTICE
from ..services.risk import (
    AVG_CLOSURE_RATE_PCT,
    CAUTION_THRESHOLD_PCT,
    DANGER_THRESHOLD_PCT,
    GRADE_NOTICE,
    SAMPLE_MIN,
    WINDOW_QUARTERS,
    action_message,
)


# 유형별 처방 문구. 부정문을 쓰지 않고 주어를 "시"가 아니라 "상권 구조"로 둔다.
# "고회전 상권에는 개별 자금지원 효과가 낮다"는 판단은 그대로 살리되,
# 화성시가 잘못하고 있다는 인상을 주지 않는 표현으로 옮겼다.
try:  # ai/cumulative.py는 파이프라인 모듈이라 백엔드에서 못 읽을 수 있다
    _AI_DIR = Path(__file__).resolve().parent.parent.parent / "ai"
    sys.path.insert(0, str(_AI_DIR))
    from cumulative import CELL_TYPES  # type: ignore
except Exception:  # pragma: no cover - 방어용
    CELL_TYPES = {}


def _pct(value: float | None) -> float:
    """0~1 비율을 퍼센트로. None은 0으로."""
    return round((value or 0.0) * 100, 2)

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_official)])


@router.get("/closure-risk", response_model=list[ClosureRiskItem])
def get_closure_risk(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """조기경보(예측) — AI 예측 폐업률로 셀 순위만 매긴다. 예측 절대값은 응답에 없음
    (예측폐업률이 실제 관측치보다 구조적으로 ~2.4배 높게 나오는 게 확인되어, 화면에 노출하면
    오해를 줌 — 순위만 신뢰할 수 있는 정보). 실제 관측 지표는 팩트로 그대로 병기.

    2026-08-20: 병기하는 관측 폐업률을 단일 분기에서 4분기 누적으로 바꿨다. 단일 분기는
    점포 60곳짜리 셀에서 폐업 1~2건 차이로 1.5%와 9.0%를 오가서, "1순위인데 폐업률이 1.5%"
    같은 모순이 화면에 그대로 노출됐다. 순위(예측)와 근거(관측)가 서로 어긋나 보이지 않게
    누적값을 쓴다. 단일 분기 값은 참고용으로 함께 준다.

    정렬은 모델 순위(predicted_rank)를 그대로 쓴다. 미래 4분기 폐업률 적중에서 모델이
    관측 지표보다 낫기 때문이다(스피어만 0.566 vs 0.438)."""
    q = (
        db.query(RiskPrediction, CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .join(CommercialQuarter, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            ModelRun.is_active.is_(True),
            CommercialQuarter.sample_insufficient.is_(False),
            RiskPrediction.predicted_rank.isnot(None),
        )
    )
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    rows = q.order_by(RiskPrediction.predicted_rank.asc()).limit(limit).all()

    result = []
    for prediction, commercial, dong, industry in rows:
        level = commercial.risk_grade or "안정"
        result.append(ClosureRiskItem(
            prediction_id=prediction.id,
            predicted_rank=prediction.predicted_rank,
            area_id=commercial.area_id,
            industry_id=commercial.industry_id,
            dong=dong,
            category=industry,
            cumulative_closure_rate_pct=_pct(commercial.closure_rate_cum4),
            cumulative_closure_count=commercial.closure_count_cum4 or 0,
            store_count=commercial.store_count,
            confidence_lower_pct=_pct(commercial.closure_rate_lower4),
            risk_grade=level,
            cell_type=commercial.cell_type,
            cell_type_summary=CELL_TYPES.get(commercial.cell_type, {}).get("summary"),
            cell_type_advice=CELL_TYPES.get(commercial.cell_type, {}).get("advice"),
            cell_type_avoid=CELL_TYPES.get(commercial.cell_type, {}).get("avoid") or None,
            quarter_closure_rate_pct=_pct(commercial.closure_rate),
            open_rate_pct=_pct(commercial.opening_rate),
            trend_slope=round(commercial.trend_slope or 0.0, 3),
            saturation=commercial.saturation_rate or 0.0,
            anomaly=commercial.anomaly_flag,
            action=action_message(level, commercial.anomaly_flag),
        ))
    return result


@router.get("/closure-rate-ranking", response_model=list[ClosureRateRankingItem])
def get_closure_rate_ranking(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """상권 순위표(현황) — 4분기 누적 관측 폐업률로만 정렬. 보정·예측 관여 없음.

    정렬 기준을 표시값과 일치시킨다. 신뢰하한으로 정렬하는 안도 검증했으나 4분기 누적에서는
    상위 10개가 동일하게 나왔다(누적 분모가 이미 충분히 커서 소표본 보정이 순서를 바꾸지 않음).
    표시값과 순서가 어긋나는 쪽이 담당자에게 더 혼란스러워 누적률 정렬을 택했다.
    하한은 근거로 함께 준다.

    업종 내 순위를 병기한다 — 전체 순위만 두면 목록이 한 업종으로 덮인다(실측: 위험 24개 중
    18개가 교육 계열).
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return []

    base = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.sample_insufficient.is_(False),
            CommercialQuarter.closure_rate_cum4.isnot(None),
        )
    )

    # 업종 내 순위는 필터 적용 전 전체 집합에서 매겨야 의미가 있다.
    # (한식만 필터한 뒤 순위를 매기면 전체 순위와 같아져 병기할 이유가 없다)
    industry_rank: dict[int, tuple[int, int]] = {}
    per_industry: dict[str, list] = {}
    for commercial, _dong, industry in base.all():
        per_industry.setdefault(industry, []).append(commercial)
    for cells in per_industry.values():
        cells.sort(key=lambda c: c.closure_rate_cum4 or 0.0, reverse=True)
        for position, cell in enumerate(cells, 1):
            industry_rank[cell.id] = (position, len(cells))

    q = base
    if category:
        q = q.filter(IndustryCategory.industry_name == category)
    rows = q.order_by(CommercialQuarter.closure_rate_cum4.desc()).limit(limit).all()

    result = []
    for i, (commercial, dong, industry) in enumerate(rows, 1):
        rank_in_industry, industry_total = industry_rank.get(commercial.id, (None, None))
        result.append(ClosureRateRankingItem(
            rank=i,
            dong=dong,
            category=industry,
            closure_rate_pct=_pct(commercial.closure_rate_cum4),
            cumulative_closure_count=commercial.closure_count_cum4 or 0,
            confidence_lower_pct=_pct(commercial.closure_rate_lower4),
            store_count=commercial.store_count,
            risk_grade=commercial.risk_grade or "안정",
            industry_rank=rank_in_industry,
            industry_total=industry_total,
        ))
    return result


@router.get("/grade-notice")
def get_grade_notice():
    """등급 기준선과 고지 문구.

    프론트가 화성시 평균을 상수로 박아두면 파이프라인을 다시 돌릴 때마다 값이 어긋난다
    (실제로 CITY_AVG_PCT = 3.22가 코드에 하드코딩돼 있었다). 서버에서 내려준다.
    """
    return {
        "notice": GRADE_NOTICE,
        "window_quarters": WINDOW_QUARTERS,
        "city_average_pct": AVG_CLOSURE_RATE_PCT,
        "caution_threshold_pct": CAUTION_THRESHOLD_PCT,
        "danger_threshold_pct": DANGER_THRESHOLD_PCT,
        "sample_min": SAMPLE_MIN,
    }


@router.get("/vacancy-risk/map", response_model=list[VacancyRiskItem])
def get_vacancy_risk_map(db: Session = Depends(get_db)):
    """지도(현황) — 저장된 동×분기 집계를 조회한다. 예측값 관여 없음."""
    latest = db.query(func.max(AreaQuarterSummary.quarter_code)).scalar()
    if not latest:
        return []

    rows = (
        db.query(
            AreaQuarterSummary,
            AdminArea.area_name,
        )
        .join(AdminArea, AreaQuarterSummary.area_id == AdminArea.id)
        .filter(AreaQuarterSummary.quarter_code == latest)
        .all()
    )

    colors = {"안정": "#10B981", "주의": "#F59E0B", "위험": "#D51B4C"}
    result = [
            VacancyRiskItem(
                dong=dong,
                risk_ratio=summary.risk_industry_ratio_pct,
                risk_level=summary.area_risk_grade or "안정",
                color=colors.get(summary.area_risk_grade, "#10B981"),
                trend=round(summary.avg_trend_slope or 0.0, 3),
                total_cells=summary.total_cells,
                sample_sufficient_cells=summary.sample_sufficient_cells,
                coverage_pct=round(
                    summary.sample_sufficient_cells / summary.total_cells * 100, 1
                ) if summary.total_cells else 0.0,
            )
            for summary, dong in rows
        ]
    return sorted(result, key=lambda item: item.dong)


BLINDSPOT_NOTICE = (
    "표본이 작아 통계적 판단을 보류한 상권입니다. 모델이 판단하지 않으며, "
    "폐업 건수 순으로 정렬했습니다. 현장 확인을 권장합니다."
)


@router.get("/blindspots", response_model=BlindspotResponse)
def get_blindspots(
    limit: int = Query(30, ge=1, le=200),
    dong: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """사각지대 — 표본부족으로 등급·순위에서 빠진 셀.

    조회 기준(점포 50곳)을 넘지 못하면 화면에서 아예 사라진다. 그렇게 빠지는 점포가
    전체의 38%이고, 기배동·매송면은 커버율이 0%다. 아무리 상황이 나빠도 후보에 못 오른다.
    정책 우선순위를 고르는 도구에서 이건 형평성 문제로 직결된다.

    통계 판단은 계속 보류하되(등급을 매기지 않는다) 목록에서 지우지는 않는다.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return BlindspotResponse(
            notice=BLINDSPOT_NOTICE, items=[], total_cells=0, total_stores=0,
            total_closures=0, store_share_pct=0.0, sample_min=SAMPLE_MIN,
        )

    base = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.sample_insufficient.is_(True),
            CommercialQuarter.closure_count_cum4.isnot(None),
        )
    )

    all_rows = base.all()
    total_stores = sum(c.store_count for c, _, _ in all_rows)
    total_closures = sum(c.closure_count_cum4 or 0 for c, _, _ in all_rows)
    city_stores = (
        db.query(func.sum(CommercialQuarter.store_count))
        .filter(CommercialQuarter.quarter_code == latest)
        .scalar()
    ) or 0

    q = base
    if dong:
        q = q.filter(AdminArea.area_name == dong)
    rows = (
        q.order_by(CommercialQuarter.closure_count_cum4.desc())
        .limit(limit)
        .all()
    )

    return BlindspotResponse(
        notice=BLINDSPOT_NOTICE,
        items=[
            BlindspotItem(
                area_id=commercial.area_id,
                industry_id=commercial.industry_id,
                dong=area,
                category=industry,
                store_count=commercial.store_count,
                cumulative_closure_count=commercial.closure_count_cum4 or 0,
                cumulative_closure_rate_pct=_pct(commercial.closure_rate_cum4),
            )
            for commercial, area, industry in rows
        ],
        total_cells=len(all_rows),
        total_stores=total_stores,
        total_closures=total_closures,
        store_share_pct=round(total_stores / city_stores * 100, 1) if city_stores else 0.0,
        sample_min=SAMPLE_MIN,
    )


@router.get(
    "/{prediction_id}/contributions",
    response_model=PredictionExplanationResponse,
)
def get_prediction_contributions(
    prediction_id: int,
    db: Session = Depends(get_db),
):
    prediction = db.get(RiskPrediction, prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="예측 결과가 없습니다")
    rows = (
        db.query(PredictionContribution)
        .filter(PredictionContribution.prediction_id == prediction_id)
        .order_by(PredictionContribution.rank)
        .all()
    )
    return PredictionExplanationResponse(
        notice=EXPLANATION_NOTICE,
        contributions=rows,
    )
