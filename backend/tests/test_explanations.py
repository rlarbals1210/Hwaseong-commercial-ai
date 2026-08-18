import numpy as np

from ai.build_explanations import _group_contributions


def test_categorical_contributions_are_merged_before_shares():
    features = [
        "행정동명",
        "상권업종중분류명",
        "임대료_매핑그룹",
        "평균업력_분기수",
        "점포수",
    ]
    raw = np.array([[0.1, 0.2, -0.05, -0.3, 0.4]])

    grouped = _group_contributions(raw, features)

    assert grouped.shape == (1, 3)
    assert np.allclose(grouped[0], [0.25, -0.3, 0.4])
