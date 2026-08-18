"""활성 셀 모델의 상대적 기여 요인을 계산해 prediction_contributions에 적재한다.

원 예측값과 원 기여도는 외부 API에 노출하지 않는다. 범주형 중첩 변수는 하나의 설명 요인으로
합치고, 전체 절대 기여도의 90%를 단일 요인이 차지하면 M1 실패로 판정해 적재하지 않는다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import engine  # noqa: E402
from backend.models import (  # noqa: E402
    AdminArea,
    CommercialQuarter,
    IndustryCategory,
    ModelRun,
    PredictionContribution,
    RiskPrediction,
)


CATEGORICAL_FEATURES = ["행정동명", "상권업종중분류명", "임대료_매핑그룹"]
FACTOR_GROUPS = [
    {
        "code": "area_industry_pattern",
        "label": "지역·업종 과거 패턴",
        "features": CATEGORICAL_FEATURES,
    },
    {
        "code": "avg_business_age",
        "label": "평균 업력",
        "features": ["평균업력_분기수"],
    },
    {
        "code": "store_scale",
        "label": "점포 규모",
        "features": ["점포수"],
    },
]
MAX_DOMINANT_SHARE_PCT = 90.0


def _quarter_key(value: str) -> int:
    year, quarter = value.split("Q")
    return int(year) * 4 + int(quarter)


def _group_contributions(raw: np.ndarray, features: list[str]) -> np.ndarray:
    grouped = []
    for factor in FACTOR_GROUPS:
        indices = [features.index(name) for name in factor["features"]]
        grouped.append(raw[:, indices].sum(axis=1))
    return np.column_stack(grouped)


def build_explanations(
    session: Session,
    model_path: Path,
    cell_table_path: Path,
    validation_output_path: Path,
    validate_only: bool = False,
) -> dict:
    artifact = joblib.load(model_path)
    model = artifact["model"]
    features = list(artifact["features"])
    expected = {name for factor in FACTOR_GROUPS for name in factor["features"]}
    missing = sorted(expected - set(features))
    if missing:
        raise ValueError(f"설명 요인에 필요한 모델 feature가 없습니다: {missing}")

    cell = pd.read_csv(cell_table_path, encoding="utf-8-sig")
    latest_label = max(cell["기준분기"].astype(str).unique(), key=_quarter_key)
    latest = cell[cell["기준분기"].astype(str) == latest_label].copy()
    for column in CATEGORICAL_FEATURES:
        latest[column] = latest[column].astype("category")

    raw = np.asarray(model.predict(latest[features], pred_contrib=True))
    if raw.shape[1] != len(features) + 1:
        raise ValueError(
            f"예상하지 못한 pred_contrib shape: {raw.shape}, features={len(features)}"
        )
    grouped = _group_contributions(raw[:, :-1], features)
    global_abs = np.abs(grouped).sum(axis=0)
    total_global_abs = float(global_abs.sum())
    global_shares = (
        global_abs / total_global_abs * 100
        if total_global_abs > 0
        else np.zeros(len(FACTOR_GROUPS))
    )
    dominant_share = float(global_shares.max()) if len(global_shares) else 0.0
    m1_passed = total_global_abs > 0 and dominant_share <= MAX_DOMINANT_SHARE_PCT

    validation = {
        "latest_quarter": latest_label,
        "rows": int(len(latest)),
        "max_allowed_dominant_share_pct": MAX_DOMINANT_SHARE_PCT,
        "dominant_share_pct": round(dominant_share, 4),
        "factor_global_share_pct": {
            factor["code"]: round(float(share), 4)
            for factor, share in zip(FACTOR_GROUPS, global_shares)
        },
        "m1_passed": m1_passed,
    }
    validation_output_path.parent.mkdir(parents=True, exist_ok=True)
    validation_output_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    active_run = session.query(ModelRun).filter(ModelRun.is_active.is_(True)).one_or_none()
    if not active_run:
        raise RuntimeError("활성 model_run이 없습니다")
    prediction_rows = (
        session.query(
            RiskPrediction.id,
            AdminArea.area_name,
            IndustryCategory.industry_name,
        )
        .join(CommercialQuarter, RiskPrediction.commercial_quarter_id == CommercialQuarter.id)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            RiskPrediction.model_run_id == active_run.id,
            RiskPrediction.predicted_rank.isnot(None),
            CommercialQuarter.sample_insufficient.is_(False),
        )
        .all()
    )
    prediction_lookup = {(area, industry): prediction_id for prediction_id, area, industry in prediction_rows}

    if validate_only:
        return {**validation, "eligible_predictions": len(prediction_lookup), "written": 0}

    prediction_ids = list(prediction_lookup.values())
    if prediction_ids:
        session.query(PredictionContribution).filter(
            PredictionContribution.prediction_id.in_(prediction_ids)
        ).delete(synchronize_session=False)

    if not m1_passed:
        session.commit()
        return {**validation, "eligible_predictions": len(prediction_lookup), "written": 0}

    latest = latest.reset_index(drop=True)
    contribution_rows = []
    for index, row in latest.iterrows():
        prediction_id = prediction_lookup.get(
            (str(row["행정동명"]), str(row["상권업종중분류명"]))
        )
        if prediction_id is None:
            continue
        values = grouped[index]
        denominator = float(np.abs(values).sum())
        if denominator <= 0:
            continue
        ordered = np.argsort(-np.abs(values))
        for rank, factor_index in enumerate(ordered, 1):
            factor = FACTOR_GROUPS[int(factor_index)]
            value = float(values[factor_index])
            contribution_rows.append(
                PredictionContribution(
                    prediction_id=prediction_id,
                    rank=rank,
                    factor_code=factor["code"],
                    factor_label=factor["label"],
                    direction="risk" if value >= 0 else "safe",
                    share_pct=round(abs(value) / denominator * 100, 4),
                    contribution_value_internal=value,
                    source_features=factor["features"],
                )
            )
    session.add_all(contribution_rows)
    session.commit()
    return {
        **validation,
        "eligible_predictions": len(prediction_lookup),
        "written": len(contribution_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=PROJECT_ROOT / "data/processed/lgbm_model_cell.pkl",
    )
    parser.add_argument(
        "--cell-table",
        type=Path,
        default=PROJECT_ROOT / "data/processed/cell_train_table.csv",
    )
    parser.add_argument(
        "--validation-output",
        type=Path,
        default=PROJECT_ROOT / "data/processed/explanation_validation.json",
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    with Session(engine) as session:
        result = build_explanations(
            session,
            args.model,
            args.cell_table,
            args.validation_output,
            args.validate_only,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
