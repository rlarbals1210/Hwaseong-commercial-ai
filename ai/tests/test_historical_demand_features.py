import numpy as np
import pandas as pd

from ai.build_historical_demand_features import (
    MIN_SELECTION_TARGET_MONTHS,
    eligible_source_months,
    month_to_quarter_code,
    previous_quarter_code,
    select_asof_blend,
)


def _supervised(target_months: list[str]) -> pd.DataFrame:
    rows = []
    for month in target_months:
        for area, current, rolling, target in (
            ("a", 0.6, 0.55, 0.52),
            ("b", 0.4, 0.45, 0.48),
        ):
            rows.append({
                "target_month": month,
                "card_code": "Q01",
                "area_code": area,
                "current_share": current,
                "rolling3_share": rolling,
                "target_share": target,
            })
    return pd.DataFrame(rows)


def test_quarter_code_helpers() -> None:
    assert month_to_quarter_code("202203") == 20221
    assert month_to_quarter_code("202212") == 20224
    assert previous_quarter_code(20221) == 20214
    assert previous_quarter_code(20224) == 20223


def test_eligible_sources_require_three_contiguous_months_and_supply() -> None:
    months = ["202201", "202202", "202203", "202205", "202206", "202212"]
    assert eligible_source_months(months, {20221, 20222, 20224}) == ["202203"]


def test_asof_selection_never_uses_future_target_months() -> None:
    supervised = _supervised(["202202", "202203", "202204", "202205"])
    choice = select_asof_blend(supervised, "202204")
    assert choice.history_target_months == ("202202", "202203", "202204")
    assert "202205" not in choice.history_target_months
    assert np.isfinite(choice.validation_mae)


def test_asof_selection_falls_back_with_too_little_history() -> None:
    supervised = _supervised(["202202", "202203"])
    choice = select_asof_blend(supervised, "202203")
    assert len(choice.history_target_months) < MIN_SELECTION_TARGET_MONTHS
    assert choice.method == "persistence_fallback"
    assert choice.rolling_blend == 0.0
    assert choice.validation_mae is None
