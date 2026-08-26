from backend.services.report import AI_DISCLOSURE, build_report


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
