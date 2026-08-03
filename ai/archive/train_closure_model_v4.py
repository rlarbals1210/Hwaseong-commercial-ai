"""
예측 기간 확대 실험 — label_h1to4(B+1~B+4 중 아무때나 폐업=1) vs 기존 label_h2.

label_h1to4 정의: 점포의 마지막 등장분기(last_idx, v3 개념과 동일)가
B..B+4 사이(즉 last_idx - B_idx <= 4)면 1. B+4를 확보 못하는 마지막 4개 분기는 보류.
(last_idx==B인 경우도 포함 — "B+1 시점엔 이미 없음"이므로 B+1~B+4 창 안에 폐업이 속함)

3차에서 확정한 feature 세트(업력_신규 포함, scale_pos_weight 미사용) 그대로 사용.

사용법:
    python ai/train_closure_model_v4.py
"""
import json
import os
import re
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score, roc_auc_score

warnings.filterwarnings("ignore")
load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
DATASET_DIR = PROJECT_ROOT / "Hwaseong-commercial-ai-main-dataset"
PERMIT_DIR = DATASET_DIR / "화성시_인허가데이터"

TRAIN_V3_PATH = PROCESSED_DATA_DIR / "train_table_v3.csv"
PANEL_FILLED_PATH = PROCESSED_DATA_DIR / "sbiz_panel_filled.csv"
SBIZ_ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"

TRAIN_END = "2023Q2"
VALID_END = "2024Q2"
WINDOW = 4

EXCLUDE_REASONS_KEYS = [
    "카드매출_공통업종_후보", "카드매출_행정동내구성비", "카드매출_업종내행정동share",
    "카드매출_구성비_변화", "카드매출_구성비_추세4", "전환율", "전환율_변화", "전환율_추세4",
    "사업체통계_carry_forward", "인구통계_carry_forward", "B", "최초등장분기",
    "is_filled", "갭길이", "상가업소번호", "행정동코드", "지번주소", "상권업종소분류명",
    "임대가격지수", "공실률", "업력_분기수", "업력_분기수_보정", "임대료_매핑그룹",
    "대규모점포_행정동내개수",
]
CATEGORICAL_COLS = ["행정동명", "상권업종대분류명", "상권업종중분류명", "분기_Q"]
LGB_PARAMS = dict(objective="binary", n_estimators=2000, learning_rate=0.05,
                   num_leaves=63, min_child_samples=50, random_state=42, verbosity=-1)


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def norm_addr(s) -> str:
    if pd.isna(s):
        return ""
    s = re.sub(r"경기도|화성시|효행구|만세구|동탄구|병점구", "", str(s))
    m = re.search(r"\d+(-\d+)?", s)
    if m:
        s = s[:m.end()]
    return "".join(s.split())


def to_date(s):
    return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")


