"""
폐업 예측 모델 1차 학습 — 라벨 3종(v2/v3/v3b) x 타깃 2종(h1/h2) 비교,
베이스라인 3종, 점포단위/행정동x업종 집계단위 평가, 카드매출 가치 실험.

시간 기준 분할(무작위 분할 금지): Train ≤2023Q2 / Valid 2023Q3~2024Q2 / Test 2024Q3~라벨가용마지막분기.

사용법:
    python ai/train_closure_model.py
"""
import json
import os
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.metrics import average_precision_score, roc_auc_score

warnings.filterwarnings("ignore")
load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

TRAIN_END = "2023Q2"
VALID_END = "2024Q2"

VERSIONS = {
    "v2": {"path": PROCESSED_DATA_DIR / "train_table_v2.csv", "h1": "label_h1", "h2": "label_h2"},
    "v3": {"path": PROCESSED_DATA_DIR / "train_table_v3.csv", "h1": "label_h1_v3", "h2": "label_h2_v3"},
    "v3b": {"path": PROCESSED_DATA_DIR / "train_table_v3b.csv", "h1": "label_h1_v3b", "h2": "label_h2_v3b"},
}

# ==================== feature 제외 목록 (사유 포함, 로그로 남김) ====================
EXCLUDE_REASONS = {
    "카드매출_공통업종_후보": "카드매출 계열 — 2024-02~12 원본 결측, 시기상관 누수 위험",
    "카드매출_행정동내구성비": "카드매출 계열 — 상동",
    "카드매출_업종내행정동share": "카드매출 계열 — 상동",
    "카드매출_구성비_변화": "카드매출 계열 — 상동",
    "카드매출_구성비_추세4": "카드매출 계열 — 상동",
    "전환율": "전환율 계열 — 카드매출 결측 구간과 동일한 누수 위험",
    "전환율_변화": "전환율 계열 — 상동",
    "전환율_추세4": "전환율 계열 — 상동",
    "사업체통계_carry_forward": "carry-forward 플래그 — 사실상 '2024~25년 여부' 시간식별자",
    "인구통계_carry_forward": "carry-forward 플래그 — 상동",
    "B": "시간 식별자(관측분기 문자열) — 분할 키로만 사용, feature 제외",
    "최초등장분기": "시간 식별자(절대 분기 문자열) — 분기_Q(계절성)만 허용",
    "is_filled": "라벨링 파이프라인 메타데이터 — 예측 시점엔 존재하지 않는 정보",
    "갭길이": "라벨링 파이프라인 메타데이터 — 상동",
    "상가업소번호": "ID — 예측력 없는 식별자",
    "행정동코드": "ID — 행정동명과 중복(범주형으로 행정동명 사용)",
    "지번주소": "ID — 자유텍스트 주소, 좌표(경도/위도)로 위치정보 대체됨",
    "상권업종소분류명": "범주형 과다분화(248종) — 대/중분류만 categorical로 사용",
}
CATEGORICAL_COLS = ["행정동명", "상권업종대분류명", "상권업종중분류명", "분기_Q", "임대료_매핑그룹", "카드매출_공통업종_후보"]
CARD_COLS = ["카드매출_공통업종_후보", "카드매출_행정동내구성비", "카드매출_업종내행정동share",
             "카드매출_구성비_변화", "카드매출_구성비_추세4"]

LABEL_ALL_COLS = {"label_h1", "label_h2", "label_h1_v3", "label_h2_v3", "label_h1_v3b", "label_h2_v3b"}


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def get_feature_cols(df: pd.DataFrame, include_card: bool = False):
    exclude = set(EXCLUDE_REASONS.keys()) | LABEL_ALL_COLS
    if not include_card:
        pass  # 카드 계열은 이미 EXCLUDE_REASONS에 있음
    else:
        exclude -= set(CARD_COLS)
    feats = [c for c in df.columns if c not in exclude]
    return feats


