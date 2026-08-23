"""
store_train_table.csv(점포단위, 참고용) + cell_train_table.csv(중분류 셀단위, 주력) -> LightGBM 학습
-> model_store_results.json/lgbm_model_store.pkl(참고) + model_cell_results.json/lgbm_model_cell.pkl(주력)
-> scores.csv(실제 최신 분기 전체 중분류 셀 추론, ScoreData 원천)

eda/03_modeling.ipynb에서 검증된 하이퍼파라미터·분할·feature를 그대로 이식했다. 셀단위(중분류, n>=30
필터로 학습)를 주력 프로덕션 스코어로 채택 - 팀원 벤치마크(스피어만 0.293) 대비 크게 상회(0.419).
리프트는 분위수 기준(pred>=quantile(0.9))으로 계산한다 - "상위 10개 고정" 방식은 극단치 하나에 크게
흔들리는 노이즈 지표라 폐기(eda 03_modeling 3-5절 결론).

사용법:
    python ai/train_model.py
"""
import json
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eda"))
import paths as eda_paths  # noqa: E402
from build_dataset import quarter_to_code  # noqa: E402

TRAIN_END = "2023Q2"
VALID_END = "2024Q2"

CAT_COLS = ["행정동명", "상권업종대분류명", "상권업종중분류명", "임대료_매핑그룹"]
NUM_COLS = ["업력_분기수", "최근1분기이탈률"]
STORE_TARGET = "label_h2"

# 임대료_매핑그룹 제거 (2026-08-20). 되돌리지 말 것.
#
# [이 스크립트가 실제로 출력하는 값 — 보고서·발표에 쓸 공식 수치]
#     스피어만  0.4193 -> 0.4184
#     리프트    1.444  -> 1.433
#   아래 고정 분할(TRAIN_END/VALID_END) 1회 측정 기준. 사실상 동등하며 미세 하락이다.
#
# [제거한 이유 — 성능이 아니라 방어 가능성]
#   실질 값이 3개(동탄권/병점권/기타)뿐이라 25개 행정동이 같은 값을 공유하는 조잡한
#   지역 라벨이다. docs/modeling.md 2-5절이 이 계열을 시간 대리변수로 경고했고,
#   feature 중요도도 1.1%로 사실상 쓰이지 않았다. 문서와 코드의 불일치를 없앤 것이 요지다.
#
# [혼동 주의]
#   내부 검증에서 테스트 구간을 3개로 옮겨가며 잰 값은 0.4992 -> 0.5016 / 1.486 -> 1.522x다.
#   측정 조건이 달라 이 스크립트로는 재현되지 않는다(버그가 아니다).
#   두 수치를 섞어 쓰지 말 것. 대외 공식 성능은 위의 고정 분할 값이다.
#   상세 실험 기록: 프로젝트 문서 "모델-성능개선-실험-2026-08-20"
CELL_CAT = ["행정동명", "상권업종중분류명"]
CELL_NUM = ["평균업력_분기수", "점포수"]
CELL_TARGET = "폐업률"
CELL_MIN_STORES = 30


def quarter_key(q: str) -> int:
    y, qn = int(q[:4]), int(q[5])
    return y * 4 + qn


def split_label(q: str) -> str:
    k = quarter_key(q)
    if k <= quarter_key(TRAIN_END):
        return "train"
    if k <= quarter_key(VALID_END):
        return "valid"
    return "test"


def grade_series(prob: pd.Series) -> pd.Series:
    """분위수 기준 A~D(상위 25%=A, 하위 25%=D). 구버전 grade()의 고정 임계값(A>=70 등)은 "다음분기
    점포수 증가확률"(양성비율 ~44%) 기준으로 잡힌 값이라, 폐업률 기반 성장확률(대부분 70~100 사이에
    몰림 - 분기당 폐업은 원래 드문 사건)에 그대로 쓰면 거의 전부 A가 나와 변별력이 없어진다. 대신
    이 스코어링 배치 안에서의 상대적 위치로 등급을 매겨 항상 A~D가 고르게 나오게 한다.
    """
    q25, q50, q75 = prob.quantile([0.25, 0.5, 0.75])
    return pd.cut(prob, bins=[-np.inf, q25, q50, q75, np.inf], labels=["D", "C", "B", "A"]).astype(str)


