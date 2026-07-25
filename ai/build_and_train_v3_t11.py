"""
갭 필링 임계값 8 -> 11 상향 후 최종(v3-t11) 라벨·feature·모델 재구축.
목적: 2024Q4/2025Q3에 남아있던 장기갭(9~11분기) 재등장 잔여 이상치를 마저 제거해
정직한 최종 성능을 재측정한다(성능 향상이 목적이 아니라 왜곡 제거가 목적).

임계값 8 버전 파일은 전부 보존, 이번 결과는 전부 _t11 접미사로 별도 저장.

사용법:
    python ai/build_and_train_v3_t11.py
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

ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
TRAIN_V3_PATH = PROCESSED_DATA_DIR / "train_table_v3.csv"  # 임계값8 — '나머지 feature' 승계용
LABELS_V1_PATH = PROCESSED_DATA_DIR / "sbiz_labels.csv"
LABELS_V2_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v2.csv"

PANEL_T11_PATH = PROCESSED_DATA_DIR / "sbiz_panel_filled_t11.csv"
LABELS_T11_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v3_t11.csv"
TRAIN_T11_PATH = PROCESSED_DATA_DIR / "train_table_v3_t11.csv"

THRESHOLD = 11
TRAIN_END = "2023Q2"
VALID_END = "2024Q2"
TARGET = "label_h2_v3_t11"

EXCLUDE_KEYS = [
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


# ==================== 1. 갭필링 패널(임계값11) ====================

def build_filled_panel(sbiz, quarters, q_idx, threshold):
    print(f"\n[1] 갭 필링 패널 재구축 (임계값={threshold})")
    sbiz = sbiz.copy()
    sbiz["idx"] = sbiz["기준분기"].map(q_idx)
    sbiz["is_filled"] = 0
    sbiz["갭길이"] = np.nan

    fill_rows = []
    for store, grp in sbiz.groupby("상가업소번호"):
        grp_sorted = grp.sort_values("idx")
        idxs = grp_sorted["idx"].tolist()
        last_row_by_idx = {row["idx"]: row for _, row in grp_sorted.iterrows()}
        for a, b in zip(idxs, idxs[1:]):
            gap = b - a - 1
            if 0 < gap <= threshold:
                base = last_row_by_idx[a]
                for missing_idx in range(a + 1, b):
                    fill_rows.append({
                        "상가업소번호": store, "기준분기": quarters[missing_idx],
                        "행정동코드": base["행정동코드"], "행정동명": base["행정동명"],
                        "상권업종대분류명": base["상권업종대분류명"], "상권업종중분류명": base["상권업종중분류명"],
                        "상권업종소분류명": base["상권업종소분류명"], "지번주소": base["지번주소"],
                        "경도": base["경도"], "위도": base["위도"], "is_filled": 1, "갭길이": gap,
                    })

    fill_df = pd.DataFrame(fill_rows)
    print(f"  채워진 행 수: {len(fill_df):,} (참고: 임계값8은 44,626행)")
    keep_cols = ["상가업소번호", "기준분기", "행정동코드", "행정동명", "상권업종대분류명", "상권업종중분류명",
                 "상권업종소분류명", "지번주소", "경도", "위도", "is_filled", "갭길이"]
    panel = pd.concat([sbiz[keep_cols], fill_df[keep_cols]], ignore_index=True)
    panel = panel.sort_values(["상가업소번호", "기준분기"], key=lambda s: s if s.name != "기준분기" else s.map(quarter_sort_key))
    panel.to_csv(PANEL_T11_PATH, index=False, encoding="utf-8-sig")
    print(f"  저장 완료: {PANEL_T11_PATH} ({len(panel):,}행)")
    return panel


# ==================== 2. 라벨 ====================

def build_labels(panel, quarters, q_idx):
    print("\n[2] v3-t11 라벨 (마지막 등장 이후 데이터 끝까지 재등장 없음=폐업)")
    panel = panel.copy()
    panel["idx"] = panel["기준분기"].map(q_idx)
    hold_out_idx = {len(quarters) - 2, len(quarters) - 1}
    last_idx_by_store = panel.groupby("상가업소번호")["idx"].max()

    def label_row(row):
        if row["idx"] in hold_out_idx:
            return np.nan
        return 1 if row["idx"] == last_idx_by_store[row["상가업소번호"]] else 0

    panel["is_closed_v3_t11"] = panel.apply(label_row, axis=1)
    panel = panel.drop(columns=["idx"])
    panel.to_csv(LABELS_T11_PATH, index=False, encoding="utf-8-sig")
    labeled = panel.dropna(subset=["is_closed_v3_t11"])
    print(f"  저장 완료: {LABELS_T11_PATH} ({len(panel):,}행, 판정 {len(labeled):,}행)")
    print(f"  총 폐업 건수: {int(labeled['is_closed_v3_t11'].sum()):,}")
    return panel


# ==================== 3. 검증: 스파이크 해소 여부 ====================

def verify_spike_resolution(sbiz, panel8, panel11, quarters):
    print("\n" + "=" * 80)
    print("[검증] 분기별 점포수/개업수 — 원본 vs 임계값8 vs 임계값11")
    print("=" * 80)
    orig_cnt = sbiz.groupby("기준분기")["상가업소번호"].nunique().reindex(quarters)
    p8_cnt = panel8.groupby("기준분기")["상가업소번호"].nunique().reindex(quarters)
    p11_cnt = panel11.groupby("기준분기")["상가업소번호"].nunique().reindex(quarters)
    print("\n점포수:")
    print(pd.DataFrame({"원본": orig_cnt, "임계값8": p8_cnt, "임계값11": p11_cnt}).to_string())

    def open_counts(sets_by_q):
        out = {}
        for i in range(1, len(quarters)):
            q, pq = quarters[i], quarters[i - 1]
            out[q] = len(sets_by_q[q] - sets_by_q[pq])
        return out

    orig_sets = {q: set(sbiz.loc[sbiz["기준분기"] == q, "상가업소번호"]) for q in quarters}
    p8_sets = {q: set(panel8.loc[panel8["기준분기"] == q, "상가업소번호"]) for q in quarters}
    p11_sets = {q: set(panel11.loc[panel11["기준분기"] == q, "상가업소번호"]) for q in quarters}
    print("\n개업수(2024Q4, 2025Q3 스파이크 확인):")
    df_open = pd.DataFrame({"원본": open_counts(orig_sets), "임계값8": open_counts(p8_sets), "임계값11": open_counts(p11_sets)})
    print(df_open.to_string())


def compare_yearly_rates(quarters):
    print("\n" + "=" * 80)
    print("[검증] 연도별 폐업률 — v1/v2/v3(임계값8)/v3-t11")
    print("=" * 80)
    v1 = pd.read_csv(LABELS_V1_PATH, encoding="utf-8-sig", dtype={"기준분기": str})
    v2 = pd.read_csv(LABELS_V2_PATH, encoding="utf-8-sig", dtype={"기준분기": str})
    v3_8 = pd.read_csv(PROCESSED_DATA_DIR / "sbiz_labels_v3.csv", encoding="utf-8-sig", dtype={"기준분기": str})
    v3_11 = pd.read_csv(LABELS_T11_PATH, encoding="utf-8-sig", dtype={"기준분기": str})

    v1["연도"] = v1["기준분기"].str[:4]
    v2l = v2.dropna(subset=["is_closed_v2"]).copy(); v2l["연도"] = v2l["기준분기"].str[:4]
    v3_8l = v3_8.dropna(subset=["is_closed_v3"]).copy(); v3_8l["연도"] = v3_8l["기준분기"].str[:4]
    v3_11l = v3_11.dropna(subset=["is_closed_v3_t11"]).copy(); v3_11l["연도"] = v3_11l["기준분기"].str[:4]

    comp = pd.concat([
        (v1.groupby("연도")["is_closed"].mean() * 100).rename("v1"),
        (v2l.groupby("연도")["is_closed_v2"].mean() * 100).rename("v2"),
        (v3_8l.groupby("연도")["is_closed_v3"].mean() * 100).rename("v3(임계값8)"),
        (v3_11l.groupby("연도")["is_closed_v3_t11"].mean() * 100).rename("v3-t11(임계값11)"),
    ], axis=1)
    print(comp.round(2).to_string())
    print(f"\n총 폐업건수: v1={int(v1['is_closed'].sum()):,} v2={int(v2l['is_closed_v2'].sum()):,} "
          f"v3(8)={int(v3_8l['is_closed_v3'].sum()):,} v3-t11(11)={int(v3_11l['is_closed_v3_t11'].sum()):,}")


# ==================== 4. feature 재계산 ====================

def recompute_market_features(panel, quarters, unit_col, prefix):
    store_sets = (panel.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"]
                  .apply(set).rename("점포집합").reset_index())
    store_sets = store_sets.rename(columns={unit_col: "업종", "기준분기": "B"})
    rows = []
    for (dong, industry), g in store_sets.groupby(["행정동명", "업종"]):
        g = g.set_index("B").reindex(quarters)
        prev_set = None
        for q in quarters:
            cur_set = g.loc[q, "점포집합"]
            cur_set = cur_set if isinstance(cur_set, set) else set()
            store_cnt = len(cur_set)
            if prev_set is None:
                open_cnt, close_cnt = np.nan, np.nan
            else:
                open_cnt, close_cnt = len(cur_set - prev_set), len(prev_set - cur_set)
            rows.append((dong, industry, q, store_cnt, open_cnt, close_cnt))
            prev_set = cur_set
    feat = pd.DataFrame(rows, columns=["행정동명", "업종", "B", f"{prefix}_점포수", f"{prefix}_개업수", f"{prefix}_폐업수"])
    feat[f"{prefix}_개업률"] = feat[f"{prefix}_개업수"] / feat[f"{prefix}_점포수"].replace(0, np.nan)
    feat[f"{prefix}_회전율"] = (feat[f"{prefix}_개업수"] + feat[f"{prefix}_폐업수"]) / feat[f"{prefix}_점포수"].replace(0, np.nan)
    feat[f"{prefix}_순증감률"] = (feat[f"{prefix}_개업수"] - feat[f"{prefix}_폐업수"]) / feat[f"{prefix}_점포수"].replace(0, np.nan)
    feat = feat.sort_values(["행정동명", "업종", "B"], key=lambda s: s if s.name != "B" else s.map(quarter_sort_key))

    def per_group(g):
        g[f"{prefix}_과거폐업률"] = g[f"{prefix}_폐업수"].expanding().sum() / g[f"{prefix}_점포수"].expanding().sum()
        g[f"{prefix}_개업률_MA2"] = g[f"{prefix}_개업률"].rolling(2, min_periods=1).mean()
        g[f"{prefix}_개업률_MA4"] = g[f"{prefix}_개업률"].rolling(4, min_periods=1).mean()
        g[f"{prefix}_순증감률_MA4"] = g[f"{prefix}_순증감률"].rolling(4, min_periods=1).mean()

        def slope(s):
            y = s.dropna().values
            if len(y) < 2:
                return np.nan
            return np.polyfit(np.arange(len(y)), y, 1)[0]

        g[f"{prefix}_순증감률_추세4"] = g[f"{prefix}_순증감률"].rolling(4, min_periods=2).apply(slope, raw=False)
        return g

    feat = feat.set_index(["행정동명", "업종"])
    feat = feat.groupby(level=[0, 1], group_keys=False).apply(per_group)
    feat = feat.reset_index()
    dong_total = feat.groupby(["행정동명", "B"])[f"{prefix}_점포수"].transform("sum")
    feat[f"{prefix}_업종밀도"] = feat[f"{prefix}_점포수"] / dong_total.replace(0, np.nan)
    return feat


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


def compute_true_age(train):
    permits = load_permit_dates()
    train = train.copy()
    train["지번주소_norm"] = train["지번주소"].map(norm_addr)
    train = train.merge(permits, on="지번주소_norm", how="left")

    def abs_q(y, m):
        return y * 4 + (m - 1) // 3

    train["인허가_절대분기"] = train["인허가일자_dt"].apply(lambda d: abs_q(d.year, d.month) if pd.notna(d) else np.nan)
    b_year = train["B"].str[:4].astype(int)
    b_q = train["B"].str[-1].astype(int)
    train["B_절대분기"] = b_year * 4 + (b_q - 1)
    valid = train["인허가_절대분기"].notna() & (train["인허가_절대분기"] <= train["B_절대분기"])
    age = pd.Series(np.nan, index=train.index)
    age.loc[valid] = train.loc[valid, "B_절대분기"] - train.loc[valid, "인허가_절대분기"]
    print(f"  실제 업력 확보 비율: {valid.mean()*100:.1f}%")
    return age


def build_train_table(panel, labels, quarters):
    print("\n[3] feature 재계산 및 train_table_v3_t11 구축")
    skeleton = panel.rename(columns={"기준분기": "B"}).copy()
    lv = labels[["상가업소번호", "기준분기", "is_closed_v3_t11"]].rename(
        columns={"기준분기": "B", "is_closed_v3_t11": TARGET})
    skeleton = skeleton.merge(lv, on=["상가업소번호", "B"], how="left")

    jung = recompute_market_features(panel, quarters, "상권업종중분류명", "중분류")
    dae = recompute_market_features(panel, quarters, "상권업종대분류명", "대분류")
    skeleton = skeleton.merge(jung, left_on=["행정동명", "상권업종중분류명", "B"],
                               right_on=["행정동명", "업종", "B"], how="left").drop(columns=["업종"])
    skeleton = skeleton.merge(dae, left_on=["행정동명", "상권업종대분류명", "B"],
                               right_on=["행정동명", "업종", "B"], how="left").drop(columns=["업종"])

    print("  업력_신규 계산 중...")
    skeleton["업력_신규"] = compute_true_age(skeleton)

    print(f"  [로드] {TRAIN_V3_PATH} (나머지 feature 승계)")
    v3_8 = pd.read_csv(TRAIN_V3_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "B": str, "상가업소번호": str})

    store_cols = ["상가업소번호", "B", "면적", "종사자수",
                  "대규모점포_최근4분기신규", "대규모점포_최근접거리km"]
    store_ref = v3_8[store_cols].drop_duplicates(subset=["상가업소번호", "B"])
    skeleton = skeleton.merge(store_ref, on=["상가업소번호", "B"], how="left")

    dong_cols = [c for c in v3_8.columns if c not in (
        "상가업소번호", "B", "행정동코드", "행정동명", "지번주소", "경도", "위도",
        "상권업종중분류명", "상권업종대분류명", "상권업종소분류명", "label_h1", "label_h2_v3", "label_h1_v3",
        "is_filled", "갭길이", "업력_분기수", "업력_분기수_보정", "면적", "종사자수",
        "대규모점포_행정동내개수", "대규모점포_최근4분기신규", "대규모점포_최근접거리km",
        "카드매출_공통업종_후보", "카드매출_행정동내구성비", "카드매출_업종내행정동share",
        "카드매출_구성비_변화", "카드매출_구성비_추세4",
        *[c for c in v3_8.columns if c.startswith("중분류_") or c.startswith("대분류_")],
        "분기_Q",
    )]
    dong_ref = v3_8[["행정동명", "B"] + dong_cols].drop_duplicates(subset=["행정동명", "B"])
    skeleton = skeleton.merge(dong_ref, on=["행정동명", "B"], how="left")
    skeleton["분기_Q"] = skeleton["B"].str[-2:]

    skeleton.to_csv(TRAIN_T11_PATH, index=False, encoding="utf-8-sig")
    print(f"  저장 완료: {TRAIN_T11_PATH} ({len(skeleton):,}행, {len(skeleton.columns)}컬럼)")
    return skeleton


# ==================== 5. 모델 학습/평가 ====================

def get_feature_cols(df):
    exclude = set(EXCLUDE_KEYS) | {TARGET}
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
    return {"n_cells": len(sub), "spearman": round(sp, 3), "lift": round(lift, 3)}


def run_cell_regression(unit_col, unit_name, sbiz, labels_t11, quarters, df_ref):
    q_idx = {q: i for i, q in enumerate(quarters)}
    next2 = {quarters[i]: quarters[i + 2] for i in range(len(quarters) - 2)}
    labeled_stores = labels_t11.dropna(subset=["is_closed_v3_t11"])
    store_cnt = sbiz.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"].nunique().rename("점포수").reset_index()
    closure = labeled_stores.groupby(["행정동명", unit_col, "기준분기"])["is_closed_v3_t11"].mean()

    def get_label(row):
        t2 = next2.get(row["기준분기"])
        if t2 is None:
            return np.nan
        return closure.get((row["행정동명"], row[unit_col], t2), np.nan)

    store_cnt["target"] = store_cnt.apply(get_label, axis=1)
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
        print(f"  [{unit_name}] 데이터 부족으로 스킵")
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
          f"스피어만={sp:.3f}, 리프트={lift:.2f}x")
    return {"spearman": round(sp, 3), "lift": round(lift, 3)}


def main():
    print(f"[로드] {ALL_PATH}")
    sbiz = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str, "상권업종대분류명": str,
        "상권업종중분류명": str, "상권업종소분류명": str, "지번주소": str, "기준분기": str})
    quarters = sorted(sbiz["기준분기"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}

    panel11 = build_filled_panel(sbiz, quarters, q_idx, THRESHOLD)
    labels11 = build_labels(panel11, quarters, q_idx)

    print(f"\n[로드] 임계값8 패널(비교용)")
    panel8 = pd.read_csv(PROCESSED_DATA_DIR / "sbiz_panel_filled.csv", encoding="utf-8-sig",
                          dtype={"상가업소번호": str, "기준분기": str})
    verify_spike_resolution(sbiz, panel8, panel11, quarters)
    compare_yearly_rates(quarters)

    df = build_train_table(panel11, labels11, quarters)

    feats = get_feature_cols(df)
    cat_cols = [c for c in CATEGORICAL_COLS if c in feats]
    print(f"\n모델 입력 feature 수: {len(feats)}개")

    train, valid, test, last_q = time_split(df, TARGET)
    print(f"\n라벨 가용 마지막 분기: {last_q}")
    print(f"Train {train['B'].min()}~{train['B'].max()}({len(train):,}) / "
          f"Valid {valid['B'].min()}~{valid['B'].max()}({len(valid):,}) / "
          f"Test {test['B'].min()}~{test['B'].max()}({len(test):,})")
    print(f"Test 양성비율: {test[TARGET].mean()*100:.2f}% (정상범위 4~7% 목표)")

    X_train, y_train = prepare_xy(train, feats, TARGET, cat_cols)
    X_valid, y_valid = prepare_xy(valid, feats, TARGET, cat_cols)
    X_test, y_test = prepare_xy(test, feats, TARGET, cat_cols)

    model = lgb.LGBMClassifier(**LGB_PARAMS)
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], eval_metric="average_precision",
              categorical_feature=cat_cols, callbacks=[lgb.early_stopping(100, verbose=False)])
    print(f"\nbest_iteration={model.best_iteration_} / 총 split={int(model.feature_importances_.sum())}")

    pred_valid = model.predict_proba(X_valid)[:, 1]
    pred_test = model.predict_proba(X_test)[:, 1]
    score_valid, score_test = eval_scores(y_valid, pred_valid), eval_scores(y_test, pred_test)
    print(f"[모델] Valid: {score_valid}")
    print(f"[모델] Test:  {score_test}")

    age_median = train["업력_신규"].median()
    b1 = -test["업력_신규"].fillna(age_median)
    b0 = (test["중분류_폐업수"] / test["중분류_점포수"].replace(0, np.nan)).fillna(0)
    score_b1, score_b0 = eval_scores(y_test, b1), eval_scores(y_test, b0)
    print(f"[B0_관성] Test: {score_b0}")
    print(f"[B1_업력] Test: {score_b1}")

    ens = (rankdata(pred_test) + rankdata(b1)) / 2
    score_ens = eval_scores(y_test, ens)
    print(f"[앙상블] Test: {score_ens}")

    cell_jung_agg = cell_eval(test, y_test.values, pred_test, ["행정동명", "상권업종중분류명"], 30)
    cell_dae_agg = cell_eval(test, y_test.values, pred_test, ["행정동명", "상권업종대분류명"], 30)
    print(f"\n[셀평가 n>=30, 점포모델집계] 중분류: {cell_jung_agg}")
    print(f"[셀평가 n>=30, 점포모델집계] 대분류: {cell_dae_agg}")

    print("\n[셀 회귀]")
    r_dae = run_cell_regression("상권업종대분류명", "대분류", sbiz, labels11, quarters, df)
    r_jung = run_cell_regression("상권업종중분류명", "중분류", sbiz, labels11, quarters, df)

    print("\n" + "=" * 80)
    print("[최종 비교] 임계값8 vs 임계값11")
    print("=" * 80)
    print(f"{'항목':<25}{'임계값8(3차)':<20}{'임계값11(이번)':<20}")
    print(f"{'Test 양성비율':<25}{'6.73%':<20}{test[TARGET].mean()*100:.2f}%")
    print(f"{'모델 Test PR-AUC':<25}{'0.0734':<20}{score_test['PR-AUC']}")
    print(f"{'모델 Test ROC-AUC':<25}{'0.5384':<20}{score_test['ROC-AUC']}")
    print(f"{'B1 Test PR-AUC':<25}{'0.0706':<20}{score_b1['PR-AUC']}")
    print(f"{'앙상블 Test PR-AUC':<25}{'0.0751':<20}{score_ens['PR-AUC']}")
    print(f"{'셀회귀(대분류) 스피어만':<25}{'0.378':<20}{r_dae['spearman'] if r_dae else None}")
    print(f"{'셀회귀(대분류) 리프트':<25}{'1.22':<20}{r_dae['lift'] if r_dae else None}")
    print(f"{'셀회귀(중분류) 스피어만':<25}{'0.300':<20}{r_jung['spearman'] if r_jung else None}")
    print(f"{'셀회귀(중분류) 리프트':<25}{'1.38':<20}{r_jung['lift'] if r_jung else None}")

    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        return o

    results = {"score_valid": score_valid, "score_test": score_test, "b0": score_b0, "b1": score_b1,
               "ensemble": score_ens, "cell_store_agg": {"중분류": cell_jung_agg, "대분류": cell_dae_agg},
               "cell_regression": {"대분류": r_dae, "중분류": r_jung}, "best_iteration": model.best_iteration_,
               "test_pos_rate": float(test[TARGET].mean())}
    with open(PROCESSED_DATA_DIR / "model_v3_t11_results.json", "w", encoding="utf-8") as f:
        json.dump(clean(results), f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {PROCESSED_DATA_DIR / 'model_v3_t11_results.json'}")


if __name__ == "__main__":
    main()
