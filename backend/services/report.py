"""외부 생성형 AI 없이 만드는 공개 상권 요약 보고서."""
from __future__ import annotations

from urllib.parse import quote

from .risk import SAMPLE_MIN


REPORT_VERSION = "rules-v1"
AI_DISCLOSURE = (
    "LightGBM 예측은 같은 업종 안의 상대 적합도 계산에만 사용했습니다. "
    "보고서 문장은 검증된 규칙으로 조합하며 외부 생성형 AI API를 사용하지 않습니다."
)


def _fmt(value, suffix: str = "", digits: int = 1) -> str:
    if value is None:
        return "자료 없음"
    return f"{float(value):.{digits}f}{suffix}"


def _count(value) -> str:
    return "자료 없음" if value is None else f"{int(value):,}곳"


def build_report(score: dict, observed: dict) -> dict:
    area = score["area_name"]
    industry = score["industry_name"]
    fallback = bool(score.get("is_fallback"))
    rank_text = (
        "표본이 적어 상대 순위를 매기지 않음"
        if fallback
        else f"{industry} {score['total']}개 읍면동 중 {score['rank']}위 · 상위 {score['percentile']}%"
    )
    observed_data = observed.get("comparison", {})
    metrics = [
        {"label": "최근 1년 누적 폐업률", "value": _fmt(observed.get("closure_rate_pct"), "%")},
        {"label": "같은 기간 폐업 점포", "value": _count(observed.get("closure_count"))},
        {"label": "현재 점포", "value": _count(observed.get("store_count"))},
        {"label": "보정 개업률", "value": _fmt(observed.get("opening_rate_pct"), "%")},
        {"label": "화성시 표본충분 셀 평균", "value": _fmt(observed_data.get("city_avg_pct"), "%")},
    ]
    facts = [f"{metric['label']}: {metric['value']}" for metric in metrics]
    strengths = score.get("pros") or ["상대점수에서 70점 이상인 두드러진 축이 없습니다."]
    cautions = score.get("cons") or ["상대점수에서 40점 미만인 두드러진 축이 없습니다."]
    if observed.get("sample_insufficient"):
        cautions = [
            f"점포가 {SAMPLE_MIN}곳 미만이라 비율·순위·등급을 판단하지 않습니다.",
            *cautions,
        ]

    sections = [
        {
            "key": "overview",
            "title": "한눈에 보기",
            "body": [score["summary"], rank_text],
        },
        {
            "key": "observed",
            "title": "확인된 관측 사실",
            "body": facts,
        },
        {
            "key": "strengths",
            "title": "상대 강점",
            "body": strengths,
        },
        {
            "key": "cautions",
            "title": "유의할 점",
            "body": cautions,
        },
        {
            "key": "field-check",
            "title": "현장에서 확인할 항목",
            "body": [
                "임대료와 관리비가 예상 매출 구조에 맞는지 확인",
                "시간대별 유동인구와 실제 고객 구성을 현장 방문으로 확인",
                "공실 기간·권리금·주차 접근성처럼 현재 데이터에 없는 조건 확인",
                "최종 입지 판단 전 소관 부서 공고와 인허가 요건 확인",
            ],
        },
    ]
    quarter = score["quarter_code"]
    preset = score["preset"]
    cache_key = ":".join(
        [REPORT_VERSION, str(quarter), str(score["area_id"]), str(score["industry_id"]), quote(preset)]
    )
    return {
        "title": f"{area} · {industry} 상권 요약",
        "area_name": area,
        "industry_name": industry,
        "quarter_code": quarter,
        "quarter_label": score["quarter_label"],
        "preset": preset,
        "cache_key": cache_key,
        "generated_by": REPORT_VERSION,
        "sections": sections,
        "metrics": metrics,
        "sources": [
            "소상공인시장진흥공단 상가(상권)정보: 읍면동·업종별 점포와 개·폐업 집계",
            "상대 적합도: 같은 업종 내 AI 예측·수요 여건·경쟁·포화도 비교",
        ],
        "provisional_notice": observed.get("provisional_notice", ""),
        "relative_notice": score["relative_notice"],
        "disclaimer": score["disclaimer"],
        "ai_disclosure": AI_DISCLOSURE,
    }