def prepare_xy(df: pd.DataFrame, feats: list, target: str, cat_cols: list):
    X = df[feats].copy()
    for c in X.columns:
        if c in cat_cols:
            continue
        if X[c].dtype == object or str(X[c].dtype) == "bool":
            # CSV 왕복 과정에서 True/False가 문자열로 저장돼 object가 된 컬럼(대규모점포_최근4분기신규 등) 보정
            X[c] = X[c].map({"True": 1, "False": 0, True: 1, False: 0}).astype(float)
    for c in cat_cols:
        if c in X.columns:
            X[c] = X[c].astype("category")
    y = df[target]
    return X, y


def time_split(df: pd.DataFrame, target: str):
    labeled = df.dropna(subset=[target]).copy()
    last_q = max(labeled["B"].unique(), key=quarter_sort_key)
    train = labeled[labeled["B"].map(quarter_sort_key) <= quarter_sort_key(TRAIN_END)]
    valid = labeled[(labeled["B"].map(quarter_sort_key) > quarter_sort_key(TRAIN_END)) &
                     (labeled["B"].map(quarter_sort_key) <= quarter_sort_key(VALID_END))]
    test = labeled[labeled["B"].map(quarter_sort_key) > quarter_sort_key(VALID_END)]
    return train, valid, test, last_q


def recall_at_k(y_true, y_score, k_pct):
    n = len(y_score)
    k = max(1, int(n * k_pct))
    order = np.argsort(-y_score)
    top_k_idx = order[:k]
    total_pos = y_true.sum()
    if total_pos == 0:
        return np.nan
    return y_true.iloc[top_k_idx].sum() / total_pos


def eval_scores(y_true, y_score, label=""):
    y_true = y_true.reset_index(drop=True)
    y_score = pd.Series(y_score).reset_index(drop=True)
    pr_auc = average_precision_score(y_true, y_score) if y_true.sum() > 0 else np.nan
    roc_auc = roc_auc_score(y_true, y_score) if y_true.nunique() > 1 else np.nan
    r10 = recall_at_k(y_true, y_score.values, 0.10)
    r20 = recall_at_k(y_true, y_score.values, 0.20)
    return {"PR-AUC": pr_auc, "ROC-AUC": roc_auc, "Recall@10%": r10, "Recall@20%": r20, "n": len(y_true), "pos_rate": y_true.mean()}


def baseline_scores(df_split: pd.DataFrame):
    """B0 관성 / B1 업력 / B2 상수, df_split엔 이미 존재하는 feature만 사용(누수 없음)."""
    b0 = (df_split["중분류_폐업수"] / df_split["중분류_점포수"].replace(0, np.nan)).fillna(0)
    b1 = -df_split["업력_분기수"].fillna(df_split["업력_분기수"].median())
    b2 = pd.Series(df_split["_train_pos_rate"].iloc[0], index=df_split.index)
    return {"B0_관성": b0, "B1_업력": b1, "B2_상수": b2}