def load_permit_dates():
    frames = []
    for f in sorted(PERMIT_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(f, encoding="cp949", dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
        frames.append(pd.DataFrame({
            "지번주소_norm": df["지번주소"].map(norm_addr) if "지번주소" in df.columns else "",
            "인허가일자_dt": to_date(df.get("인허가일자")),
        }))
    permits = pd.concat(frames, ignore_index=True)
    permits = permits[permits["지번주소_norm"] != ""].dropna(subset=["인허가일자_dt"])
    return permits.drop_duplicates(subset="지번주소_norm", keep="first")


def compute_true_age(train, q_idx):
    permits = load_permit_dates()
    train = train.copy()
    train["지번주소_norm"] = train["지번주소"].map(norm_addr)
    train = train.merge(permits, on="지번주소_norm", how="left")

    def abs_quarter_idx(y, m):
        return y * 4 + (m - 1) // 3

    train["인허가_절대분기"] = train["인허가일자_dt"].apply(
        lambda d: abs_quarter_idx(d.year, d.month) if pd.notna(d) else np.nan)
    b_year = train["B"].str[:4].astype(int)
    b_q = train["B"].str[-1].astype(int)
    train["B_절대분기"] = b_year * 4 + (b_q - 1)

    valid = train["인허가_절대분기"].notna() & (train["인허가_절대분기"] <= train["B_절대분기"])
    age = pd.Series(np.nan, index=train.index)
    age.loc[valid] = train.loc[valid, "B_절대분기"] - train.loc[valid, "인허가_절대분기"]
    return age


def build_label_h1to4(panel: pd.DataFrame, quarters: list, q_idx: dict) -> pd.Series:
    panel = panel.copy()
    panel["idx"] = panel["기준분기"].map(q_idx)
    last_idx_by_store = panel.groupby("상가업소번호")["idx"].max()
    n_q = len(quarters)

    def label_row(row):
        if row["idx"] + WINDOW >= n_q:
            return np.nan
        return 1 if (last_idx_by_store[row["상가업소번호"]] - row["idx"]) <= WINDOW else 0

    return panel.apply(label_row, axis=1)


def get_feature_cols(df):
    exclude = set(EXCLUDE_REASONS_KEYS) | {"label_h1", "label_h2", "label_h1_v3", "label_h2_v3",
                                            "label_h1_v3b", "label_h2_v3b", "label_h1to4"}
    return [c for c in df.columns if c not in exclude]


def prepare_xy(df, feats, target, cat_cols):
    X = df[feats].copy()
    for c in X.columns:
        if c in cat_cols:
            continue
        if X[c].dtype == object or str(X[c].dtype) == "bool":
            X[c] = X[c].map({"True": 1, "False": 0, True: 1, False: 0}).astype(float)
    for c in cat_cols:
        if c in X.columns:
            X[c] = X[c].astype("category")
    return X, df[target]


def time_split(df, target):
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
    total_pos = y_true.sum()
    if total_pos == 0:
        return np.nan
    return y_true.iloc[order[:k]].sum() / total_pos


def eval_scores(y_true, y_score):
    y_true = y_true.reset_index(drop=True)
    y_score = pd.Series(y_score).reset_index(drop=True)
    pr = average_precision_score(y_true, y_score) if y_true.sum() > 0 else np.nan
    roc = roc_auc_score(y_true, y_score) if y_true.nunique() > 1 else np.nan
    return {"PR-AUC": round(pr, 4), "ROC-AUC": round(roc, 4),
            "Recall@10%": round(recall_at_k(y_true, y_score.values, 0.10), 4),
            "Recall@20%": round(recall_at_k(y_true, y_score.values, 0.20), 4),
            "n": len(y_true), "pos_rate": round(y_true.mean(), 4)}


def cell_eval(df_split, y_true_arr, pred_arr, group_cols, min_n=30):
    cell_df = df_split[group_cols].copy()
    cell_df["y_true"] = y_true_arr
    cell_df["y_pred"] = pred_arr
    agg = cell_df.groupby(group_cols).agg(실제=("y_true", "mean"), 예측=("y_pred", "mean"), n=("y_true", "size")).reset_index()
    sub = agg[agg["n"] >= min_n]
    if len(sub) < 5:
        return {"n_cells": len(sub), "spearman": np.nan, "lift": np.nan}
    sp = sub["예측"].corr(sub["실제"], method="spearman")
    overall = cell_df["y_true"].mean()
    top10 = sub.sort_values("예측", ascending=False).head(10)
    lift = top10["실제"].mean() / overall if overall > 0 else np.nan
    return {"n_cells": len(sub), "spearman": round(sp, 3), "lift": round(lift, 3),
            "top10_actual_rate": round(top10["실제"].mean(), 4)}


def run_store_model(df, target, feats, cat_cols, tag):
    train, valid, test, last_q = time_split(df, target)
    print(f"\n[{tag}] 라벨 가용 마지막 분기: {last_q}, 양성비율(train)={train[target].mean()*100:.2f}%")
    print(f"  Train {train['B'].min()}~{train['B'].max()}({len(train):,}) / "
          f"Valid {valid['B'].min()}~{valid['B'].max()}({len(valid):,}) / "
          f"Test {test['B'].min()}~{test['B'].max()}({len(test):,})")

    X_train, y_train = prepare_xy(train, feats, target, cat_cols)
    X_valid, y_valid = prepare_xy(valid, feats, target, cat_cols)
    X_test, y_test = prepare_xy(test, feats, target, cat_cols)

    model = lgb.LGBMClassifier(**LGB_PARAMS)
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], eval_metric="average_precision",
              categorical_feature=cat_cols, callbacks=[lgb.early_stopping(100, verbose=False)])
    print(f"  best_iteration={model.best_iteration_} / 총 split={int(model.feature_importances_.sum())}")

    pred_valid = model.predict_proba(X_valid)[:, 1]
    pred_test = model.predict_proba(X_test)[:, 1]
    sv, st = eval_scores(y_valid, pred_valid), eval_scores(y_test, pred_test)
    print(f"  [모델] Valid: {sv}")
    print(f"  [모델] Test:  {st}")

    age_median = train["업력_신규"].median()
    b1 = -test["업력_신규"].fillna(age_median)
    sb1 = eval_scores(y_test, b1)
    b0 = (test["중분류_폐업수"] / test["중분류_점포수"].replace(0, np.nan)).fillna(0)
    sb0 = eval_scores(y_test, b0)
    b2 = pd.Series(train[target].mean(), index=test.index)
    sb2 = eval_scores(y_test, b2)
    print(f"  [B0_관성] Test: {sb0}")
    print(f"  [B1_업력] Test: {sb1}")
    print(f"  [B2_상수] Test: {sb2}")

    improve_over_b1 = (st["PR-AUC"] - sb1["PR-AUC"]) / sb1["PR-AUC"] * 100 if sb1["PR-AUC"] else np.nan
    improve_over_b2 = (st["PR-AUC"] - sb2["PR-AUC"]) / sb2["PR-AUC"] * 100 if sb2["PR-AUC"] else np.nan
    print(f"  베이스라인 대비 개선율: B1 대비 {improve_over_b1:+.1f}%, B2 대비 {improve_over_b2:+.1f}%")

    ens = (rankdata(pred_test) + rankdata(b1)) / 2
    s_ens = eval_scores(y_test, ens)
    print(f"  [앙상블] Test: {s_ens} (모델 PR-AUC={st['PR-AUC']}, B1={sb1['PR-AUC']}, 앙상블={s_ens['PR-AUC']})")

    cell_jung = cell_eval(test, y_test.values, pred_test, ["행정동명", "상권업종중분류명"], 30)
    cell_dae = cell_eval(test, y_test.values, pred_test, ["행정동명", "상권업종대분류명"], 30)
    print(f"  [셀평가 n>=30] 중분류: {cell_jung}")
    print(f"  [셀평가 n>=30] 대분류: {cell_dae}")

    return {"tag": tag, "target": target, "last_label_q": last_q,
            "pos_rate_train": round(train[target].mean(), 4),
            "n_train": len(train), "n_valid": len(valid), "n_test": len(test),
            "valid": sv, "test": st, "b0": sb0, "b1": sb1, "b2": sb2, "ensemble": s_ens,
            "improve_over_b1_pct": improve_over_b1, "improve_over_b2_pct": improve_over_b2,
            "cell_jung": cell_jung, "cell_dae": cell_dae}


