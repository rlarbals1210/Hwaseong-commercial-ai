import pandas as pd

from ai.analyze_tenure import build_exposures, summarize_tenure


def test_build_exposures_uses_explicit_future_closure_date():
    permits = pd.DataFrame(
        {
            "business_id": ["a", "b"],
            "source": ["fixture", "fixture"],
            "open_date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
            "close_date": pd.to_datetime(["2021-05-01", None]),
        }
    )

    exposures = build_exposures(permits, "2020Q4", "2020Q4", horizon_quarters=2)

    assert len(exposures) == 2
    assert exposures.set_index("business_id").loc["a", "closure_within_horizon"]
    assert not exposures.set_index("business_id").loc["b", "closure_within_horizon"]


def test_summarize_tenure_keeps_predeclared_bins():
    exposures = pd.DataFrame(
        {
            "business_id": ["a", "b", "c", "d", "e"],
            "source": ["fixture"] * 5,
            "origin_quarter": ["2024Q1"] * 5,
            "tenure_quarters": [0, 4, 8, 12, 20],
            "closure_within_horizon": [False, True, True, False, False],
        }
    )

    summary, quarterly, overall_rate = summarize_tenure(exposures)

    assert summary["tenure_segment"].tolist() == ["0-3", "4-7", "8-11", "12-19", "20+"]
    assert quarterly["tenure_segment"].nunique() == 5
    assert overall_rate == 0.4
