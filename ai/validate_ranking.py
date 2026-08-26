"""조기경보 정렬 방식 재검증 — 모델 단독 vs 관측 단독 vs 앙상블.

왜 이 스크립트가 있나
────────────────────────────────────────────────────────────────────────────
build_risk_index.py와 backend/routers/alerts.py의 주석이 서로 다른 말을 하고 있었다.

    build_risk_index.py  "정렬은 앙상블 (모델 1.393x / 관측 1.428x / 앙상블 1.438x)"
    alerts.py            "정렬은 모델 순위 (스피어만 0.566 vs 0.438)"

실제 동작은 후자였고, 앙상블 컬럼은 계산만 되고 버려지고 있었다. 두 수치 어느 쪽도
리포에 재현 근거가 없었다 — 로그도 없고 스크립트도 없었다. 그래서 만들었다.

**숫자를 주석에 적을 거면 그 숫자를 다시 뽑는 방법도 함께 남긴다.**

검증 방법
────────────────────────────────────────────────────────────────────────────
기준 분기에서 세 방식으로 셀 순위를 매기고, 그 뒤 4분기에 실제로 일어난 폐업률과 맞춘다.

    모델 단독   저장된 LightGBM이 그 시점 feature로 예측한 폐업률
    관측 단독   그 시점까지 4분기 누적 폐업률의 Wilson 신뢰하한
    앙상블      위 둘의 백분위 순위 평균

    스피어만    순위 전체가 미래와 얼마나 맞는가
    리프트      상위 10%의 미래 폐업률 / 전체 평균

한계 — 쓸 수 있는 기준 분기가 2개뿐이다(모델 검증 종료가 2024Q2라 그 이후여야 하고,
미래 4분기가 필요해 2024Q4가 마지막이다). 셀도 200여 개다. 소수점 둘째 자리 차이를
근거로 결론을 내지 말 것.

실행: python ai/validate_ranking.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cumulative import wilson_lower  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
MODEL_PKL = ROOT / "data" / "processed" / "lgbm_model_cell.pkl"
CELL_TABLE = ROOT / "data" / "processed" / "cell_train_table.csv"

KEY = ["행정동명", "상권업종중분류명"]
SAMPLE_MIN = 50          # 조회 기준과 동일
TOP_PCT = 0.10           # 리프트를 재는 상위 비율
ORIGINS = [20243, 20244]  # 모델 검증 종료(2024Q2) 이후 & 미래 4분기가 확보되는 분기


def _quarter_code(label: str) -> int:
    return int(label[:4]) * 10 + int(label[5])


def _cumulative(df: pd.DataFrame, quarters: list[int]) -> pd.DataFrame:
    """건수합/분모합. 비율의 평균이 아니다(ai/cumulative.py와 같은 원칙)."""
    window = df[df["qc"].isin(quarters)]
    agg = window.groupby(KEY).apply(
        lambda x: pd.Series({
            "건수": (x["폐업률"] * x["점포수"]).sum(),
            "분모": x["점포수"].sum(),
        })
    )
    agg["률"] = agg["건수"] / agg["분모"] * 100
    return agg


def main() -> None:
    if not MODEL_PKL.exists() or not CELL_TABLE.exists():
        raise SystemExit(
            f"필요한 파일이 없습니다:\n  {MODEL_PKL}\n  {CELL_TABLE}\n"
            "ai/train_model.py를 먼저 실행하세요."
        )

    bundle = joblib.load(MODEL_PKL)
    model, features = bundle["model"], bundle["features"]

    cells = pd.read_csv(CELL_TABLE)
    cells["qc"] = cells["기준분기"].map(_quarter_code)
    quarters = sorted(cells["qc"].unique())

    rows = []
    for origin in ORIGINS:
        if origin not in quarters:
            print(f"  건너뜀 — {origin} 분기가 없습니다")
            continue
        i = quarters.index(origin)
        past, future = quarters[i - 3:i + 1], quarters[i + 1:i + 5]
        if len(past) < 4 or len(future) < 4:
            print(f"  건너뜀 — {origin}은 과거 4분기 또는 미래 4분기가 부족합니다")
            continue

        current = cells[(cells["qc"] == origin) & (cells["점포수"] >= SAMPLE_MIN)].copy()
        for column in KEY:
            current[column] = current[column].astype("category")
        current["모델"] = model.predict(current[features])
        current = current.set_index(KEY)

        past_cum = _cumulative(cells, past).reindex(current.index)
        current["관측"] = wilson_lower(past_cum["건수"].values, past_cum["분모"].values) * 100
        current["미래"] = _cumulative(cells, future).reindex(current.index)["률"].values
        current = current.dropna(subset=["모델", "관측", "미래"])

        current["앙상블"] = (
            current["모델"].rank(pct=True) + current["관측"].rank(pct=True)
        ) / 2

        n = len(current)
        k = max(1, round(n * TOP_PCT))
        baseline = current["미래"].mean()

        row = {"기준분기": origin, "셀수": n}
        for name in ("모델", "관측", "앙상블"):
            row[f"스피어만_{name}"] = round(
                spearmanr(current[name], current["미래"]).correlation, 3
            )
            row[f"리프트_{name}"] = round(
                current.nlargest(k, name)["미래"].mean() / baseline, 3
            )
        rows.append(row)

    if not rows:
        raise SystemExit("검증할 수 있는 기준 분기가 없습니다.")

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    print("\n[평균]")
    means = result.drop(columns=["기준분기", "셀수"]).mean().round(3)
    for name in ("모델", "관측", "앙상블"):
        print(f"  {name:4s}  스피어만 {means[f'스피어만_{name}']:.3f}"
              f"   리프트 {means[f'리프트_{name}']:.3f}")
    print(
        "\n지표에 따라 승자가 갈리고 차이가 오차 수준이면 성능으로 고르지 말 것.\n"
        "현재 선택은 모델 단독이며 이유는 화면 정체성이다 — 자세한 내용은\n"
        "ai/build_risk_index.py의 예측 순위 블록 주석 참조."
    )


if __name__ == "__main__":
    main()
