"""
3차 모델 — 업력 좌측절단(left-truncation) 보정 + 잔여 대리변수 제거 + 앙상블 + 셀회귀 강화.

업력_분기수(소진공 최초등장 기준)는 2020Q4 이전 업력을 알 수 없어 관측 시작점에서
잘려있다(Train 구간 최대 10분기, Test 구간 최대 18분기 — 절단 정도가 구간마다 달라
모델이 업력의 진짜 관계를 배울 수 없음). 인허가일자로 실제 업력을 아는 점포(80.8%)만
그 값을 쓰고, 나머지는 NaN 처리(절단값 대체 금지 — 잘못된 관계를 학습시키므로).

2차와 동일 설정 유지: scale_pos_weight 미사용, eval_metric=average_precision,
early_stopping=100, lr=0.05, n_estimators=2000, 라벨 v3, 시간기준 분할.

사용법:
    python ai/train_closure_model_v3.py
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
SBIZ_ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
LABELS_V3_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v3.csv"

TRAIN_END = "2023Q2"
VALID_END = "2024Q2"
TARGET = "label_h2_v3"

EXCLUDE_REASONS = {
    "카드매출_공통업종_후보": "카드매출 계열 — 결측/누수 위험", "카드매출_행정동내구성비": "카드매출 계열",
    "카드매출_업종내행정동share": "카드매출 계열", "카드매출_구성비_변화": "카드매출 계열",
    "카드매출_구성비_추세4": "카드매출 계열",
    "전환율": "전환율 계열", "전환율_변화": "전환율 계열", "전환율_추세4": "전환율 계열",
    "사업체통계_carry_forward": "carry-forward 플래그(시간식별자)", "인구통계_carry_forward": "carry-forward 플래그",
    "B": "시간 식별자", "최초등장분기": "시간 식별자(절대 분기)",
    "is_filled": "라벨링 메타데이터", "갭길이": "라벨링 메타데이터",
    "상가업소번호": "ID", "행정동코드": "ID", "지번주소": "ID",
    "상권업종소분류명": "범주형 과다분화(248종)",
    "임대가격지수": "동탄/병점/경기 3그룹 대리변수(2차에서 제외)",
    "공실률": "동탄/병점/경기 3그룹 대리변수(2차에서 제외)",
    "업력_분기수": "좌측절단 — 이번 턴에서 업력_신규로 대체",
    "업력_분기수_보정": "미매칭시 절단값으로 fallback되는 구버전 — 업력_신규로 대체",
    "임대료_매핑그룹": "임대가격지수와 동일한 3그룹 대리변수(범주형이라도 잔재)",
    "대규모점포_행정동내개수": "전 분기 값이 2종뿐 — 사실상 이진, 정보량 낮음",
}
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


def compute_true_age(train: pd.DataFrame, quarters: list, q_idx: dict) -> pd.Series:
    print("\n[수정 1] 업력 재정의 — 인허가일자 기준 실제 업력만 사용(미매칭은 NaN)")
    permits = load_permit_dates()
    train = train.copy()
    train["지번주소_norm"] = train["지번주소"].map(norm_addr)
    train = train.merge(permits, on="지번주소_norm", how="left")

    def date_to_our_quarter(dt):
        if pd.isna(dt):
            return None
        return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"

    # 절대 분기 인덱스(연*4+분기)로 계산 — 관측기간(2020Q4~) 이전의 오래된 인허가일자도
    # 정상적으로 다뤄야 함(오래된 가게일수록 이 케이스가 많아 q_idx 멤버십 체크로 걸러내면
    # 안 됨 — 실제로 이 버그로 14.5%까지 떨어졌던 것을 수정).
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
    match_rate = valid.mean() * 100
    print(f"  실제 업력 확보 비율: {match_rate:.1f}% (나머지는 NaN)")
    return age


def report_age_distribution(df, age_col, split_masks):
    print(f"\n[검증] {age_col} 분포 — Train/Valid/Test 비교")
    for name, mask in split_masks.items():
        s = df.loc[mask, age_col].dropna()
        if len(s) == 0:
            print(f"  {name}: 유효값 없음")
            continue
        print(f"  {name}: n={len(s):,}(결측제외), 평균={s.mean():.2f}, 중앙값={s.median():.1f}, "
              f"최대={s.max():.0f}, p25={s.quantile(.25):.1f}, p75={s.quantile(.75):.1f}, p95={s.quantile(.95):.1f}")


def get_feature_cols(df):
    exclude = set(EXCLUDE_REASONS.keys()) | {"label_h1", "label_h2", "label_h1_v3", "label_h2_v3",
                                              "label_h1_v3b", "label_h2_v3b"}
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
        return agg, {"n_cells": len(sub), "spearman": np.nan, "lift": np.nan}
    sp = sub["예측"].corr(sub["실제"], method="spearman")
    overall = cell_df["y_true"].mean()
    top10 = sub.sort_values("예측", ascending=False).head(10)
    lift = top10["실제"].mean() / overall if overall > 0 else np.nan
    return agg, {"n_cells": len(sub), "spearman": round(sp, 3), "lift": round(lift, 3),
                 "top10_actual_rate": round(top10["실제"].mean(), 4)}


def main():
    print(f"[로드] {TRAIN_V3_PATH}")
    df = pd.read_csv(TRAIN_V3_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "B": str, "상가업소번호": str})
    quarters = sorted(df["B"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}

    df["업력_신규"] = compute_true_age(df, quarters, q_idx)

    train_mask = df["B"].map(quarter_sort_key) <= quarter_sort_key(TRAIN_END)
    valid_mask = (df["B"].map(quarter_sort_key) > quarter_sort_key(TRAIN_END)) & \
                 (df["B"].map(quarter_sort_key) <= quarter_sort_key(VALID_END))
    test_mask = df["B"].map(quarter_sort_key) > quarter_sort_key(VALID_END)

    print("\n--- 구버전(업력_분기수, 좌측절단) ---")
    report_age_distribution(df, "업력_분기수", {"Train": train_mask, "Valid": valid_mask, "Test": test_mask})
    print("\n--- 신버전(업력_신규, 인허가 기준) ---")
    report_age_distribution(df, "업력_신규", {"Train": train_mask, "Valid": valid_mask, "Test": test_mask})

    feats = get_feature_cols(df)
    feats = [f for f in feats if f != "업력_신규"] + ["업력_신규"]
    cat_cols = [c for c in CATEGORICAL_COLS if c in feats]
    print(f"\n모델 입력 feature 수: {len(feats)}개")

    train, valid, test, last_q = time_split(df, TARGET)
    print(f"\nTrain {train['B'].min()}~{train['B'].max()}({len(train):,}) / "
          f"Valid {valid['B'].min()}~{valid['B'].max()}({len(valid):,}) / "
          f"Test {test['B'].min()}~{test['B'].max()}({len(test):,})")

    X_train, y_train = prepare_xy(train, feats, TARGET, cat_cols)
    X_valid, y_valid = prepare_xy(valid, feats, TARGET, cat_cols)
    X_test, y_test = prepare_xy(test, feats, TARGET, cat_cols)

    print(f"\n[학습] {LGB_PARAMS}")
    model = lgb.LGBMClassifier(**LGB_PARAMS)
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], eval_metric="average_precision",
              categorical_feature=cat_cols, callbacks=[lgb.early_stopping(100, verbose=False)])
    print(f"best_iteration={model.best_iteration_} / 총 split={int(model.feature_importances_.sum())}")

    pred_valid = model.predict_proba(X_valid)[:, 1]
    pred_test = model.predict_proba(X_test)[:, 1]
    score_valid = eval_scores(y_valid, pred_valid)
    score_test = eval_scores(y_test, pred_test)
    print(f"\n[모델] Valid: {score_valid}")
    print(f"[모델] Test:  {score_test}")
    print("(2차 결과 참고용: Test PR-AUC=0.0761, ROC-AUC=0.5508)")

    print("\n" + "=" * 80)
    print("[수정 3] B1(업력) 베이스라인 재정의 및 비교")
    print("=" * 80)
    age_median_train = train["업력_신규"].median()
    b1_new = -test["업력_신규"].fillna(age_median_train)
    b1_old = -test["업력_분기수"].fillna(test["업력_분기수"].median())
    score_b1_new = eval_scores(y_test, b1_new)
    score_b1_old = eval_scores(y_test, b1_old)
    print(f"[B1_업력_신규] Test: {score_b1_new}")
    print(f"[B1_업력_구버전(참고)] Test: {score_b1_old}")
    if score_test["PR-AUC"] > score_b1_new["PR-AUC"]:
        print("-> 모델이 신규 B1을 PR-AUC 기준으로 이김")
    else:
        print("-> 모델이 여전히 신규 B1에 못 미침")

    print("\n" + "=" * 80)
    print("[수정 3] 앙상블 실험 (모델 순위 x 업력 순위)")
    print("=" * 80)
    rank_model = rankdata(pred_test)
    rank_b1 = rankdata(b1_new)
    ensemble = (rank_model + rank_b1) / 2
    score_ens = eval_scores(y_test, ensemble)
    print(f"[앙상블(순위평균)] Test: {score_ens}")
    print(f"  모델 단독 PR-AUC={score_test['PR-AUC']}, B1 단독={score_b1_new['PR-AUC']}, 앙상블={score_ens['PR-AUC']}")

    print("\n" + "=" * 80)
    print("[셀 평가, n>=30] 점포단위 모델 집계")
    print("=" * 80)
    _, cell_r_jung = cell_eval(test, y_test.values, pred_test, ["행정동명", "상권업종중분류명"], min_n=30)
    _, cell_r_dae = cell_eval(test, y_test.values, pred_test, ["행정동명", "상권업종대분류명"], min_n=30)
    print(f"중분류 집계: {cell_r_jung}")
    print(f"대분류 집계: {cell_r_dae}")

    fi = pd.Series(model.feature_importances_, index=feats).sort_values(ascending=False)
    print(f"\n[feature importance top20]\n{fi.head(20).to_string()}")

    # ==================== 수정 4: 셀 단위 회귀 (대분류/중분류, n>=30) ====================
    print("\n" + "=" * 80)
    print("[수정 4] 셀 단위 회귀 모델 (n>=30 필터, 대분류 vs 중분류)")
    print("=" * 80)

    sbiz = pd.read_csv(SBIZ_ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "상권업종중분류명": str, "기준분기": str})
    labels = pd.read_csv(LABELS_V3_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "상권업종중분류명": str, "기준분기": str})
    next2 = {quarters[i]: quarters[i + 2] for i in range(len(quarters) - 2)}
    labeled_stores = labels.dropna(subset=["is_closed_v3"])

    def run_cell_regression(unit_col, unit_name):
        store_cnt = sbiz.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"].nunique().rename("점포수").reset_index()
        closure = labeled_stores.groupby(["행정동명", unit_col, "기준분기"])["is_closed_v3"].mean().rename("폐업률").reset_index()
        closure_lookup = closure.set_index(["행정동명", unit_col, "기준분기"])["폐업률"]

        def get_label(row):
            t2 = next2.get(row["기준분기"])
            if t2 is None:
                return np.nan
            return closure_lookup.get((row["행정동명"], row[unit_col], t2), np.nan)

        store_cnt["target_h2"] = store_cnt.apply(get_label, axis=1)
        store_cnt = store_cnt.rename(columns={"기준분기": "B", unit_col: "업종"})
        store_cnt = store_cnt[store_cnt["점포수"] >= 30]

        prefix = "대분류" if unit_col == "상권업종대분류명" else "중분류"
        ref_cols = [c for c in df.columns if c.startswith(prefix + "_") or c in
                    ("인구", "고령비율", "인구_증감률", "전체_사업체수", "전체_종사자수", "전체_사업체당평균종사자수",
                     "세대수", "등록인구", "외국인비율", "고령비율_kosis", "분기_Q",
                     "유동인구_행정동share", "유동인구_주중주말비", "유동인구_share_변화", "유동인구_share_추세4")]
        ref = df[["행정동명", unit_col, "B"] + ref_cols].drop_duplicates(subset=["행정동명", unit_col, "B"])
        ref = ref.rename(columns={unit_col: "업종"})
        cell_df = store_cnt.merge(ref, on=["행정동명", "업종", "B"], how="left")

        labeled = cell_df.dropna(subset=["target_h2"]).copy()
        tr = labeled[labeled["B"].map(quarter_sort_key) <= quarter_sort_key(TRAIN_END)]
        va = labeled[(labeled["B"].map(quarter_sort_key) > quarter_sort_key(TRAIN_END)) &
                     (labeled["B"].map(quarter_sort_key) <= quarter_sort_key(VALID_END))]
        te = labeled[labeled["B"].map(quarter_sort_key) > quarter_sort_key(VALID_END)]
        print(f"\n  [{unit_name}, n>=30] 데이터: Train({len(tr):,})/Valid({len(va):,})/Test({len(te):,})")
        if len(tr) < 30 or len(va) < 10 or len(te) < 10:
            print(f"  [{unit_name}] 데이터 부족으로 스킵")
            return None

        feat_cols = ["행정동명", "업종"] + ref_cols
        cat = [c for c in ["행정동명", "업종", "분기_Q"] if c in feat_cols]
        Xtr, ytr = prepare_xy(tr, feat_cols, "target_h2", cat)
        Xva, yva = prepare_xy(va, feat_cols, "target_h2", cat)
        Xte, yte = prepare_xy(te, feat_cols, "target_h2", cat)

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
        lift = top10["target_h2"].mean() / overall if overall > 0 else np.nan
        print(f"  [{unit_name}] best_iter={reg.best_iteration_}, 스피어만={sp:.3f}, "
              f"전체평균={overall*100:.2f}%, top10실제={top10['target_h2'].mean()*100:.2f}%, 리프트={lift:.2f}x")
        return {"unit": unit_name, "spearman": sp, "lift": lift, "n_train": len(tr), "n_test": len(te),
                "best_iteration": reg.best_iteration_}

    result_dae = run_cell_regression("상권업종대분류명", "대분류")
    result_jung = run_cell_regression("상권업종중분류명", "중분류")

    print("\n" + "=" * 80)
    print("[종합 비교] 점포집계 vs 셀회귀(대분류) vs 셀회귀(중분류)")
    print("=" * 80)
    print(f"  점포단위모델->중분류집계(n>=30): 스피어만={cell_r_jung['spearman']}, 리프트={cell_r_jung['lift']}")
    print(f"  점포단위모델->대분류집계(n>=30): 스피어만={cell_r_dae['spearman']}, 리프트={cell_r_dae['lift']}")
    if result_dae:
        print(f"  셀회귀(대분류, n>=30): 스피어만={result_dae['spearman']:.3f}, 리프트={result_dae['lift']:.2f}")
    if result_jung:
        print(f"  셀회귀(중분류, n>=30): 스피어만={result_jung['spearman']:.3f}, 리프트={result_jung['lift']:.2f}")

    all_results = {
        "age_fix": {"model_test": score_test, "model_valid": score_valid,
                    "b1_new_test": score_b1_new, "b1_old_test": score_b1_old, "ensemble_test": score_ens},
        "cell_store_agg": {"중분류": cell_r_jung, "대분류": cell_r_dae},
        "cell_regression": {"대분류": result_dae, "중분류": result_jung},
        "fi_top20": fi.head(20).to_dict(),
        "best_iteration": model.best_iteration_,
    }

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        return o

    with open(PROCESSED_DATA_DIR / "model_v3_comparison_results.json", "w", encoding="utf-8") as f:
        json.dump(clean(all_results), f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {PROCESSED_DATA_DIR / 'model_v3_comparison_results.json'}")


if __name__ == "__main__":
    main()
