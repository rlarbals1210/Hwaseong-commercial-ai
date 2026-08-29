import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import case, func
from typing import Optional
from ..auth.dependencies import get_current_official
from ..database import get_db
from ..models import (
    AdminArea,
    AreaPopulationQuarter,
    AreaQuarterSummary,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    PredictionContribution,
    RiskPrediction,
)
from ..schemas import (
    AreaDetailResponse,
    AreaIndustryItem,
    BlindspotCoverageItem,
    BlindspotCoverageResponse,
    BlindspotIndustryItem,
    BlindspotIndustryResponse,
    BlindspotItem,
    BlindspotResponse,
    ClosureRiskItem,
    ClosureRateRankingItem,
    PredictionExplanationResponse,
    VacancyRiskItem,
)
from ..services.compare import closure_interval_pct, cumulative_denominator, two_proportion_z
from ..services.explain import EXPLANATION_NOTICE
from ..services.risk import (
    AREA_HOLD_LEVEL,
    AREA_HOLD_NOTICE,
    AREA_MIN_SUFFICIENT_CELLS,
    AREA_THIN_EVIDENCE_CELLS,
    AREA_THIN_NOTICE,
    AVG_CLOSURE_RATE_PCT,
    CAUTION_THRESHOLD_PCT,
    pct,
    CELL_TYPE_CLOSE_CUT_PCT,
    CELL_TYPE_OPEN_CUT_PCT,
    ELIGIBLE_CELLS,
    DANGER_THRESHOLD_PCT,
    GRADE_NOTICE,
    LATEST_QUARTER,
    PROVISIONAL_NOTICE,
    SAMPLE_MIN,
    WINDOW_QUARTERS,
    action_message,
    quarter_label,
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


# services.risk.pct를 쓴다. 라우터마다 사본을 두면 한쪽만 고쳐졌을 때 같은 셀이
# 화면에 따라 "—"와 "0.00%"로 다르게 뜬다 — 0.00%는 "가장 안전한 값"으로 읽힌다.
_pct = pct

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(get_current_official)])


