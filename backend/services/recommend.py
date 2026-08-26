"""창업 적합도 추천 — 종합점수·등급 계산을 모아 둔 곳.

## 이 모듈이 하나여야 하는 이유

노다지(서울)는 `views.py` 안에서 세 엔드포인트(`recommend_location`/`recommend_industry`/
`recommend_score`)가 **각자** 정규화와 가중치를 계산한다. 그래서 같은 셀이 화면마다 다른
점수를 받을 수 있다. 화성시는 이미 같은 실수를 한 번 했고(`build_risk_index.py`와
`import_normalized_db.py`가 각자 등급을 계산해 CSV와 화면이 어긋났다) `ai/cumulative.py`로
수습했다. 추천 관련 계산은 전부 이 파일에서만 한다.

## 종합점수 — 가중치는 사용자가 고른다

노다지 원본 공식은 이렇다.

    성장확률 x 0.40 + 소분류경쟁 x 0.30 + 유동인구 x 0.15 + 포화도 x 0.15

화성시로 옮기면서 두 가지가 달라졌다.

**(1) 유동인구 축이 없다.** 절대값이 2021-12 -> 2022-01 사이 4.4배로 단절돼 쓸 수 없다
(share는 보존되지만 아직 파이프라인에 없다). 그 자리를 평균 업력('정착도')으로 채우려
했으나 계측에서 기각했다 — 2026-08-26, 표본충분 231셀 기준 각 후보와 최근 1년 누적
폐업률의 스피어만:

    평균 업력            -0.064
    보정 개업률          +0.420   <- 방향이 반대(개업 많은 곳이 폐업도 많다)
    읍면동 전체 점포수    -0.042
    업종 점포수          +0.026
    업종 포화도          +0.068

업력은 안전도가 아니라 신도시 여부의 대리변수였다(면·읍이 높고 동탄이 낮다). 그래서
축에서 빼고 표시 지표로만 남겼다. 남은 축은 셋이다.

**(2) 가중치의 근거가 없다.** 위 표대로면 모델 예측 말고는 관측 결과를 설명하는 축이
없으므로 "왜 40/30/15/15인가"에 답할 수 없다. 그래서 **가중치를 고정하지 않고 사용자가
고르게** 한다(노다지의 PREFERENCE_WEIGHTS와 같은 구조). 기본값은 '균형'이고, 화면은
어떤 프리셋으로 계산된 점수인지를 항상 함께 보여준다.

## 성장확률은 업종 안에서 다시 정규화한다

노다지는 성장확률만 정규화하지 않고 0~100 원값에 가중치를 곱한다. 서울은 행정동이 424개라
성장확률이 넓게 퍼지지만, 화성시는 업종 내 폭이 평균 7.0점뿐이다(자동차 수리·세차는 2.0).
원값을 그대로 쓰면 가중 0.40이 실질 5%도 안 되고 나머지 축이 점수를 지배한다.

    정규화 전: 성장확률 순위와 종합점수 순위의 top-N 겹침 51% / 스피어만 +0.309
    정규화 후: 74% / +0.784

대신 폭이 좁은 업종에서도 1등 100점 꼴찌 0점이 되므로, 응답에 `growth_spread`를 함께
내리고 화면이 "이 업종은 읍면동 간 예측 차이가 크지 않습니다"를 띄운다.

## 등급은 업종 내 백분위다

`scores.csv`의 `등급` 컬럼은 **전체 1,810셀 기준** 분위수라 한식은 어느 읍면동이든 C~D다
(업종 간 폐업률 차이가 등급을 통째로 밀어버린다). 화면의 질문은 "어느 읍면동에 열까"이므로
모집단도 그 업종의 읍면동이어야 한다. 그래서 종합점수를 업종 안에서 다시 순위 매겨
등급을 부여한다. `scores.csv`의 등급 컬럼은 이 화면에서 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import (
    AdminArea,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    RiskPrediction,
)

# 가중치 프리셋. 합이 1.0이 아니면 로드 시점에 걸린다(아래 검증 참조).
# 이름과 설명은 화면에 그대로 나가므로 여기서만 고친다.
WEIGHT_PRESETS: dict[str, dict] = {
    "균형": {
        "label": "균형",
        "description": "AI 예측을 절반, 경쟁과 포화도를 나머지로 봅니다.",
        "weights": {"growth": 0.50, "competition": 0.30, "saturation": 0.20},
    },
    "예측중심": {
        "label": "AI 예측 중심",
        "description": "모델이 예측한 다음 분기 전망에 무게를 둡니다.",
        "weights": {"growth": 0.80, "competition": 0.10, "saturation": 0.10},
    },
    "블루오션": {
        "label": "블루오션",
        "description": "같은 업종이 적은 곳을 우선합니다.",
        "weights": {"growth": 0.25, "competition": 0.50, "saturation": 0.25},
    },
    "여유": {
        "label": "자리 여유",
        "description": "읍면동 안에서 그 업종이 아직 덜 찬 곳을 우선합니다.",
        "weights": {"growth": 0.25, "competition": 0.25, "saturation": 0.50},
    },
}
DEFAULT_PRESET = "균형"

AXES = ("growth", "competition", "saturation")

AXIS_LABELS = {
    "growth": "성장 추세",
    "competition": "경쟁 우위",
    "saturation": "포화도",
}
AXIS_DESCRIPTIONS = {
    "growth": "AI가 예측한 다음 분기 폐업 위험의 반대값입니다. 같은 업종 안에서 상대 비교합니다.",
    "competition": "같은 업종 점포가 적을수록 높습니다.",
    "saturation": "읍면동 전체 점포 중 이 업종이 차지하는 비중이 낮을수록 높습니다.",
}

# 성장확률 폭이 이 값(퍼센트포인트) 미만이면 "읍면동 간 차이가 작다"고 화면에 알린다.
# 정규화가 없는 차이를 있는 것처럼 벌려 놓기 때문이다.
GROWTH_SPREAD_MIN = 3.0

# 등급 경계(업종 내 상위 퍼센트). scores.csv의 to_grade와 같은 25/50/75다 —
# 모집단만 '전체 배치'에서 '업종 내'로 바뀐다.
GRADE_CUTS = ((25.0, "A"), (50.0, "B"), (75.0, "C"))

for _name, _preset in WEIGHT_PRESETS.items():
    _total = sum(_preset["weights"].values())
    if abs(_total - 1.0) > 1e-9:
        raise ValueError(f"가중치 프리셋 '{_name}'의 합이 1.0이 아닙니다: {_total}")
    if set(_preset["weights"]) != set(AXES):
        raise ValueError(f"가중치 프리셋 '{_name}'의 축이 AXES와 다릅니다")


@dataclass
class Candidate:
    """점수를 매길 셀 하나. DB 모델이 아니라 계산 입력이다."""
    area_id: int
    area_name: str
    industry_id: int
    industry_name: str
    growth_prob: float            # 0~100, (1 - 예측폐업률) x 100
    store_count: int
    saturation: float | None
    closure_rate_cum4_pct: float | None
    closure_count_cum4: int | None
    opening_rate_pct: float | None
    tenure_quarters: float | None
    cell_type: str | None

    axis_scores: dict = field(default_factory=dict)
    score: float = 0.0
    rank: int = 0
    percentile: float = 0.0
    grade: str = "-"


def load_rows(
    db: Session,
    quarter: int,
    *,
    area_id: int | None = None,
    industry_id: int | None = None,
):
    """추천 계산에 필요한 내부 예측과 관측치를 한 번에 읽는다.

    내부 예측 컬럼을 라우터가 직접 다루지 않게 이 모듈에 둔다. 라우터는 이 값으로
    계산된 업종 내 상대점수만 응답하고, 예측 폐업률이나 그 반대값은 공개하지 않는다.
    """
    query = (
        db.query(
            CommercialQuarter,
            RiskPrediction.predicted_closure_rate_internal,
            AdminArea.area_name,
            IndustryCategory.industry_name,
        )
        .join(RiskPrediction, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .join(ModelRun, RiskPrediction.model_run_id == ModelRun.id)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == quarter,
            ModelRun.is_active.is_(True),
        )
    )
    if area_id is not None:
        query = query.filter(CommercialQuarter.area_id == area_id)
    if industry_id is not None:
        query = query.filter(CommercialQuarter.industry_id == industry_id)
    return query.all()


def minmax(values: list[float]) -> list[float]:
    """조회 집합 안에서 0~100으로 편다. 전부 같은 값이면 50.0으로 둔다.

    50.0인 이유: 0으로 두면 그 축이 통째로 죽고, 100으로 두면 모두가 만점을 받는다.
    어느 쪽도 "차이가 없다"를 뜻하지 않는다.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [50.0] * len(values)
    return [(v - lo) / (hi - lo) * 100 for v in values]