def run_cell_regression(unit_col, unit_name, sbiz, target_lookup_fn, quarters, df_ref):
    store_cnt = sbiz.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"].nunique().rename("점포수").reset_index()
    store_cnt["target"] = store_cnt.apply(lambda r: target_lookup_fn(r["행정동명"], r[unit_col], r["기준분기"]), axis=1)
    store_cnt = store_cnt.rename(columns={"기준분기": "B", unit_col: "업종"})
    store_cnt = store_cnt[store_cnt["점포수"] >= 30]

    prefix = "대분류" if unit_col == "상권업종대분류명" else "중분류"
    ref_cols = [c for c in df_ref.columns if c.startswith(prefix + "_") or c in
                ("인구", "고령비율", "인구_증감률", "전체_사업체수", "전체_종사자수", "전체_사업체당평균종사자수",
                 "세대수", "등록인구", "외국인비율", "고령비율_kosis", "분기_Q",
                 "유동인구_행정동share", "유동인구_주중주말비", "유동인구_share_변화", "유동인구_share_추세4")]
    ref = df_ref[["행정동명", unit_col, "B"] + ref_cols].drop_duplicates(subset=["행정동명", unit_col, "B"])
    ref = ref.rename(columns={unit_col: "업종"})
    cell_df = store_cnt.merge(ref, on=["행정동명", "업종", "B"], how="left")

    labeled = cell_df.dropna(subset=["target"]).copy()
    tr = labeled[labeled["B"].map(quarter_sort_key) <= quarter_sort_key(TRAIN_END)]
    va = labeled[(labeled["B"].map(quarter_sort_key) > quarter_sort_key(TRAIN_END)) &
                 (labeled["B"].map(quarter_sort_key) <= quarter_sort_key(VALID_END))]
    te = labeled[labeled["B"].map(quarter_sort_key) > quarter_sort_key(VALID_END)]
    if len(tr) < 30 or len(va) < 10 or len(te) < 10:
        print(f"  [{unit_name}] 데이터 부족으로 스킵 ({len(tr)}/{len(va)}/{len(te)})")
        return None

    feat_cols = ["행정동명", "업종"] + ref_cols
    cat = [c for c in ["행정동명", "업종", "분기_Q"] if c in feat_cols]
    Xtr, ytr = prepare_xy(tr, feat_cols, "target", cat)
    Xva, yva = prepare_xy(va, feat_cols, "target", cat)
    Xte, yte = prepare_xy(te, feat_cols, "target", cat)

    reg = lgb.LGBMRegressor(objective="regression", n_estimators=2000, learning_rate=0.05,
                             num_leaves=31, min_child_samples=20, random_state=42, verbosity=-1)
    reg.fit(Xtr, ytr, sample_weight=tr["점포수"], eval_set=[(Xva, yva)], eval_sample_weight=[va["점포수"]],
            eval_metric="l2", categorical_feature=cat, callbacks=[lgb.early_stopping(100, verbose=False)])

    pred = reg.predict(Xte)
    sp = pd.Series(pred).corr(yte.reset_index(drop=True), method="spearman")
    overall = yte.mean()
    te_r = te.copy()
    te_r["pred"] = pred
    top10 = te_r.sort_values("pred", ascending=False).head(10)
    lift = top10["target"].mean() / overall if overall > 0 else np.nan
    print(f"  [{unit_name}] n(tr/va/te)={len(tr)}/{len(va)}/{len(te)}, best_iter={reg.best_iteration_}, "
          f"스피어만={sp:.3f}, 전체평균={overall*100:.2f}%, top10실제={top10['target'].mean()*100:.2f}%, 리프트={lift:.2f}x")
    return {"spearman": round(sp, 3), "lift": round(lift, 3), "n_test": len(te), "overall_rate": round(overall, 4)}