def run_one(version_name: str, target_kind: str, include_card: bool = False, save_artifacts: bool = False,
            restrict_card_rows: bool = None):
    cfg = VERSIONS[version_name]
    df = pd.read_csv(cfg["path"], encoding="utf-8-sig", dtype={"행정동코드": str, "B": str, "상가업소번호": str})
    target = cfg[target_kind]

    if restrict_card_rows is None:
        restrict_card_rows = include_card
    if restrict_card_rows:
        df = df.dropna(subset=CARD_COLS, how="any")

    feats = get_feature_cols(df, include_card=include_card)
    cat_cols = [c for c in CATEGORICAL_COLS if c in feats]

    train, valid, test, last_q = time_split(df, target)
    if len(test) == 0 or len(train) == 0 or len(valid) == 0:
        return {"version": version_name, "target": target_kind, "error": "구간 데이터 부족", "last_label_q": last_q}

    train_pos_rate = train[target].mean()
    for split in (train, valid, test):
        split["_train_pos_rate"] = train_pos_rate

    X_train, y_train = prepare_xy(train, feats, target, cat_cols)
    X_valid, y_valid = prepare_xy(valid, feats, target, cat_cols)
    X_test, y_test = prepare_xy(test, feats, target, cat_cols)

    pos = y_train.sum()
    neg = len(y_train) - pos
    scale_pos_weight = neg / pos if pos > 0 else 1.0

    model = lgb.LGBMClassifier(
        objective="binary", n_estimators=1000, learning_rate=0.05,
        num_leaves=63, scale_pos_weight=scale_pos_weight,
        random_state=42, verbosity=-1,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_valid, y_valid)],
        eval_metric="average_precision",
        categorical_feature=cat_cols,
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )

    pred_valid = model.predict_proba(X_valid)[:, 1]
    pred_test = model.predict_proba(X_test)[:, 1]

    result = {
        "version": version_name, "target": target_kind, "target_col": target,
        "include_card": include_card, "last_label_q": last_q,
        "train_range": f"{train['B'].min()}~{train['B'].max()}",
        "valid_range": f"{valid['B'].min()}~{valid['B'].max()}",
        "test_range": f"{test['B'].min()}~{test['B'].max()}",
        "n_train": len(train), "n_valid": len(valid), "n_test": len(test),
        "n_features": len(feats), "scale_pos_weight": scale_pos_weight,
    }

    result["model_valid"] = eval_scores(y_valid, pred_valid)
    result["model_test"] = eval_scores(y_test, pred_test)

    bl_test = baseline_scores(test)
    for name, score in bl_test.items():
        result[f"{name}_test"] = eval_scores(y_test, score)

    fi = pd.Series(model.feature_importances_, index=feats).sort_values(ascending=False)
    result["feature_importance_top20"] = fi.head(20).to_dict()

    # ---------------- 행정동x업종 집계 평가 (test) ----------------
    cell_df = test[["행정동명", "상권업종중분류명"]].copy()
    cell_df["y_true"] = y_test.values
    cell_df["y_pred"] = pred_test
    cell_agg = cell_df.groupby(["행정동명", "상권업종중분류명"]).agg(
        실제폐업률=("y_true", "mean"), 예측위험도=("y_pred", "mean"), n=("y_true", "size")
    ).reset_index()
    cell_agg_reliable = cell_agg[cell_agg["n"] >= 5]
    spearman = cell_agg_reliable["예측위험도"].corr(cell_agg_reliable["실제폐업률"], method="spearman")
    overall_rate = cell_df["y_true"].mean()
    top10 = cell_agg_reliable.sort_values("예측위험도", ascending=False).head(10)
    top10_actual_rate = top10["실제폐업률"].mean()
    lift = top10_actual_rate / overall_rate if overall_rate > 0 else np.nan

    result["cell_spearman"] = spearman
    result["cell_n_reliable"] = len(cell_agg_reliable)
    result["cell_overall_rate"] = overall_rate
    result["cell_top10_actual_rate"] = top10_actual_rate
    result["cell_top10_lift"] = lift
    result["cell_top20"] = cell_agg_reliable.sort_values("예측위험도", ascending=False).head(20)[
        ["행정동명", "상권업종중분류명", "예측위험도", "실제폐업률", "n"]
    ].to_dict("records")

    if save_artifacts:
        # LightGBM의 C레벨 save_model()이 한글 포함 경로에서 실패하는 Windows 이슈가 있어
        # 파이썬 파일 I/O로 우회(model_to_string 사용, 유니코드 경로 안전)
        model_str = model.booster_.model_to_string()
        with open(MODELS_DIR / f"lgbm_{version_name}_{target_kind}.txt", "w", encoding="utf-8") as f:
            f.write(model_str)
        pred_out = test[["상가업소번호", "B", "행정동명", "상권업종중분류명"]].copy()
        pred_out["y_true"] = y_test.values
        pred_out["y_pred"] = pred_test
        pred_out.to_csv(PROCESSED_DATA_DIR / "predictions_test.csv", index=False, encoding="utf-8-sig")
        cell_agg.to_csv(PROCESSED_DATA_DIR / "cell_risk_test.csv", index=False, encoding="utf-8-sig")

    return result


