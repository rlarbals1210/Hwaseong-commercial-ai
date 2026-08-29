"""창업 적합도 추천 — 공개 화면(로그인 없음).

## 왜 공개인가 (2026-08-26 결정)

`public.py` 맨 위는 원래 "예측 순위·성장확률은 어떤 형태로도 내지 않는다"고 선언했다.
그 원칙은 **기존 소상공인의 자가진단**("내 가게가 위험한가")을 막기 위한 것이었고,
2026-08-18에 시민 조회 기능을 제거한 근거이기도 하다.

예비 창업자는 다른 경우다. 아직 가게가 없으니 "동과 업종을 고른다"가 자연스러운 행동이고
그것이 이 데이터의 단위와 정확히 일치한다. `public.py`의 docstring도 이 영역을 "8/18
결정이 다루지 않은 영역"이라고 이미 적어 두었다. 그래서 추천은 공개한다.

**다만 성장확률은 `(1 - 예측폐업률) x 100`이라, 성장확률 등급을 공개하는 것은 예측
폐업률 상위 25%를 공개하는 것과 같다.** "성장확률만 내니 낙인이 아니다"는 성립하지 않는다.
그래서 낙인의 단위를 통제하는 쪽으로 조건을 걸었다.

1. **등급은 셀(읍면동 x 업종) 단위로만 낸다.** "동탄1동 D등급"은 그 동네 상인 전체에
   대한 낙인이지만 "동탄1동 한식은 27곳 중 22위"는 창업 준비자에게 필요한 정보다.
   읍면동 하나를 한 등급으로 요약하는 응답은 이 라우터에 두지 않는다
   (공무원 화면의 `공실위험지수`가 그 역할이고, 그건 로그인 뒤에 있다).
2. **지도 색칠은 등급이 아니라 관측치로 한다.** `/api/public/industry-map`이 이미 그렇다.
3. **표본이 작은 셀도 숨기지 않는다.** 대신 점포 수에 비례해 원점수를
   50점(중립)쪽으로 보정하고, 근거 수준을 점수와 함께 낸다. 동종업종이
   관측되지 않은 지역은 목록에는 남기되 점수나 순위를 매기지 않는다.
4. **면책 문구를 응답에 담는다.** 프론트에 박으면 문구가 두 곳에 생긴다.

계산은 전부 `backend/services/recommend.py`에 있다. 여기서는 조회와 응답 조립만 한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AdminArea, CommercialQuarter, StoreCluster
from ..schemas import (
    RecommendationAreaListResponse,
    RecommendationIndustryListResponse,
    RecommendationPresetsResponse,
    RecommendationScoreResponse,
    StoreClusterResponse,
)
from ..services import recommend as R
from ..services.risk import SAMPLE_MIN, WINDOW_QUARTERS, pct, quarter_label

router = APIRouter(prefix="/api/recommend", tags=["recommend"])

DISCLAIMER = (
    "본 추천은 공공데이터로 계산한 읍면동 x 업종 단위 통계이며, 특정 점포의 성패를 "
    "예측하지 않습니다. 실제 창업 전에 현장 확인을 병행하시기 바랍니다."
)
RELATIVE_NOTICE = (
    f"점수는 이 목록 안에서의 상대값입니다. 점포 {SAMPLE_MIN}곳 미만은 작은 표본이 순위를 "
    "과도하게 흔들지 않도록 50점 쪽으로 보정했습니다. 등급은 절대 기준이 아니라 "
    "같은 업종 안에서의 상대 순위입니다."
)
CLUSTER_PUBLIC_MIN = 3


def _relative_notice() -> str:
    return f"{RELATIVE_NOTICE} {R.demand_notice()}"


def _latest_quarter(db: Session) -> int:
    from sqlalchemy import func

    quarter = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not quarter:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")
    return quarter


def _rows(db: Session, quarter: int, *, area_id: int | None = None, industry_id: int | None = None):
    """활성 모델런의 예측이 붙은 셀만 가져온다. 예측이 없으면 점수를 못 매긴다."""
    return R.load_rows(db, quarter, area_id=area_id, industry_id=industry_id)


def _to_candidates(rows) -> tuple[list[R.Candidate], int]:
    """예측과 관측치가 있는 셀을 모두 후보로 옮긴다."""
    candidates, limited = [], 0
    for cell, model_rate, area_name, industry_name in rows:
        if cell.sample_insufficient:
            limited += 1
        # 성장확률 = (1 - 예측폐업률) x 100. 원본 내부값은 그대로 내리지 않는다.
        growth = round((1.0 - float(model_rate)) * 100, 1)
        demand_signal = R.demand_signal_for(area_name, industry_name)
        candidates.append(R.Candidate(
            area_id=cell.area_id,
            area_name=area_name,
            industry_id=cell.industry_id,
            industry_name=industry_name,
            growth_prob=growth,
            store_count=cell.store_count,
            saturation=cell.saturation_rate,
            closure_rate_cum4_pct=pct(cell.closure_rate_cum4),
            closure_count_cum4=cell.closure_count_cum4,
            opening_rate_pct=pct(cell.opening_rate_ma4),
            tenure_quarters=(
                round(cell.avg_tenure_quarters, 1) if cell.avg_tenure_quarters is not None else None
            ),
            cell_type=cell.cell_type,
            sample_insufficient=bool(cell.sample_insufficient),
            demand_gap=demand_signal["gap"] if demand_signal else None,
            demand_mapping_level=demand_signal["mapping_level"] if demand_signal else None,
        ))
    return candidates, limited


def _append_unobserved_areas(
    db: Session,
    candidates: list[R.Candidate],
    *,
    industry_id: int,
    industry_name: str,
) -> None:
    """선택 업종이 관측되지 않은 읍면동도 목록에 남긴다.

    값이 없는 것을 '경쟁이 없는 블루오션'으로 오인하지 않도록 이 후보들은
    점수와 순위가 None인 동종업종 미관측로만 내린다.
    """
    present = {candidate.area_id for candidate in candidates}
    for area in db.query(AdminArea).order_by(AdminArea.area_name).all():
        if area.id in present:
            continue
        candidates.append(R.Candidate(
            area_id=area.id,
            area_name=area.area_name,
            industry_id=industry_id,
            industry_name=industry_name,
            growth_prob=None,
            store_count=0,
            saturation=None,
            closure_rate_cum4_pct=None,
            closure_count_cum4=None,
            opening_rate_pct=None,
            tenure_quarters=None,
            cell_type=None,
            sample_insufficient=True,
        ))


def _observed(c: R.Candidate) -> dict:
    """관측 지표. 예측만 보여주면 방어가 안 되므로 항상 병기한다."""
    stable = c.evidence_key == "sufficient"
    return {
        "closure_rate_cum4_pct": c.closure_rate_cum4_pct if stable else None,
        "closure_count_cum4": c.closure_count_cum4,
        "store_count": c.store_count,
        "opening_rate_pct": c.opening_rate_pct if stable else None,
        "tenure_quarters": c.tenure_quarters,
        "cell_type": c.cell_type if stable else None,
    }


def _evidence(c: R.Candidate) -> dict:
    return {
        "evidence_key": c.evidence_key,
        "evidence_label": c.evidence_label,
        "data_weight_pct": round(c.data_weight * 100),
        "score_adjusted": c.score is not None and c.data_weight < 1.0,
        "adjustment_note": c.adjustment_note,
    }


@router.get("/presets", response_model=RecommendationPresetsResponse)
def list_presets():
    """가중치 프리셋. 프론트에 박지 말고 여기서 받는다."""
    return {
        "default": R.DEFAULT_PRESET,
        "presets": [
            {"key": key, "label": v["label"], "description": v["description"], "weights": v["weights"]}
            for key, v in R.WEIGHT_PRESETS.items()
        ],
        "axes": [
            {"key": a, "label": R.AXIS_LABELS[a], "desc": R.AXIS_DESCRIPTIONS[a]} for a in R.AXES
        ],
        "notice": (
            "가중치는 고정된 정답이 아닙니다. 폐업 부담 예측과 검증된 카드수요 전망, "
            "경쟁·포화도 중 무엇을 중요하게 볼지 고르실 수 있습니다."
        ),
    }


@router.get("/clusters", response_model=StoreClusterResponse)
def store_clusters(
    industry_id: int = Query(...),
    limit: int = Query(1200, ge=100, le=2000),
    db: Session = Depends(get_db),
):
    """선택 업종의 격자 집계. 개별 좌표와 3개 미만 격자는 공개하지 않는다."""
    quarter = _latest_quarter(db)
    rows = (
        db.query(StoreCluster)
        .filter(
            StoreCluster.quarter_code == quarter,
            StoreCluster.industry_id == industry_id,
        )
        .order_by(StoreCluster.store_count.desc(), StoreCluster.id)
        .all()
    )
    visible = [row for row in rows if row.store_count >= CLUSTER_PUBLIC_MIN]
    returned = visible[:limit]
    return {
        "quarter_code": quarter,
        "industry_id": industry_id,
        "grid_degrees": 0.002,
        "min_cluster_size": CLUSTER_PUBLIC_MIN,
        "clusters": [
            {
                "lat": row.center_lat,
                "lng": row.center_lng,
                "store_count": row.store_count,
            }
            for row in returned
        ],
        "visible_store_count": sum(row.store_count for row in returned),
        "suppressed_store_count": sum(
            row.store_count for row in rows if row.store_count < CLUSTER_PUBLIC_MIN
        ),
        "omitted_cluster_count": max(0, len(visible) - len(returned)),
        "privacy_notice": (
            "개별 점포 위치는 제공하지 않습니다. 0.002도 격자에 3곳 이상 모인 경우만 "
            "격자 중심과 점포 수를 표시합니다."
        ),
    }


@router.get("/areas", response_model=RecommendationAreaListResponse)
def recommend_areas(
    industry_id: int = Query(...),
    preset: str | None = Query(None),
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """업종 하나 → 읍면동 랭킹 (노다지 '업종 → 행정동')."""
    quarter = _latest_quarter(db)
    rows = _rows(db, quarter, industry_id=industry_id)
    if not rows:
        raise HTTPException(status_code=404, detail="해당 업종의 예측 결과가 없습니다")
    industry_name = rows[0][3]
    candidates, _ = _to_candidates(rows)
    _append_unobserved_areas(
        db, candidates, industry_id=industry_id, industry_name=industry_name,
    )
    meta = R.score_candidates(candidates, preset)
    ranked = sorted(
        candidates,
        key=lambda c: (c.rank is None, c.rank if c.rank is not None else 10_000, c.area_name),
    )[:limit]
    sufficient = sum(c.evidence_key == "sufficient" for c in candidates)
    limited = sum(c.evidence_key in {"medium", "low"} for c in candidates)
    unobserved = sum(c.evidence_key == "unobserved" for c in candidates)
    return {
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "window_quarters": WINDOW_QUARTERS,
        "industry_id": industry_id,
        "industry_name": industry_name,
        "measured_count": meta["ranked_count"],
        "excluded_count": 0,
        "total_count": len(candidates),
        "sufficient_count": sufficient,
        "limited_count": limited,
        "unobserved_count": unobserved,
        "sample_min": SAMPLE_MIN,
        "comparison_notice": (
            f"관측값이 있는 {meta['ranked_count']}곳은 모두 점수로 비교합니다. "
            f"점포 {SAMPLE_MIN}곳 미만 {limited}곳은 점수를 50점 쪽으로 보정했고, "
            f"동종업종 미관측 {unobserved}곳은 순위를 매기지 않았습니다."
        ),
        **meta,
        "results": [{
            "rank": c.rank,
            "area_id": c.area_id,
            "area_name": c.area_name,
            "score": c.score,
            "grade": c.grade,
            "percentile": c.percentile,
            "breakdown": R.breakdown_of(c, meta["weights"]) if c.score is not None else [],
            "tags": R.tags_for(c),
            "reason": R.reason_for(c, meta["weights"]),
            "observed": _observed(c),
            **_evidence(c),
        } for c in ranked],
        "relative_notice": _relative_notice(),
        "disclaimer": DISCLAIMER,
    }


@router.get("/industries", response_model=RecommendationIndustryListResponse)
def recommend_industries(
    area_id: int = Query(...),
    preset: str | None = Query(None),
    limit: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """읍면동 하나 → 업종 랭킹 (노다지 '행정동 → 업종').

    **여기서는 등급을 내지 않는다.** 각 셀의 점수는 `/areas`·`/score`와 같게
    '같은 업종의 전체 읍면동' 안에서 계산한 다음, 해당 읍면동의 업종들을
    교차 비교한다. 그래야 같은 셀이 화면마다 다른 점수를 받지 않는다. 등급은
    교차 업종 사이의 절대 비교로 오인될 수 있어 표시하지 않는다.
    """
    quarter = _latest_quarter(db)
    area_rows = _rows(db, quarter, area_id=area_id)
    if not area_rows:
        raise HTTPException(status_code=404, detail="해당 읍면동의 예측 결과가 없습니다")
    area_name = area_rows[0][2]
    measured_industry_ids = {
        row[0].industry_id for row in area_rows if not row[0].sample_insufficient
    }
    excluded = len(area_rows) - len(measured_industry_ids)

    # 전체 셀을 한 번 읽고 업종별 모집단으로 나눈다. 업종마다 DB를 다시 조회하면
    # 최대 74번의 쿼리가 되므로, 상대점수의 모집단만 다르고 원본 조회는 한 번으로 끝낸다.
    grouped: dict[int, list] = {}
    for row in _rows(db, quarter):
        if row[0].industry_id in measured_industry_ids:
            grouped.setdefault(row[0].industry_id, []).append(row)

    scored: list[tuple[R.Candidate, dict]] = []
    for industry_rows in grouped.values():
        candidates, _ = _to_candidates(industry_rows)
        meta = R.score_candidates(candidates, preset)
        target = next((candidate for candidate in candidates if candidate.area_id == area_id), None)
        if target is not None:
            scored.append((target, meta))

    ranked = sorted(scored, key=lambda item: (-item[0].score, item[0].industry_name))[:limit]
    preset_key, weights = R.resolve_preset(preset)
    return {
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "area_id": area_id,
        "area_name": area_name,
        "measured_count": len(scored),
        "excluded_count": excluded,
        "preset": preset_key,
        "weights": weights,
        "results": [{
            "rank": rank,
            "industry_id": c.industry_id,
            "industry_name": c.industry_name,
            "score": c.score,
            "breakdown": R.breakdown_of(c, item_meta["weights"]),
            "tags": R.tags_for(c),
            "reason": R.reason_for(c, item_meta["weights"]),
            "observed": _observed(c),
            "growth_spread": item_meta["growth_spread"],
            "growth_spread_narrow": item_meta["growth_spread_narrow"],
        } for rank, (c, item_meta) in enumerate(ranked, start=1)],
        "grade_notice": (
            "각 점수는 같은 업종의 화성시 읍면동 안에서 계산했습니다. "
            "서로 다른 업종의 절대 우열을 뜻하지 않으며 등급은 표시하지 않습니다."
        ),
        "relative_notice": _relative_notice(),
        "disclaimer": DISCLAIMER,
    }


@router.get("/score", response_model=RecommendationScoreResponse)
def recommend_score(
    area_id: int = Query(...),
    industry_id: int = Query(...),
    preset: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """셀 하나의 적합도 (노다지 '행정동 + 업종 적합도' 3탭 패널).

    점수와 등급은 **그 업종 전체 읍면동을 모집단으로** 계산한다. 그래야 `/areas`가 말하는
    등급과 이 화면의 등급이 같아진다.
    """
    quarter = _latest_quarter(db)
    rows = _rows(db, quarter, industry_id=industry_id)
    if not rows:
        raise HTTPException(status_code=404, detail="해당 업종의 예측 결과가 없습니다")
    industry_name = rows[0][3]
    candidates, _ = _to_candidates(rows)
    _append_unobserved_areas(
        db, candidates, industry_id=industry_id, industry_name=industry_name,
    )
    meta = R.score_candidates(candidates, preset)

    target = next((c for c in candidates if c.area_id == area_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")

    if target.score is None:
        return {
            "quarter_code": quarter,
            "quarter_label": quarter_label(quarter),
            "area_id": area_id, "area_name": target.area_name,
            "industry_id": industry_id, "industry_name": industry_name,
            "is_fallback": True,
            "score": None, "grade": None, "percentile": None, "rank": None,
            "total": meta["ranked_count"],
            "summary": target.adjustment_note,
            "breakdown": [], "pros": [], "cons": [],
            "observed": _observed(target),
            **_evidence(target),
            **{k: meta[k] for k in ("preset", "weights", "growth_spread", "growth_spread_narrow")},
            "relative_notice": _relative_notice(),
            "disclaimer": DISCLAIMER,
        }

    breakdown = R.breakdown_of(target, meta["weights"])
    pros = [f"{b['label']} {b['score']:.0f}점" for b in breakdown if b["score"] >= 70]
    cons = [f"{b['label']} {b['score']:.0f}점" for b in breakdown if b["score"] < 40]
    if meta["growth_spread_narrow"]:
        cons.append(
            f"이 업종은 읍면동 간 AI 예측 차이가 작습니다(폭 {meta['growth_spread']}점). "
            "성장 추세 점수의 차이를 크게 해석하지 마세요."
        )
    return {
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "window_quarters": WINDOW_QUARTERS,
        "area_id": area_id, "area_name": target.area_name,
        "industry_id": industry_id, "industry_name": industry_name,
        "is_fallback": False,
        "score": target.score,
        "grade": target.grade,
        "percentile": target.percentile,
        "rank": target.rank,
        "total": meta["ranked_count"],
        "excluded_count": 0,
        "summary": R.reason_for(target, meta["weights"]),
        "breakdown": breakdown,
        "pros": pros,
        "cons": cons,
        "observed": _observed(target),
        **_evidence(target),
        **meta,
        "relative_notice": _relative_notice(),
        "disclaimer": DISCLAIMER,
    }