def train_store_model() -> dict:
    """점포단위 분류기(참고용) - label_h2 + 최근1분기이탈률. DB에는 안 들어감, 결과만 json/pkl로 보존."""
    store = pd.read_csv(eda_paths.STORE_TRAIN_TABLE_CSV, dtype={"행정동코드": str})
    store["split"] = store["기준분기"].map(split_label)
    for c in CAT_COLS:
        store[c] = store[c].astype("category")
    store = store.dropna(subset=[STORE_TARGET] + NUM_COLS).copy()

    Xtr = store.loc[store["split"] == "train", CAT_COLS + NUM_COLS]
    ytr = store.loc[store["split"] == "train", STORE_TARGET]
    Xva = store.loc[store["split"] == "valid", CAT_COLS + NUM_COLS]
    yva = store.loc[store["split"] == "valid", STORE_TARGET]
    Xte = store.loc[store["split"] == "test", CAT_COLS + NUM_COLS]
    yte = store.loc[store["split"] == "test", STORE_TARGET]

    model = lgb.LGBMClassifier(
        objective="binary", n_estimators=2000, learning_rate=0.05,
        num_leaves=63, min_child_samples=50, random_state=42, verbosity=-1,
    )
    model.fit(
        Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="average_precision",
        categorical_feature=CAT_COLS, callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    pred = model.predict_proba(Xte)[:, 1]
    pr_auc = average_precision_score(yte, pred)
    roc_auc = roc_auc_score(yte, pred)
    print(f"[점포단위-참고용] best_iter={model.best_iteration_} PR-AUC={pr_auc:.4f} ROC-AUC={roc_auc:.4f}")

    results = {
        "label": STORE_TARGET, "features": CAT_COLS + NUM_COLS,
        "split": {"train_end": TRAIN_END, "valid_end": VALID_END},
        "test_n": int(len(yte)), "test_positive_rate": float(yte.mean()),
        "main": {"pr_auc": float(pr_auc), "roc_auc": float(roc_auc), "best_iteration": int(model.best_iteration_)},
    }
    with open(eda_paths.MODEL_STORE_RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    joblib.dump({"model": model, "features": CAT_COLS + NUM_COLS}, eda_paths.LGBM_MODEL_STORE_PKL)
    print(f"저장: {eda_paths.MODEL_STORE_RESULTS_JSON} / {eda_paths.LGBM_MODEL_STORE_PKL}")
    return results


def train_cell_model() -> tuple[lgb.LGBMRegressor, pd.DataFrame]:
    """셀단위(중분류) 회귀 - 주력 프로덕션 모델. n>=30 필터로 학습, 전체 셀 추론은 별도 함수에서."""
    cell = pd.read_csv(eda_paths.CELL_TRAIN_TABLE_CSV)
    cell["split"] = cell["기준분기"].map(split_label)
    # 전체 cell에 astype("category") 적용 -> cell30 학습과 최신 분기 추론이 동일한 카테고리 코드를 공유
    for c in CELL_CAT:
        cell[c] = cell[c].astype("category")

    cell_labeled = cell.dropna(subset=[CELL_TARGET])  # 라벨 판정 불가한 최신 분기 제외
    cell30 = cell_labeled[cell_labeled["점포수"] >= CELL_MIN_STORES].copy()

    cXtr = cell30.loc[cell30["split"] == "train", CELL_CAT + CELL_NUM]
    cytr = cell30.loc[cell30["split"] == "train", CELL_TARGET]
    cXva = cell30.loc[cell30["split"] == "valid", CELL_CAT + CELL_NUM]
    cyva = cell30.loc[cell30["split"] == "valid", CELL_TARGET]
    cXte = cell30.loc[cell30["split"] == "test", CELL_CAT + CELL_NUM]
    cyte = cell30.loc[cell30["split"] == "test", CELL_TARGET]

    model = lgb.LGBMRegressor(
        objective="regression", n_estimators=1000, learning_rate=0.05,
        num_leaves=31, min_child_samples=20, random_state=42, verbosity=-1,
    )
    model.fit(
        cXtr, cytr, eval_set=[(cXva, cyva)], categorical_feature=CELL_CAT,
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    pred = model.predict(cXte)
    rho, _ = spearmanr(pred, cyte)
    top10 = pred >= np.quantile(pred, 0.9)  # 분위수 기준. "상위 10개 고정" 방식은 채택하지 않음(eda 3-5절)
    lift = cyte[top10].mean() / cyte.mean()
    print(f"[셀단위-주력] best_iter={model.best_iteration_} 스피어만={rho:.4f} 리프트={lift:.3f}x (test n={len(cyte)})")

    results = {
        "label": f"{CELL_TARGET} (중분류 셀 집계, n>={CELL_MIN_STORES})", "features": CELL_CAT + CELL_NUM,
        "test_n": int(len(cyte)), "spearman": float(rho), "lift_top10pct": float(lift),
        "best_iteration": int(model.best_iteration_),
    }
    with open(eda_paths.MODEL_CELL_RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    joblib.dump({"model": model, "features": CELL_CAT + CELL_NUM}, eda_paths.LGBM_MODEL_CELL_PKL)
    print(f"저장: {eda_paths.MODEL_CELL_RESULTS_JSON} / {eda_paths.LGBM_MODEL_CELL_PKL}")
    return model, cell


def score_latest_quarter(cell_model: lgb.LGBMRegressor, cell: pd.DataFrame) -> pd.DataFrame:
    """학습된 셀 회귀 모델을 실제 최신 분기(n>=30 필터 없이 전체 셀)에 추론 -> scores.csv(ScoreData 원천).

    폐업률이 NaN인(라벨 판정 범위를 벗어난, 즉 결과를 아직 아무도 모르는) 최신 분기 행이 정확히
    지금 스코어링해야 할 대상이다 - 그래서 n>=30/dropna 필터를 건 학습용 cell30이 아니라 원본 cell
    전체에서 최신 분기를 뽑는다.
    """
    latest_q = max(cell["기준분기"].unique(), key=quarter_key)
    latest = cell[cell["기준분기"] == latest_q].copy()
    latest["통합카테고리"] = latest["상권업종중분류명"]
    latest["기준_년분기_코드"] = latest["기준분기"].map(quarter_to_code)
    latest["예측폐업률"] = cell_model.predict(latest[CELL_CAT + CELL_NUM])
    latest["성장확률"] = ((1 - latest["예측폐업률"]) * 100).clip(0, 100).round(1)
    latest["등급"] = grade_series(latest["성장확률"])
    latest["업종내_순위"] = latest.groupby("통합카테고리", observed=True)["성장확률"].rank(ascending=False, method="min").astype(int)
    latest["업종내_전체동수"] = latest.groupby("통합카테고리", observed=True)["행정동명"].transform("count")
    latest["상위_퍼센트"] = (latest["업종내_순위"] / latest["업종내_전체동수"] * 100).round(1)

    out = latest[[
        "행정동명", "통합카테고리", "기준_년분기_코드",
        "성장확률", "등급", "업종내_순위", "업종내_전체동수", "상위_퍼센트",
    ]]
    print(f"최신 분기({latest_q}) 스코어링: {len(out):,}개 셀")
    return out


def main():
    print("점포단위(참고용) 모델 학습 중...")
    train_store_model()

    print("셀단위(중분류, 주력) 모델 학습 중...")
    cell_model, cell = train_cell_model()

    print("최신 분기 전체 셀 추론 중...")
    scores = score_latest_quarter(cell_model, cell)
    out_path = eda_paths.PROCESSED_DATA_DIR / "scores.csv"
    scores.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장: {out_path} ({len(scores):,}행)")


if __name__ == "__main__":
    main()