def print_result(r):
    if "error" in r:
        print(f"  [{r['version']}/{r['target']}] 오류: {r['error']}")
        return
    print(f"\n--- {r['version']} / {r['target']} (target_col={r['target_col']}, card={r['include_card']}) ---")
    print(f"  라벨 가용 마지막 분기: {r['last_label_q']}")
    print(f"  Train {r['train_range']}({r['n_train']:,}) / Valid {r['valid_range']}({r['n_valid']:,}) / "
          f"Test {r['test_range']}({r['n_test']:,}) / feature수 {r['n_features']}")
    print(f"  [모델] Valid: {r['model_valid']}")
    print(f"  [모델] Test:  {r['model_test']}")
    for name in ["B0_관성", "B1_업력", "B2_상수"]:
        print(f"  [{name}] Test: {r[f'{name}_test']}")
    print(f"  [집계] 스피어만={r['cell_spearman']:.3f} (신뢰셀 n={r['cell_n_reliable']}), "
          f"전체폐업률={r['cell_overall_rate']*100:.2f}%, top10실제폐업률={r['cell_top10_actual_rate']*100:.2f}%, "
          f"리프트={r['cell_top10_lift']:.2f}x")
    print(f"  [feature importance top10] {list(r['feature_importance_top20'].items())[:10]}")


def main():
    all_results = {}

    print("=" * 90)
    print("[1] 라벨 3종 x 타깃 2종 비교 (v2/v3/v3b x h1/h2)")
    print("=" * 90)
    for version_name in ["v2", "v3", "v3b"]:
        for target_kind in ["h2", "h1"]:
            save = (version_name == "v3" and target_kind == "h2")
            r = run_one(version_name, target_kind, include_card=False, save_artifacts=save)
            all_results[f"{version_name}_{target_kind}"] = r
            print_result(r)

    print("\n" + "=" * 90)
    print("[2] 카드매출 가치 실험 (v3, label_h2, 동일 행 집합에서 feature만 껐다/켰다 — 공정 비교)")
    print("=" * 90)
    r_no_card_full = run_one("v3", "h2", include_card=False, save_artifacts=False, restrict_card_rows=False)
    r_no_card_fair = run_one("v3", "h2", include_card=False, save_artifacts=False, restrict_card_rows=True)
    r_with_card = run_one("v3", "h2", include_card=True, save_artifacts=False, restrict_card_rows=True)
    all_results["card_ablation_no_card_full_data"] = r_no_card_full
    all_results["card_ablation_no_card_same_rows"] = r_no_card_fair
    all_results["card_ablation_with_card_same_rows"] = r_with_card
    print("\n[참고: 전체 데이터, 카드 feature 미사용]")
    print_result(r_no_card_full)
    print("\n[공정비교 A: 카드결측아닌행만, 카드 feature 미사용]")
    print_result(r_no_card_fair)
    print("\n[공정비교 B: 카드결측아닌행만, 카드 feature 포함]")
    print_result(r_with_card)

    with open(PROCESSED_DATA_DIR / "model_comparison_results.json", "w", encoding="utf-8") as f:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items()}
            if isinstance(o, (np.floating, np.integer)):
                return float(o)
            return o
        json.dump(clean(all_results), f, ensure_ascii=False, indent=2)
    print(f"\n전체 결과 저장: {PROCESSED_DATA_DIR / 'model_comparison_results.json'}")


if __name__ == "__main__":
    main()