def invert(scores: list[float]) -> list[float]:
    """적을수록 좋은 축(점포수·포화도)을 뒤집는다."""
    return [100.0 - s for s in scores]


def grade_for(percentile: float) -> str:
    for cut, grade in GRADE_CUTS:
        if percentile <= cut:
            return grade
    return "D"


def resolve_preset(name: str | None) -> tuple[str, dict]:
    key = name or DEFAULT_PRESET
    if key not in WEIGHT_PRESETS:
        key = DEFAULT_PRESET
    return key, WEIGHT_PRESETS[key]["weights"]


def score_candidates(candidates: list[Candidate], preset: str | None = None) -> dict:
    """후보들에 종합점수·업종 내 순위·등급을 매긴다. 리스트를 제자리에서 고친다.

    정규화가 **조회 집합 안에서** 이뤄지므로, 후보 목록이 달라지면 같은 셀의 점수도
    달라진다. 노다지도 같은 구조이고, 화성시는 읍면동이 29개뿐이라 요동이 더 크다.
    화면에 "이 목록 안에서의 상대 점수"임을 반드시 밝힌다.
    """
    preset_key, weights = resolve_preset(preset)
    if not candidates:
        return {
            "preset": preset_key, "weights": weights,
            "growth_spread": 0.0, "growth_spread_narrow": True,
        }

    growth_raw = [c.growth_prob for c in candidates]
    growth = minmax(growth_raw)
    competition = invert(minmax([float(c.store_count) for c in candidates]))
    saturation = invert(minmax([float(c.saturation or 0.0) for c in candidates]))

    for i, c in enumerate(candidates):
        c.axis_scores = {
            "growth": round(growth[i], 1),
            "competition": round(competition[i], 1),
            "saturation": round(saturation[i], 1),
        }
        c.score = round(sum(c.axis_scores[a] * weights[a] for a in AXES), 1)

    # 등급은 종합점수의 업종 내 백분위. 동점은 같은 등수를 준다 — 소수점 한 자리가
    # 같은데 등수가 갈리면 "왜 우리가 한 칸 아래냐"에 답할 근거가 없다.
    ordered = sorted(candidates, key=lambda c: -c.score)
    total = len(ordered)
    seen: dict[float, int] = {}
    for idx, c in enumerate(ordered, start=1):
        c.rank = seen.setdefault(c.score, idx)
        c.percentile = round(c.rank / total * 100, 1)
        c.grade = grade_for(c.percentile)

    spread = max(growth_raw) - min(growth_raw)
    return {
        "preset": preset_key,
        "weights": weights,
        "growth_spread": round(spread, 1),
        "growth_spread_narrow": spread < GROWTH_SPREAD_MIN,
    }