def main():
    print(f"[로드] {TRAIN_V3_PATH}")
    df = pd.read_csv(TRAIN_V3_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "B": str, "상가업소번호": str})
    quarters = sorted(df["B"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}

    df["업력_신규"] = compute_true_age(df, q_idx)

    print(f"\n[로드] {PANEL_FILLED_PATH}")
    panel = pd.read_csv(PANEL_FILLED_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "기준분기": str})
    print(f"\nlabel_h1to4(B+1~B+4 중 폐업, 보류=마지막 {WINDOW}개 분기) 생성 중...")
    label_h1to4_by_row = build_label_h1to4(panel, quarters, q_idx)
    panel_key = panel[["상가업소번호", "기준분기"]].copy()
    panel_key["label_h1to4"] = label_h1to4_by_row.values
    panel_key = panel_key.rename(columns={"기준분기": "B"})

    df = df.merge(panel_key, on=["상가업소번호", "B"], how="left")

    labeled_h1to4 = df.dropna(subset=["label_h1to4"])
    print(f"label_h1to4 양성비율(전체): {labeled_h1to4['label_h1to4'].mean()*100:.2f}% "
          f"(참고: label_h2_v3 양성비율 {df['label_h2_v3'].dropna().mean()*100:.2f}%)")
    print(f"label_h1to4 라벨 가용 마지막 분기: {max(labeled_h1to4['B'].unique(), key=quarter_sort_key)}")

    feats = get_feature_cols(df)
    cat_cols = [c for c in CATEGORICAL_COLS if c in feats]
    print(f"모델 입력 feature 수: {len(feats)}개")

    all_results = {}
    for target in ["label_h2_v3", "label_h1to4"]:
        tag = "A_label_h2" if target == "label_h2_v3" else "B_label_h1to4"
        print(f"\n{'='*80}\n[{tag}] 점포단위 모델\n{'='*80}")
        r = run_store_model(df, target, feats, cat_cols, tag)
        all_results[tag] = r

    print(f"\n{'='*80}\n[셀 회귀] label_h2 vs label_h1to4 x 대분류/중분류\n{'='*80}")
    sbiz = pd.read_csv(SBIZ_ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "상권업종중분류명": str, "기준분기": str})

    next2 = {quarters[i]: quarters[i + 2] for i in range(len(quarters) - 2)}
    labels_v3_path = PROCESSED_DATA_DIR / "sbiz_labels_v3.csv"
    labels_v3 = pd.read_csv(labels_v3_path, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "상권업종중분류명": str, "기준분기": str})
    labeled_stores_v3 = labels_v3.dropna(subset=["is_closed_v3"])

    for unit_col, unit_name in [("상권업종대분류명", "대분류"), ("상권업종중분류명", "중분류")]:
        closure_h2 = labeled_stores_v3.groupby(["행정동명", unit_col, "기준분기"])["is_closed_v3"].mean()

        def lookup_h2(dong, industry, q, _closure=closure_h2):
            t2 = next2.get(q)
            if t2 is None:
                return np.nan
            return _closure.get((dong, industry, t2), np.nan)

        print(f"\n--- label_h2, {unit_name} ---")
        r1 = run_cell_regression(unit_col, unit_name, sbiz, lookup_h2, quarters, df)
        all_results[f"cell_h2_{unit_name}"] = r1

    # panel(sbiz_panel_filled.csv)에 이미 상권업종대/중분류명 컬럼이 있으므로 sbiz와
    # 다시 merge하면 이름 충돌(_x/_y)이 남 -> panel 자체 컬럼을 그대로 사용
    cell_h1to4_cache = {}
    for unit_col, unit_name in [("상권업종대분류명", "대분류"), ("상권업종중분류명", "중분류")]:
        cell_avg = panel.merge(
            panel_key.rename(columns={"B": "기준분기"}), on=["상가업소번호", "기준분기"], how="left"
        )
        agg = cell_avg.dropna(subset=["label_h1to4", unit_col]).groupby(
            ["행정동명", unit_col, "기준분기"])["label_h1to4"].mean()
        cell_h1to4_cache[unit_col] = agg

        def lookup_h1to4(dong, industry, q, _agg=agg):
            return _agg.get((dong, industry, q), np.nan)

        print(f"\n--- label_h1to4, {unit_name} ---")
        r2 = run_cell_regression(unit_col, unit_name, sbiz, lookup_h1to4, quarters, df)
        all_results[f"cell_h1to4_{unit_name}"] = r2

    print(f"\n{'='*80}\n[종합 비교]\n{'='*80}")
    print(f"{'항목':<20}{'label_h2':<25}{'label_h1to4':<25}")
    print(f"{'양성비율':<20}{all_results['A_label_h2']['pos_rate_train']:<25}{all_results['B_label_h1to4']['pos_rate_train']:<25}")
    print(f"{'모델 Test PR-AUC':<20}{all_results['A_label_h2']['test']['PR-AUC']:<25}{all_results['B_label_h1to4']['test']['PR-AUC']:<25}")
    print(f"{'B1대비개선율(%)':<20}{all_results['A_label_h2']['improve_over_b1_pct']:<25.1f}{all_results['B_label_h1to4']['improve_over_b1_pct']:<25.1f}")
    print(f"{'셀중분류 스피어만':<20}{all_results['A_label_h2']['cell_jung']['spearman']:<25}{all_results['B_label_h1to4']['cell_jung']['spearman']:<25}")
    print(f"{'셀중분류 리프트':<20}{all_results['A_label_h2']['cell_jung']['lift']:<25}{all_results['B_label_h1to4']['cell_jung']['lift']:<25}")
    print(f"{'셀대분류 스피어만':<20}{all_results['A_label_h2']['cell_dae']['spearman']:<25}{all_results['B_label_h1to4']['cell_dae']['spearman']:<25}")
    print(f"{'셀대분류 리프트':<20}{all_results['A_label_h2']['cell_dae']['lift']:<25}{all_results['B_label_h1to4']['cell_dae']['lift']:<25}")

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        return o

    with open(PROCESSED_DATA_DIR / "model_v4_comparison_results.json", "w", encoding="utf-8") as f:
        json.dump(clean(all_results), f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {PROCESSED_DATA_DIR / 'model_v4_comparison_results.json'}")


if __name__ == "__main__":
    main()