@router.get("/closure-risk", response_model=list[ClosureRiskItem])
def get_closure_risk(
    # 상한을 50에서 500으로 올렸다(2026-08-29). 담당자가 "10개 말고 더" 요구했고, 판정 셀이
    # 382개라 50으로는 전체를 못 받는다. CSV 다운로드도 화면에 뜬 만큼만 나가고 있었다.
    limit: int = Query(10, ge=1, le=500),
    category: Optional[str] = Query(None),
    # 읍면동 필터 — 봉담읍 담당자는 봉담읍만 본다. 목록을 늘리는 것보다 이쪽이 실사용에 가깝다.
    dong: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """조기경보(예측) — AI 예측 폐업률로 셀 순위만 매긴다. 예측 절대값은 응답에 없음
    (예측폐업률이 실제 관측치보다 구조적으로 ~2.4배 높게 나오는 게 확인되어, 화면에 노출하면
    오해를 줌 — 순위만 신뢰할 수 있는 정보). 실제 관측 지표는 팩트로 그대로 병기.

    2026-08-20: 병기하는 관측 폐업률을 단일 분기에서 4분기 누적으로 바꿨다. 단일 분기는
    점포 60곳짜리 셀에서 폐업 1~2건 차이로 1.5%와 9.0%를 오가서, "1순위인데 폐업률이 1.5%"
    같은 모순이 화면에 그대로 노출됐다. 순위(예측)와 근거(관측)가 서로 어긋나 보이지 않게
    누적값을 쓴다. 단일 분기 값은 참고용으로 함께 준다.

    정렬은 모델 순위(predicted_rank)를 그대로 쓴다.

    2026-08-29 재검증(ai/validate_ranking.py, 표본 기준 30) — 과거 시점 순위를 그 뒤
    4분기 실제 폐업률과 맞춘 결과 스피어만은 모델 0.349 / 관측 0.268 / 앙상블 0.338,
    리프트는 1.291 / 1.242 / 1.274였다(384셀 기준). 표본 기준 50이던 시절의 값은
    0.324 / 1.180이었고, 기준을 내린 뒤 두 지표 모두 올랐다.
    지표에 따라 승자가 갈리고 차이가 오차 수준이라
    성능으로는 못 고른다. 모델 단독을 택한 이유는 화면 정체성이다 — 조기경보는
    "모델이 본 2분기 뒤", 현장 확인은 "이미 관측된 최근 1년"으로 갈라놓았고 화면에
    그렇게 안내한다. 여기에 관측을 섞으면 그 구분이 흐려진다."""
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
    if dong:
        q = q.filter(AdminArea.area_name == dong)
    rows = q.order_by(RiskPrediction.predicted_rank.asc()).limit(limit).all()

    result = []
    for prediction, commercial, dong, industry in rows:
        level = commercial.risk_grade or "안정"
        interval = closure_interval_pct(commercial) or {}
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
            closure_lower_pct=interval.get("lower_pct"),
            closure_upper_pct=interval.get("upper_pct"),
            interval_approximate=bool(interval.get("approximate", False)),
            risk_grade=level,
            cell_type=commercial.cell_type,
            cell_type_summary=CELL_TYPES.get(commercial.cell_type, {}).get("summary"),
            cell_type_advice=CELL_TYPES.get(commercial.cell_type, {}).get("advice"),
            cell_type_avoid=CELL_TYPES.get(commercial.cell_type, {}).get("avoid") or None,
            quarter_closure_rate_pct=_pct(commercial.closure_rate),
            # 유형 판정이 쓰는 보정값. 원본은 표본충분 셀의 26.8%가 0.0%로 나온다.
            open_rate_pct=_pct(commercial.opening_rate_ma4),
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
    # rate = 절대 폐업률 순(기본), excess = 업종 평균 대비 초과폭 순.
    sort: str = Query("rate", pattern="^(rate|excess)$"),
    db: Session = Depends(get_db),
):
    """상권 순위표(현황) — 4분기 누적 관측 폐업률. 보정·예측 관여 없음.

    정렬 기준을 표시값과 일치시킨다. 신뢰하한으로 정렬하는 안도 검증했으나 4분기 누적에서는
    상위 10개가 동일하게 나왔다(누적 분모가 이미 충분히 커서 소표본 보정이 순서를 바꾸지 않음).
    표시값과 순서가 어긋나는 쪽이 담당자에게 더 혼란스러워 누적률 정렬을 택했다.
    하한은 근거로 함께 준다.

    업종 내 순위를 병기한다 — 전체 순위만 두면 목록이 한 업종으로 덮인다(실측: 위험 24개 중
    18개가 교육 계열).

    sort=excess (2026-08-29 추가) — 병기만으로는 부족했다. 표본 기준을 30으로 내린 뒤에도
    절대 폐업률 상위 20개 중 13개가 교육 계열이었고, 매번 같은 목록이면 담당자가 두 번째부터
    열어볼 이유가 없다. 편중은 데이터 결함이 아니라 실제 현상이므로(학원가가 점포의 14.9%인데
    폐업의 28.8%) 값을 건드리지 않고 정렬 축을 하나 더 준다.

    초과폭 = 셀 누적폐업률 - 그 업종의 화성시 전체 누적폐업률. 이 축에서는 상위 20개 중
    교육이 2개로 줄고, 대신 "종합소매는 시 평균 4.99%인데 동탄2동만 10.49%(2.1배)" 같은
    줄이 올라온다. 현장 확인을 나갈 이유로는 후자가 명확하다.

    기준선은 표본부족 셀까지 포함한 업종 전체에서 낸다. 우리가 판정한 셀만으로 기준을 만들면
    "판정 가능한 셀들의 평균 대비 판정 가능한 셀"이라는 순환이 된다.
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

    # 업종별 기준선 — 표본부족 셀까지 포함한다(위 docstring 참조).
    industry_totals: dict[str, list[float]] = {}
    for commercial, industry in (
        db.query(CommercialQuarter, IndustryCategory.industry_name)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(CommercialQuarter.quarter_code == latest)
        .all()
    ):
        denominator, _approximate = cumulative_denominator(commercial)
        if not denominator:
            continue
        acc = industry_totals.setdefault(industry, [0.0, 0.0])
        acc[0] += commercial.closure_count_cum4 or 0
        acc[1] += denominator
    industry_avg: dict[str, float] = {
        name: round(closures / denominator * 100, 2)
        for name, (closures, denominator) in industry_totals.items()
        if denominator > 0
    }

    q = base
    if category:
        q = q.filter(IndustryCategory.industry_name == category)

    # 초과폭은 저장 컬럼이 아니라 파생값이라 DB에서 정렬할 수 없다. 판정 셀이 400개 미만이므로
    # 전부 가져와 파이썬에서 정렬한 뒤 자른다.
    scored = []
    for commercial, dong, industry in q.all():
        rate = _pct(commercial.closure_rate_cum4)
        average = industry_avg.get(industry)
        excess = round(rate - average, 2) if rate is not None and average is not None else None
        ratio = (
            round(rate / average, 2)
            if rate is not None and average not in (None, 0)
            else None
        )
        scored.append((commercial, dong, industry, rate, average, excess, ratio))

    if sort == "excess":
        # 기준선이 없는 셀(분모 복원 실패)은 뒤로 보낸다. 0으로 채우면 "평균과 같음"으로 읽힌다.
        scored.sort(key=lambda x: (x[5] is not None, x[5] or 0.0), reverse=True)
    else:
        scored.sort(key=lambda x: x[3] or 0.0, reverse=True)
    scored = scored[:limit]

    result = []
    for i, (commercial, dong, industry, rate, average, excess, ratio) in enumerate(scored, 1):
        rank_in_industry, industry_total = industry_rank.get(commercial.id, (None, None))
        result.append(ClosureRateRankingItem(
            rank=i,
            area_id=commercial.area_id,
            industry_id=commercial.industry_id,
            dong=dong,
            category=industry,
            closure_rate_pct=rate,
            cumulative_closure_count=commercial.closure_count_cum4 or 0,
            confidence_lower_pct=_pct(commercial.closure_rate_lower4),
            store_count=commercial.store_count,
            risk_grade=commercial.risk_grade or "안정",
            industry_avg_pct=average,
            excess_pp=excess,
            excess_ratio=ratio,
            industry_rank=rank_in_industry,
            industry_total=industry_total,
        ))
    return result


@router.get("/grade-notice")
def get_grade_notice(db: Session = Depends(get_db)):
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
        "eligible_cells": ELIGIBLE_CELLS,
        "cell_type_open_cut_pct": CELL_TYPE_OPEN_CUT_PCT,
        "cell_type_close_cut_pct": CELL_TYPE_CLOSE_CUT_PCT,
        "latest_quarter": LATEST_QUARTER,
        "latest_quarter_label": quarter_label(LATEST_QUARTER),
        "provisional_notice": PROVISIONAL_NOTICE,
        # 조기경보 순위를 어디까지 믿을 수 있는가 (2026-08-29 추가).
        #
        # 검증된 것은 "상위 10%의 리프트 1.29배"이지 순위 전체가 아니다. 스피어만 0.349는
        # 약한 양의 상관이라는 뜻이지, 47위가 51위보다 위험하다는 뜻이 아니다. 10개만
        # 보여줄 때는 이 구분이 드러나지 않았는데, 목록을 전부 펼치면 담당자가 47위를
        # 근거로 예산을 배정할 수 있게 된다 — 우리가 검증하지 않은 사용법이다.
        # 그래서 경계를 서버가 내려주고 화면이 그 자리에 선을 긋는다.
        #
        # 경계는 필터와 무관하게 시 전체 순위 기준이다. 봉담읍만 걸러낸 목록의 "상위 10%"는
        # 우리가 검증한 대상이 아니다. 그래서 순위(predicted_rank) 절대값으로 자른다.
        **_ranking_confidence(db),
    }


VALIDATED_TOP_Q = 0.10   # ai/validate_ranking.py의 TOP_PCT와 같은 값이어야 한다


def _ranking_confidence(db: Session) -> dict:
    """조기경보 순위의 검증 구간. validate_ranking.py가 실제로 잰 범위를 화면에 옮긴다."""
    ranked = (
        db.query(func.count(RiskPrediction.id))
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .join(CommercialQuarter, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .filter(
            ModelRun.is_active.is_(True),
            CommercialQuarter.sample_insufficient.is_(False),
            RiskPrediction.predicted_rank.isnot(None),
        )
        .scalar()
    ) or 0
    return {
        "ranked_cells": ranked,
        "validated_top_pct": int(VALIDATED_TOP_Q * 100),
        "validated_top_rank": max(1, round(ranked * VALIDATED_TOP_Q)) if ranked else None,
        "validated_lift": 1.29,   # ai/validate_ranking.py 재현값(표본 기준 30, 384셀)
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

    # 색은 frontend/src/index.css의 팔레트와 같은 값이어야 한다. 예전에는 여기 값과
    # 범례의 CSS 변수가 서로 달라(#D51B4C vs --error #ba1a1a) 폴리곤 색과 범례 점 색이
    # 한 화면에서 어긋났다(2026-08-25 감사).
    colors = {
        "안정": "#1aae39",          # --accent-green
        "주의": "#dd5b00",          # --accent-orange
        "위험": "#ba1a1a",          # --error
        AREA_HOLD_LEVEL: "#c1c6d5",  # --outline-variant
    }

    result = []
    for summary, dong in rows:
        # 저장된 등급을 그대로 믿지 않고 분모를 여기서 다시 본다. 파이프라인을 다시 돌리지
        # 않아도 화면이 바로 교정되고, 적재 로직이 바뀌어도 화면 쪽 방어가 남는다.
        judged = summary.sample_sufficient_cells >= AREA_MIN_SUFFICIENT_CELLS
        thin = judged and summary.sample_sufficient_cells < AREA_THIN_EVIDENCE_CELLS
        level = (summary.area_risk_grade or "안정") if judged else AREA_HOLD_LEVEL
        result.append(
            VacancyRiskItem(
                dong=dong,
                area_id=summary.area_id,
                risk_ratio=summary.risk_industry_ratio_pct if judged else None,
                risk_level=level,
                color=colors.get(level, "#c1c6d5"),
                trend=round(summary.avg_trend_slope or 0.0, 3),
                total_cells=summary.total_cells,
                sample_sufficient_cells=summary.sample_sufficient_cells,
                coverage_pct=round(
                    summary.sample_sufficient_cells / summary.total_cells * 100, 1
                ) if summary.total_cells else 0.0,
                evidence_thin=thin,
                hold_notice=(
                    AREA_THIN_NOTICE if thin else (None if judged else AREA_HOLD_NOTICE)
                ),
            )
        )
    return sorted(result, key=lambda item: item.dong)


# ────────────────────────────────────────────────────────────────────────────
# 읍면동 상세
#
# 지도에서 동을 누르면 "위험 업종 비율 0.0%"와 표본 충족률만 뜨고 끝났다. 담당자의 다음
# 질문은 반드시 "그래서 어느 업종인가"인데 화면에서 동선이 끊겼다.
#
# 여기서 세 가지를 한 번에 답한다 —
#   ① 어느 업종이 나쁜가       업종 목록(표본충분 셀, 폐업률 순)
#   ② 동 전체로는 어떤가       업종 구분 없이 묶은 폐업률 + 나머지 지역과의 비교
#   ③ 무엇이 안 보이는가       사각지대 규모
# 배후 여건(등록인구)은 판정 축이 아니라 원인의 방향을 좁히는 참고 자료로만 붙인다.


@router.get("/area/{area_id}/detail", response_model=AreaDetailResponse)
def get_area_detail(area_id: int, db: Session = Depends(get_db)):
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")

    area = db.query(AdminArea).filter(AdminArea.id == area_id).one_or_none()
    if area is None:
        raise HTTPException(status_code=404, detail="해당 읍면동을 찾을 수 없습니다")

    rows = (
        db.query(CommercialQuarter, IndustryCategory.industry_name)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == latest,
            CommercialQuarter.area_id == area_id,
        )
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="해당 읍면동의 분기 데이터가 없습니다")

    industries = [
        AreaIndustryItem(
            area_id=area_id,
            industry_id=cell.industry_id,
            category=name,
            store_count=cell.store_count,
            cumulative_closure_rate_pct=_pct(cell.closure_rate_cum4),
            cumulative_closure_count=cell.closure_count_cum4,
            risk_grade=cell.risk_grade,
            cell_type=cell.cell_type,
        )
        for cell, name in rows
        if not cell.sample_insufficient and cell.closure_rate_cum4 is not None
    ]
    industries.sort(key=lambda item: item.cumulative_closure_rate_pct or 0, reverse=True)

    total_cells = len(rows)
    sufficient = len(industries)
    total_stores = sum(cell.store_count for cell, _ in rows)
    blind = [cell for cell, _ in rows if cell.sample_insufficient]

    # 동 단위 폐업률 — 셀별 분모를 복원해 합산한다. 누적 비율은 건수합/분모합이므로
    # 동 전체 분모도 셀 분모의 합이어야 한다. 업종별로는 표본이 모자란 동도 이 단위에서는
    # 분모가 수천이 되어 판정할 수 있다(기배동 1,855).
    pooled_count = 0
    pooled_denominator = 0
    for cell, _ in rows:
        denominator, _approx = cumulative_denominator(cell)
        if denominator:
            pooled_count += cell.closure_count_cum4 or 0
            pooled_denominator += denominator

    # 대조군은 "시 전체"가 아니라 "이 동을 뺀 나머지"다. 자기 자신을 포함한 평균과 비교하면
    # 큰 동일수록 차이가 희석된다(동탄1동은 분모가 시 전체의 9%).
    city_count = 0
    city_denominator = 0
    for cell in (
        db.query(CommercialQuarter)
        .filter(CommercialQuarter.quarter_code == latest)
        .all()
    ):
        denominator, _approx = cumulative_denominator(cell)
        if denominator:
            city_count += cell.closure_count_cum4 or 0
            city_denominator += denominator

    pooled_rate = round(pooled_count / pooled_denominator * 100, 2) if pooled_denominator else None
    city_rate = round(city_count / city_denominator * 100, 2) if city_denominator else None

    verdict = "차이없음"
    z_value = None
    rest_count = city_count - pooled_count
    rest_denominator = city_denominator - pooled_denominator
    if pooled_denominator and rest_denominator > 0:
        z = two_proportion_z(pooled_count, pooled_denominator, rest_count, rest_denominator)
        if z is not None:
            higher = pooled_count / pooled_denominator > rest_count / rest_denominator
            z_value = round(z if higher else -z, 2)
            if z >= 1.96:
                verdict = "높음" if higher else "낮음"

    population = (
        db.query(AreaPopulationQuarter)
        .filter(
            AreaPopulationQuarter.area_id == area_id,
            AreaPopulationQuarter.total_population.isnot(None),
        )
        .order_by(AreaPopulationQuarter.quarter_code)
        .all()
    )
    pop_fields: dict = {}
    if population:
        window = population[-13:]   # 3년 + 기준점
        first, last = window[0], window[-1]
        pop_fields = {
            "population": last.total_population,
            "population_change_pct": (
                round((last.total_population - first.total_population) / first.total_population * 100, 1)
                if first.total_population else None
            ),
            "population_from_label": quarter_label(first.quarter_code),
            "population_to_label": quarter_label(last.quarter_code),
        }

    return AreaDetailResponse(
        area_id=area_id,
        dong=area.area_name,
        quarter_code=latest,
        quarter_label=quarter_label(latest),
        total_cells=total_cells,
        sample_sufficient_cells=sufficient,
        coverage_pct=round(sufficient / total_cells * 100, 1) if total_cells else 0.0,
        risk_cells=sum(1 for item in industries if item.risk_grade == "위험"),
        caution_cells=sum(1 for item in industries if item.risk_grade == "주의"),
        pooled_closure_rate_pct=pooled_rate,
        pooled_closure_count=pooled_count,
        city_pooled_closure_rate_pct=city_rate,
        vs_city=verdict,
        vs_city_z=z_value,
        blindspot_cells=len(blind),
        blindspot_stores=sum(cell.store_count for cell in blind),
        total_stores=total_stores,
        industries=industries,
        **pop_fields,
    )


BLINDSPOT_NOTICE = (
    "표본이 작아 통계적 판단을 보류한 상권입니다. 모델이 판단하지 않으며, "
    "폐업 건수 순으로 정렬했습니다. 현장 확인을 권장합니다."
)


# ────────────────────────────────────────────────────────────────────────────
# 사각지대의 모양
#
# "전체 점포의 38%가 안 보인다"는 한 숫자로는 구멍이 어디에 뚫려 있는지 알 수 없다.
# 두 축으로 나눠 보면 구조가 드러난다 —
#   지역 축: 기배동·매송면 커버율 0%, 동탄1동 35.1% (농촌·구도심에 몰려 있다)
#   업종 축: 74개 업종 중 41개가 화성시 전역에서 판단 가능 셀 0개
#
# 이걸 화면이 스스로 드러내는 편이 낫다. 정책 우선순위를 고르는 도구가 도시 지역에
# 편향돼 있다는 지적은 어차피 나오고, 우리가 먼저 재어 보여주면 한계 고지가 되지만
# 감추면 결함이 된다.

BLINDSPOT_SHAPE_NOTICE = (
    f"점포 {SAMPLE_MIN}곳 미만이라 통계 판단을 보류한 상권의 분포입니다. "
    "커버율이 낮다고 그 지역·업종이 더 위험하다는 뜻은 아닙니다. "
    "우리가 판단할 근거를 갖지 못했다는 뜻입니다."
)

# 문턱 근처 구간의 하한. 기준(50)의 60%다. 그 이상의 통계적 근거는 없고,
# "조금만 더 모이면 판단 가능한 상권"을 점포 3곳짜리와 갈라놓는 것이 목적이다.
# 화면에도 이 근거를 그대로 적는다 — 없는 이유를 지어내지 않는다.
NEAR_THRESHOLD_RATIO = 0.6
NEAR_MIN_STORES = int(SAMPLE_MIN * NEAR_THRESHOLD_RATIO)


@router.get("/blindspots/coverage", response_model=BlindspotCoverageResponse)
def get_blindspot_coverage(db: Session = Depends(get_db)):
    """읍면동별 커버율 — 사각지대의 지역 축.

    셀 수는 area_quarter_summaries에 이미 집계돼 있지만 점포 수는 없다. 점포 기준 비중이
    더 중요해서(셀 하나가 점포 3곳일 수도 400곳일 수도 있다) commercial_quarters에서
    같이 집계한다.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return BlindspotCoverageResponse(
            notice=BLINDSPOT_SHAPE_NOTICE, sample_min=SAMPLE_MIN, items=[], zero_coverage_dongs=[]
        )

    rows = (
        db.query(
            AdminArea.area_name,
            func.count(CommercialQuarter.id).label("total_cells"),
            func.sum(
                case((CommercialQuarter.sample_insufficient.is_(False), 1), else_=0)
            ).label("sufficient_cells"),
            func.sum(CommercialQuarter.store_count).label("total_stores"),
            func.sum(
                case((CommercialQuarter.sample_insufficient.is_(True), CommercialQuarter.store_count), else_=0)
            ).label("blindspot_stores"),
            func.sum(func.coalesce(CommercialQuarter.closure_count_cum4, 0)).label("closure_count"),
        )
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .filter(CommercialQuarter.quarter_code == latest)
        .group_by(AdminArea.area_name)
        .all()
    )

    # 동 단위 누적 폐업률의 분모. 셀마다 복원해서 더한다 — 누적 비율은 건수합/분모합이라
    # 동 전체 분모도 셀 분모의 합이어야 한다. 셀별 분모는 건수/비율로 복원되고,
    # 폐업 0건인 셀만 점포수 x 4로 근사한다(services/compare.cumulative_denominator).
    denominators: dict[str, int] = {}
    for commercial, dong_name in (
        db.query(CommercialQuarter, AdminArea.area_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .filter(CommercialQuarter.quarter_code == latest)
        .all()
    ):
        n, _approx = cumulative_denominator(commercial)
        if n:
            denominators[dong_name] = denominators.get(dong_name, 0) + n

    items = []
    city_closures = 0
    city_denominator = 0
    for name, total_cells, sufficient, total_stores, blind_stores, closures in rows:
        total_cells = int(total_cells or 0)
        sufficient = int(sufficient or 0)
        total_stores = int(total_stores or 0)
        blind_stores = int(blind_stores or 0)
        closures = int(closures or 0)
        denominator = denominators.get(name, 0)
        city_closures += closures
        city_denominator += denominator
        items.append(BlindspotCoverageItem(
            dong=name,
            total_cells=total_cells,
            sufficient_cells=sufficient,
            coverage_pct=round(sufficient / total_cells * 100, 1) if total_cells else 0.0,
            total_stores=total_stores,
            blindspot_stores=blind_stores,
            blindspot_store_pct=round(blind_stores / total_stores * 100, 1) if total_stores else 0.0,
            pooled_closure_rate_pct=round(closures / denominator * 100, 2) if denominator else None,
            pooled_closure_count=closures,
            pooled_denominator=denominator,
        ))

    # 안 보이는 곳이 위로. 이 화면의 주어는 "판단 가능한 곳"이 아니라 "판단 못 하는 곳"이다.
    # 시 전체 합계가 나온 뒤에야 비교가 가능해서 두 번째 패스에서 채운다.
    # 대조군은 "시 전체"가 아니라 "그 동을 뺀 나머지"다. 자기 자신을 포함한 평균과
    # 비교하면 큰 동(동탄1동은 분모가 시 전체의 9%)일수록 차이가 희석된다.
    for item in items:
        if not item.pooled_denominator:
            continue
        rest_count = city_closures - item.pooled_closure_count
        rest_denominator = city_denominator - item.pooled_denominator
        if rest_denominator <= 0:
            continue
        z = two_proportion_z(
            item.pooled_closure_count, item.pooled_denominator, rest_count, rest_denominator
        )
        if z is None:
            continue
        # two_proportion_z는 절대값을 돌려준다. 방향은 비율을 직접 비교해 붙인다.
        higher = item.pooled_closure_count / item.pooled_denominator > rest_count / rest_denominator
        item.vs_city_z = round(z if higher else -z, 2)
        if z >= 1.96:
            item.vs_city = "높음" if higher else "낮음"

    items.sort(key=lambda item: (item.coverage_pct, -item.blindspot_store_pct))
    return BlindspotCoverageResponse(
        notice=BLINDSPOT_SHAPE_NOTICE,
        sample_min=SAMPLE_MIN,
        items=items,
        zero_coverage_dongs=[item.dong for item in items if item.sufficient_cells == 0],
        city_pooled_closure_rate_pct=(
            round(city_closures / city_denominator * 100, 2) if city_denominator else None
        ),
    )


@router.get("/blindspots/industries", response_model=BlindspotIndustryResponse)
def get_blindspot_industries(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """업종별 커버율 — 사각지대의 업종 축.

    읍면동마다 조금씩 흩어져 있는 업종은 어느 셀도 기준을 못 넘어 화면에서 통째로
    사라진다. 식물 소매는 화성시에 300곳 넘게 있고 최근 4분기 폐업 건수도 세 자리인데
    판단 가능 셀이 0개다.

    폐업은 건수만 낸다. 누적 분모(4개 분기 직전점포수 합)를 같이 주면 화면이 그걸로
    폐업률을 계산할 텐데, 표본부족 셀의 률은 애초에 쓰지 않기로 한 값이다.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return BlindspotIndustryResponse(
            notice=BLINDSPOT_SHAPE_NOTICE, sample_min=SAMPLE_MIN, items=[],
            invisible_count=0, industry_total=0,
        )

    rows = (
        db.query(
            IndustryCategory.industry_name,
            func.count(CommercialQuarter.id).label("total_cells"),
            func.sum(
                case((CommercialQuarter.sample_insufficient.is_(False), 1), else_=0)
            ).label("sufficient_cells"),
            func.sum(CommercialQuarter.store_count).label("total_stores"),
            func.sum(func.coalesce(CommercialQuarter.closure_count_cum4, 0)).label("closure_count"),
        )
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(CommercialQuarter.quarter_code == latest)
        .group_by(IndustryCategory.industry_name)
        .all()
    )

    parsed = []
    for name, total_cells, sufficient, total_stores, closures in rows:
        total_cells = int(total_cells or 0)
        sufficient = int(sufficient or 0)
        parsed.append(BlindspotIndustryItem(
            category=name,
            total_cells=total_cells,
            sufficient_cells=sufficient,
            coverage_pct=round(sufficient / total_cells * 100, 1) if total_cells else 0.0,
            total_stores=int(total_stores or 0),
            closure_count=int(closures or 0),
        ))

    invisible_count = sum(1 for item in parsed if item.sufficient_cells == 0)
    # 커버율이 낮은 순, 같으면 점포가 많은 순 — 규모가 큰데 안 보이는 업종이 제일 아프다.
    parsed.sort(key=lambda item: (item.coverage_pct, -item.total_stores))
    return BlindspotIndustryResponse(
        notice=BLINDSPOT_SHAPE_NOTICE,
        sample_min=SAMPLE_MIN,
        items=parsed[:limit],
        invisible_count=invisible_count,
        industry_total=len(parsed),
    )


def _blindspot_item(commercial, dong: str, industry: str) -> BlindspotItem:
    """목록 한 줄. 등급 대신 신뢰구간을 함께 싣는다.

    구간은 모든 구간에 대해 계산하되 화면이 문턱 근처에서만 쓴다. 점포 10곳 미만
    구간은 폭이 중위 25.9%p라(위험 기준선의 2.5배) 숫자를 띄우는 것 자체가 오해를 만든다.
    잘라내는 판단은 화면 쪽에 두고 API는 사실을 그대로 준다.
    """
    interval = closure_interval_pct(commercial) or {}
    return BlindspotItem(
        area_id=commercial.area_id,
        industry_id=commercial.industry_id,
        dong=dong,
        category=industry,
        store_count=commercial.store_count,
        cumulative_closure_count=commercial.closure_count_cum4 or 0,
        cumulative_closure_rate_pct=_pct(commercial.closure_rate_cum4),
        closure_lower_pct=interval.get("lower_pct"),
        closure_upper_pct=interval.get("upper_pct"),
        interval_approximate=bool(interval.get("approximate", False)),
    )


@router.get("/blindspots", response_model=BlindspotResponse)
def get_blindspots(
    limit: int = Query(30, ge=1, le=200),
    dong: Optional[str] = Query(None),
    # near = 문턱 근처(점포 NEAR_MIN_STORES ~ SAMPLE_MIN-1). 점포 47곳짜리와 3곳짜리는
    # 같은 표에 있으면 안 된다 — 전자는 "거의 다 왔다", 후자는 "원리상 못 본다"다.
    band: str = Query("all", pattern="^(all|near)$"),
    db: Session = Depends(get_db),
):
    """사각지대 — 표본부족으로 등급·순위에서 빠진 셀.

    조회 기준(ai/build_risk_index.py의 SAMPLE_MIN)을 넘지 못하면 화면에서 아예 사라진다.
    숫자를 여기 적지 않는 이유는 그 상수가 바뀌기 때문이다 — 실제로 2026-08-29에 50에서
    30으로 내렸고, 그 시점에 사각지대 점포 비중은 38%에서 25%로, 커버율 0%인 읍면동은
    기배동·매송면 2곳에서 0곳으로 줄었다. 그래도 사각지대는 남는다. 아무리 상황이 나빠도
    후보에 못 오르는 상권이 있다는 뜻이고, 정책 우선순위를 고르는 도구에서 이건 형평성
    문제로 직결된다.

    통계 판단은 계속 보류하되(등급을 매기지 않는다) 목록에서 지우지는 않는다.
    """
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not latest:
        return BlindspotResponse(
            notice=BLINDSPOT_NOTICE, items=[], total_cells=0, total_stores=0,
            total_closures=0, store_share_pct=0.0, city_stores=0, sample_min=SAMPLE_MIN,
            band=band, band_cells=0, band_stores=0, near_min_stores=NEAR_MIN_STORES,
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
    if band == "near":
        q = q.filter(CommercialQuarter.store_count >= NEAR_MIN_STORES)

    # 탭 라벨에 개수를 박으려면 필터 적용 후 총계가 따로 필요하다. 상단 지표 4개는
    # 구간과 무관하게 전체 사각지대 기준을 유지한다 — 탭을 옮길 때마다 "38%"가
    # 흔들리면 그게 무엇의 38%인지 알 수 없어진다.
    band_rows = q.all()
    band_cells = len(band_rows)
    band_stores = sum(commercial.store_count for commercial, _, _ in band_rows)

    rows = (
        q.order_by(CommercialQuarter.closure_count_cum4.desc())
        .limit(limit)
        .all()
    )

    return BlindspotResponse(
        notice=BLINDSPOT_NOTICE,
        items=[
            _blindspot_item(commercial, area, industry)
            for commercial, area, industry in rows
        ],
        total_cells=len(all_rows),
        total_stores=total_stores,
        total_closures=total_closures,
        store_share_pct=round(total_stores / city_stores * 100, 1) if city_stores else 0.0,
        city_stores=int(city_stores),
        sample_min=SAMPLE_MIN,
        band=band,
        band_cells=band_cells,
        band_stores=band_stores,
        near_min_stores=NEAR_MIN_STORES,
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
