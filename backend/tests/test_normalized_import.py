import numpy as np
import pandas as pd

from ai.import_normalized_db import (
    _area_risk_grade,
    _cell_risk_grade,
    _quarter_add,
    _supplement_score_only_cells,
)


def test_quarter_add_rolls_over_year():
    assert _quarter_add(20254, 1) == 20261
    assert _quarter_add(20254, 2) == 20262


def test_risk_grades_use_stored_threshold_semantics():
    assert _cell_risk_grade(0.07, False, 3.22, 6.44) == "위험"
    assert _cell_risk_grade(0.04, False, 3.22, 6.44) == "주의"
    assert _cell_risk_grade(0.01, False, 3.22, 6.44) == "안정"
    assert _cell_risk_grade(0.20, True, 3.22, 6.44) == "표본부족"
    assert _cell_risk_grade(None, False, 3.22, 6.44) is None
    assert _area_risk_grade(25.0, 11.62, 23.24) == "위험"


def test_score_only_cell_is_preserved_as_unrated_fact(tmp_path):
    commercial = pd.DataFrame([
        {
            "행정동명": "동탄1동",
            "통합카테고리": "한식",
            "기준_년분기_코드": 20254,
            "점포수": 10,
            "개업_율_평균": 0.1,
            "폐업_률_평균": 0.05,
            "업종_포화도": 1.0,
            "경쟁강도": 0.0,
        }
    ])
    scores = pd.DataFrame([
        {"행정동명": "동탄1동", "통합카테고리": "한식"},
        {"행정동명": "동탄1동", "통합카테고리": "일식"},
    ])
    cell_table = pd.DataFrame([
        {"행정동명": "동탄1동", "상권업종중분류명": "한식", "기준분기": "2025Q4", "점포수": 10},
        {"행정동명": "동탄1동", "상권업종중분류명": "일식", "기준분기": "2025Q4", "점포수": 2},
    ])
    path = tmp_path / "cell.csv"
    cell_table.to_csv(path, index=False, encoding="utf-8-sig")

    result = _supplement_score_only_cells(commercial, scores, path)
    added = result[result["통합카테고리"] == "일식"].iloc[0]

    assert len(result) == 2
    assert added["점포수"] == 2
    assert np.isnan(added["개업_율_평균"])
    assert np.isnan(added["폐업_률_평균"])
    assert added["업종_포화도"] == 2 / 12
