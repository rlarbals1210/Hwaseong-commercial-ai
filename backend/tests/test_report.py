from backend.services.report import AI_DISCLOSURE, build_report
from backend.services.risk import SAMPLE_MIN


def test_rule_report_has_five_sections_and_quarter_cache_key():
    score = {
        "area_id": 1,
        "area_name": "병점1동",
        "industry_id": 2,
        "industry_name": "한식",
        "quarter_code": 20254,
        "quarter_label": "2025Q4",
        "preset": "균형",
        "is_fallback": False,
        "total": 27,
        "rank": 1,
        "percentile": 3.7,
        "summary": "상대적으로 좋은 편입니다.",
        "pros": ["경쟁 우위 80점"],
        "cons": [],
        "relative_notice": "상대값입니다.",
        "disclaimer": "현장 확인이 필요합니다.",
    }
    observed = {
        "closure_rate_pct": 3.2,
        "closure_count": 4,
        "store_count": 100,
        "opening_rate_pct": 2.1,
        "sample_insufficient": False,
        "comparison": {"city_avg_pct": 4.0},
    }

    report = build_report(score, observed)

    assert len(report["sections"]) == 5
    assert ":20254:" in report["cache_key"]
    assert report["generated_by"] == "rules-v1"
    assert report["ai_disclosure"] == AI_DISCLOSURE
    assert "외부 생성형 AI API를 사용하지 않습니다" in report["ai_disclosure"]


def test_rule_report_uses_current_sample_threshold_in_caution():
    score = {
        "area_id": 1,
        "area_name": "병점1동",
        "industry_id": 2,
        "industry_name": "한식",
        "quarter_code": 20254,
        "quarter_label": "2025Q4",
        "preset": "균형",
        "is_fallback": True,
        "total": 0,
        "rank": None,
        "percentile": None,
        "summary": "표본을 더 확인해야 합니다.",
        "pros": [],
        "cons": [],
        "relative_notice": "상대값입니다.",
        "disclaimer": "현장 확인이 필요합니다.",
    }
    observed = {
        "closure_rate_pct": None,
        "closure_count": 1,
        "store_count": SAMPLE_MIN - 1,
        "opening_rate_pct": None,
        "sample_insufficient": True,
        "comparison": {"city_avg_pct": None},
    }

    report = build_report(score, observed)
    cautions = next(section for section in report["sections"] if section["key"] == "cautions")

    assert f"점포가 {SAMPLE_MIN}곳 미만" in cautions["body"][0]