def breakdown_of(c: Candidate, weights: dict) -> list[dict]:
    return [
        {
            "key": axis,
            "label": AXIS_LABELS[axis],
            "score": c.axis_scores.get(axis, 0.0),
            "max": 100,
            "weight_pct": round(weights[axis] * 100),
            "desc": AXIS_DESCRIPTIONS[axis],
        }
        for axis in AXES
    ]


def tags_for(c: Candidate) -> list[str]:
    """카드에 붙는 짧은 꼬리표. 점수가 아니라 관측 사실만 쓴다."""
    tags: list[str] = []
    if c.store_count == 0:
        tags.append("점포 없음")
    elif c.axis_scores.get("competition", 0) >= 70:
        tags.append("경쟁 적음")
    if c.axis_scores.get("saturation", 0) >= 70:
        tags.append("자리 여유")
    if c.cell_type:
        tags.append(c.cell_type)
    if c.tenure_quarters and c.tenure_quarters >= 60:
        tags.append("오래된 상권")
    return tags[:4]


def reason_for(c: Candidate, weights: dict) -> str:
    """한 줄 설명. 가장 크게 기여한 축을 지목하고 관측치를 덧붙인다."""
    top = max(AXES, key=lambda a: c.axis_scores.get(a, 0) * weights[a])
    head = {
        "growth": "같은 업종 안에서 AI 예측이 상대적으로 좋은 편입니다",
        "competition": "같은 업종 점포가 적은 편입니다",
        "saturation": "읍면동 안에서 이 업종이 아직 덜 찬 편입니다",
    }[top]
    if c.closure_rate_cum4_pct is None:
        return f"{head}."
    return f"{head}. 최근 1년 누적 폐업률은 {c.closure_rate_cum4_pct:.1f}%입니다."
