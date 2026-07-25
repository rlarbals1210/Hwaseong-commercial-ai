"""
모델 재학습 — 1차 학습 실패 원인(early stopping 과도하게 이름, 시간 대리변수 의존,
셀 평가 표본 부족) 수정판.

수정 1: eval_metric 명시, early_stopping 100+, n_estimators 2000+, scale_pos_weight on/off 비교
수정 2: 임대가격지수/공실률 등 시간대리변수 제외 + 저변별력 feature 자동 탐지·보고
수정 3: 셀 평가 최소 점포수 30 (10/30/50 민감도 표)
수정 4: 셀 단위(행정동x대분류x분기) 회귀 모델 병행

메인 라벨: v3 (v3b는 2025년 라벨 없어 학습 불가). 비교용 v2도 실행.

사용법:
    python ai/train_closure_model_v2.py
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
    "v3": {"path": PROCESSED_DATA_DIR / "train_table_v3.csv", "h2": "label_h2_v3"},
    "v2": {"path": PROCESSED_DATA_DIR / "train_table_v2.csv", "h2": "label_h2"},
}

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
    "B": "시간 식별자 — 분할 키로만 사용",
    "최초등장분기": "시간 식별자(절대 분기 문자열)",
    "is_filled": "라벨링 메타데이터",
    "갭길이": "라벨링 메타데이터",
    "상가업소번호": "ID",
    "행정동코드": "ID — 행정동명과 중복",
    "지번주소": "ID — 자유텍스트",
    "상권업종소분류명": "범주형 과다분화(248종)",
    # 이번 턴에 새로 추가: 시간 대리변수로 작동하는 임대료/공실률
    "임대가격지수": "화성시를 동탄/병점/경기광역 3그룹으로만 나눈 값 — 행정동 변별력 거의 없음, 사실상 분기 식별자",
    "공실률": "임대가격지수와 동일 사유",
}
CATEGORICAL_COLS = ["행정동명", "상권업종대분류명", "상권업종중분류명", "분기_Q", "임대료_매핑그룹", "카드매출_공통업종_후보"]


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def get_feature_cols(df: pd.DataFrame):
    exclude = set(EXCLUDE_REASONS.keys()) | {"label_h1", "label_h2", "label_h1_v3", "label_h2_v3",
                                              "label_h1_v3b", "label_h2_v3b"}
    return [c for c in df.columns if c not in exclude]


def report_low_variance_features(df: pd.DataFrame, feats: list):
    print("\n" + "=" * 80)
    print("[수정 2] 분기 내 행정동별 고유값 개수 진단 (5개 미만이면 저변별력 후보)")
    print("=" * 80)
    # 성능: feature마다 매번 전체 groupby 다시 하지 않도록 (B,행정동명) 기준 1회만 dedup
    dedup = df.drop_duplicates(subset=["B", "행정동명"])
    rows = []
    for c in feats:
        if c not in dedup.columns:
            continue
        if dedup[c].dtype == object and c not in CATEGORICAL_COLS:
            continue
        per_q = dedup.groupby("B")[c].nunique()
        rows.append((c, per_q.median(), per_q.min(), per_q.max()))
    diag = pd.DataFrame(rows, columns=["feature", "분기별_중앙값_고유값수", "최소", "최대"]).sort_values("분기별_중앙값_고유값수")
    print(diag.to_string(index=False))
    low_var = diag[diag["분기별_중앙값_고유값수"] < 5]["feature"].tolist()
    print(f"\n고유값 5개 미만 feature(추가 제거 후보): {low_var}")
    return low_var


def prepare_xy(df: pd.DataFrame, feats: list, target: str, cat_cols: list):
    X = df[feats].copy()
    for c in X.columns:
        if c in cat_cols:
            continue
        if X[c].dtype == object or str(X[c].dtype) == "bool":
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


def eval_scores(y_true, y_score):
    y_true = y_true.reset_index(drop=True)
    y_score = pd.Series(y_score).reset_index(drop=True)
    pr_auc = average_precision_score(y_true, y_score) if y_true.sum() > 0 else np.nan
    roc_auc = roc_auc_score(y_true, y_score) if y_true.nunique() > 1 else np.nan
    return {"PR-AUC": round(pr_auc, 4), "ROC-AUC": round(roc_auc, 4),
            "Recall@10%": round(recall_at_k(y_true, y_score.values, 0.10), 4),
            "Recall@20%": round(recall_at_k(y_true, y_score.values, 0.20), 4),
            "n": len(y_true), "pos_rate": round(y_true.mean(), 4)}


def baseline_scores(df_split: pd.DataFrame, train_pos_rate: float):
    b0 = (df_split["중분류_폐업수"] / df_split["중분류_점포수"].replace(0, np.nan)).fillna(0)
    b1 = -df_split["업력_분기수"].fillna(df_split["업력_분기수"].median())
    b2 = pd.Series(train_pos_rate, index=df_split.index)
    return {"B0_관성": b0, "B1_업력": b1, "B2_상수": b2}


def train_store_model(train, valid, feats, cat_cols, target, use_scale_pos_weight: bool, tag: str):
    X_train, y_train = prepare_xy(train, feats, target, cat_cols)
    X_valid, y_valid = prepare_xy(valid, feats, target, cat_cols)

    pos, neg = y_train.sum(), len(y_train) - y_train.sum()
    scale_pos_weight = (neg / pos) if (use_scale_pos_weight and pos > 0) else 1.0

    params = dict(
        objective="binary", n_estimators=2500, learning_rate=0.05,
        num_leaves=63, min_child_samples=50, scale_pos_weight=scale_pos_weight,
        random_state=42, verbosity=-1,
    )
    print(f"\n  [{tag}] 학습 파라미터: n_estimators={params['n_estimators']}, lr={params['learning_rate']}, "
          f"num_leaves={params['num_leaves']}, min_child_samples={params['min_child_samples']}, "
          f"scale_pos_weight={scale_pos_weight:.2f}")

    model = lgb.LGBMClassifier(**params)
    model.fit(
        X_train, y_train, eval_set=[(X_valid, y_valid)], eval_metric="average_precision",
        categorical_feature=cat_cols, callbacks=[lgb.early_stopping(100, verbose=False)],
    )

    best_iter = model.best_iteration_
    total_splits = int(model.feature_importances_.sum())
    print(f"  [{tag}] best_iteration={best_iter} / n_estimators={params['n_estimators']} "
          f"/ 총 split 횟수={total_splits}")
    if best_iter is not None and best_iter < 100:
        print(f"  [{tag}] ⚠ best_iteration이 {best_iter}로 여전히 낮음 — 학습 실패 지속 가능성")

    return model, X_train, X_valid, best_iter, total_splits


def eval_store_model(model, df_split, feats, cat_cols, target):
    X, y = prepare_xy(df_split, feats, target, cat_cols)
    pred = model.predict_proba(X)[:, 1]
    return pred, eval_scores(y, pred)


def cell_eval(df_split, y_true_arr, pred_arr, group_cols, min_n_list):
    cell_df = df_split[group_cols].copy()
    cell_df["y_true"] = y_true_arr
    cell_df["y_pred"] = pred_arr
    cell_agg = cell_df.groupby(group_cols).agg(
        실제폐업률=("y_true", "mean"), 예측위험도=("y_pred", "mean"), n=("y_true", "size")
    ).reset_index()

    results = {}
    for min_n in min_n_list:
        sub = cell_agg[cell_agg["n"] >= min_n]
        if len(sub) < 5:
            results[min_n] = {"n_cells": len(sub), "spearman": np.nan, "lift": np.nan}
            continue
        sp = sub["예측위험도"].corr(sub["실제폐업률"], method="spearman")
        overall = cell_df["y_true"].mean()
        top10 = sub.sort_values("예측위험도", ascending=False).head(10)
        lift = top10["실제폐업률"].mean() / overall if overall > 0 else np.nan
        results[min_n] = {"n_cells": len(sub), "spearman": round(sp, 3), "lift": round(lift, 3),
                           "top10_actual_rate": round(top10["실제폐업률"].mean(), 4)}
    return cell_agg, results


def run_store_pipeline(version_name: str, feats: list, cat_cols: list):
    cfg = VERSIONS[version_name]
    df = pd.read_csv(cfg["path"], encoding="utf-8-sig", dtype={"행정동코드": str, "B": str, "상가업소번호": str})
    target = cfg["h2"]

    train, valid, test, last_q = time_split(df, target)
    train_pos_rate = train[target].mean()

    print(f"\n{'='*80}\n[{version_name}] 점포단위 모델 (target={target})\n{'='*80}")
    print(f"  라벨 가용 마지막 분기: {last_q}")
    print(f"  Train {train['B'].min()}~{train['B'].max()}({len(train):,}) / "
          f"Valid {valid['B'].min()}~{valid['B'].max()}({len(valid):,}) / "
          f"Test {test['B'].min()}~{test['B'].max()}({len(test):,})")

    results = {}
    for use_spw in [True, False]:
        tag = f"{version_name}_spw={use_spw}"
        model, X_train, X_valid, best_iter, total_splits = train_store_model(
            train, valid, feats, cat_cols, target, use_spw, tag)

        pred_valid, score_valid = eval_store_model(model, valid, feats, cat_cols, target)
        pred_test, score_test = eval_store_model(model, test, feats, cat_cols, target)
        print(f"  [{tag}] Valid: {score_valid}")
        print(f"  [{tag}] Test:  {score_test}")

        bl = baseline_scores(test, train_pos_rate)
        bl_scores = {name: eval_scores(test[target], s) for name, s in bl.items()}
        for name, sc in bl_scores.items():
            print(f"  [{tag}][{name}] Test: {sc}")

        cell_agg, cell_results = cell_eval(
            test, test[target].values, pred_test, ["행정동명", "상권업종중분류명"], [10, 30, 50])
        print(f"  [{tag}] 셀평가(중분류, 최소n 10/30/50): {cell_results}")

        fi = pd.Series(model.feature_importances_, index=feats).sort_values(ascending=False)

        results[f"scale_pos_weight={use_spw}"] = {
            "best_iteration": best_iter, "total_splits": total_splits,
            "valid": score_valid, "test": score_test, "baselines_test": bl_scores,
            "cell_eval": cell_results, "fi_top20": fi.head(20).to_dict(),
        }

        if use_spw:
            main_model, main_pred_test, main_test = model, pred_test, test

    return results, main_model, main_pred_test, main_test, feats, cat_cols, target, train, valid


def build_cell_dataset(sbiz_all_path, labels_v3_path):
    """행정동 x 대분류 x 분기 셀 데이터셋 (타깃=B+2 폐업률, 연속값)."""
    sbiz = pd.read_csv(sbiz_all_path, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "기준분기": str})
    labels = pd.read_csv(labels_v3_path, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "기준분기": str})

    quarters = sorted(sbiz["기준분기"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}
    next2 = {quarters[i]: quarters[i + 2] for i in range(len(quarters) - 2)}

    store_cnt = sbiz.groupby(["행정동명", "상권업종대분류명", "기준분기"])["상가업소번호"].nunique().rename("점포수").reset_index()

    labeled = labels.dropna(subset=["is_closed_v3"])
    closure = labeled.groupby(["행정동명", "상권업종대분류명", "기준분기"])["is_closed_v3"].mean().rename("폐업률").reset_index()
    closure_lookup = closure.set_index(["행정동명", "상권업종대분류명", "기준분기"])["폐업률"]

    def get_label(row):
        t2 = next2.get(row["기준분기"])
        if t2 is None:
            return np.nan
        key = (row["행정동명"], row["상권업종대분류명"], t2)
        return closure_lookup.get(key, np.nan)

    store_cnt["target_h2"] = store_cnt.apply(get_label, axis=1)
    store_cnt = store_cnt.rename(columns={"기준분기": "B"})
    return store_cnt


def run_cell_pipeline(sbiz_all_path, labels_v3_path, train_table_v3_path):
    print(f"\n{'='*80}\n[수정 4] 셀 단위(행정동x대분류x분기) 회귀 모델\n{'='*80}")
    cell_df = build_cell_dataset(sbiz_all_path, labels_v3_path)
    print(f"  셀 데이터셋 행 수: {len(cell_df):,}, 점포수 중앙값: {cell_df['점포수'].median():.0f}")

    tv3 = pd.read_csv(train_table_v3_path, encoding="utf-8-sig", dtype={"B": str}, usecols=lambda c: c not in (
        "상가업소번호", "지번주소", "행정동코드", "상권업종중분류명", "상권업종소분류명", "경도", "위도",
        "is_filled", "갭길이", "label_h1", "label_h2_v3", "label_h1_v3"))
    dae_cols = [c for c in tv3.columns if c.startswith("대분류_") or c in
                ("인구", "고령비율", "인구_증감률", "전체_사업체수", "전체_종사자수", "전체_사업체당평균종사자수",
                 "세대수", "등록인구", "외국인비율", "고령비율_kosis", "임대료_매핑그룹", "분기_Q",
                 "유동인구_행정동share", "유동인구_주중주말비", "유동인구_share_변화", "유동인구_share_추세4")]
    dong_dae_ref = tv3[["행정동명", "상권업종대분류명", "B"] + dae_cols].drop_duplicates(
        subset=["행정동명", "상권업종대분류명", "B"])

    cell_df = cell_df.merge(dong_dae_ref, on=["행정동명", "상권업종대분류명", "B"], how="left")

    labeled = cell_df.dropna(subset=["target_h2"]).copy()
    last_q = max(labeled["B"].unique(), key=quarter_sort_key)
    train = labeled[labeled["B"].map(quarter_sort_key) <= quarter_sort_key(TRAIN_END)]
    valid = labeled[(labeled["B"].map(quarter_sort_key) > quarter_sort_key(TRAIN_END)) &
                     (labeled["B"].map(quarter_sort_key) <= quarter_sort_key(VALID_END))]
    test = labeled[labeled["B"].map(quarter_sort_key) > quarter_sort_key(VALID_END)]
    print(f"  라벨 가용 마지막 분기: {last_q}")
    print(f"  Train({len(train):,}) / Valid({len(valid):,}) / Test({len(test):,})")

    feats = ["행정동명", "상권업종대분류명"] + [c for c in dae_cols if c not in ("임대가격지수", "공실률")]
    cat_cols = [c for c in ["행정동명", "상권업종대분류명", "분기_Q", "임대료_매핑그룹"] if c in feats]

    X_train, y_train = prepare_xy(train, feats, "target_h2", cat_cols)
    X_valid = prepare_xy(valid, feats, "target_h2", cat_cols)[0]
    X_test = prepare_xy(test, feats, "target_h2", cat_cols)[0]

    model = lgb.LGBMRegressor(
        objective="regression", n_estimators=2500, learning_rate=0.05,
        num_leaves=31, min_child_samples=20, random_state=42, verbosity=-1,
    )
    model.fit(
        X_train, y_train, sample_weight=train["점포수"],
        eval_set=[(X_valid, valid["target_h2"])], eval_sample_weight=[valid["점포수"]],
        eval_metric="l2", categorical_feature=cat_cols,
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    print(f"  best_iteration={model.best_iteration_} / 총 split={int(model.feature_importances_.sum())}")

    pred_test = model.predict(X_test)
    sp = pd.Series(pred_test).corr(test["target_h2"].reset_index(drop=True), method="spearman")
    overall = test["target_h2"].mean()
    test_r = test.copy()
    test_r["pred"] = pred_test
    top10 = test_r.sort_values("pred", ascending=False).head(10)
    lift = top10["target_h2"].mean() / overall if overall > 0 else np.nan
    print(f"  Test 스피어만={sp:.3f}, 전체평균={overall*100:.2f}%, top10실제={top10['target_h2'].mean()*100:.2f}%, "
          f"리프트={lift:.2f}x")

    fi = pd.Series(model.feature_importances_, index=feats).sort_values(ascending=False)
    print(f"  feature importance top10: {fi.head(10).to_dict()}")

    return {"spearman": sp, "lift": lift, "overall_rate": overall, "top10_rate": top10["target_h2"].mean(),
            "best_iteration": model.best_iteration_, "fi_top20": fi.head(20).to_dict(),
            "n_train": len(train), "n_test": len(test)}


def compare_store_vs_cell_agg(main_model, main_pred_test, main_test, cell_reg_result):
    print(f"\n{'='*80}\n[비교] 점포단위 모델 집계 vs 셀단위 회귀 모델\n{'='*80}")
    store_cell = main_test[["행정동명", "상권업종대분류명"]].copy()
    store_cell["y_true"] = main_test["label_h2_v3"].values
    store_cell["y_pred"] = main_pred_test
    agg = store_cell.groupby(["행정동명", "상권업종대분류명"]).agg(
        실제=("y_true", "mean"), 예측=("y_pred", "mean"), n=("y_true", "size"))
    agg30 = agg[agg["n"] >= 30]
    sp_store_agg = agg30["예측"].corr(agg30["실제"], method="spearman")
    overall = store_cell["y_true"].mean()
    top10 = agg30.sort_values("예측", ascending=False).head(10)
    lift_store_agg = top10["실제"].mean() / overall if overall > 0 else np.nan
    print(f"  [점포단위모델 -> 대분류 집계, n>=30] 스피어만={sp_store_agg:.3f}, 리프트={lift_store_agg:.2f}x (신뢰셀 n={len(agg30)})")
    print(f"  [셀단위 회귀모델 직접]           스피어만={cell_reg_result['spearman']:.3f}, "
          f"리프트={cell_reg_result['lift']:.2f}x")


def main():
    v3_df = pd.read_csv(VERSIONS["v3"]["path"], encoding="utf-8-sig", dtype={"B": str}, nrows=None)
    feats = get_feature_cols(v3_df)
    cat_cols = [c for c in CATEGORICAL_COLS if c in feats]
    print(f"모델 입력 feature 수: {len(feats)}개 (제외 {len(EXCLUDE_REASONS)}개, 사유는 스크립트 상단 참고)")

    low_var = report_low_variance_features(v3_df, feats)

    all_results = {}
    for version_name in ["v3", "v2"]:
        results, main_model, main_pred_test, main_test, _, _, target, train, valid = run_store_pipeline(
            version_name, feats, cat_cols)
        all_results[version_name] = results
        if version_name == "v3":
            v3_main = (main_model, main_pred_test, main_test)

    cell_reg_result = run_cell_pipeline(
        PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv",
        PROCESSED_DATA_DIR / "sbiz_labels_v3.csv",
        VERSIONS["v3"]["path"],
    )
    all_results["cell_regression_v3"] = cell_reg_result

    compare_store_vs_cell_agg(*v3_main, cell_reg_result)

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return o

    with open(PROCESSED_DATA_DIR / "model_v2_comparison_results.json", "w", encoding="utf-8") as f:
        json.dump(clean(all_results), f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {PROCESSED_DATA_DIR / 'model_v2_comparison_results.json'}")


if __name__ == "__main__":
    main()
