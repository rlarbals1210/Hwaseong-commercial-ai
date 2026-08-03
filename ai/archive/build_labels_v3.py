"""
폐업 라벨 v3: 2023Q1 스냅샷 결함(재등장률 72.1%, 인허가상 영업중 46.8% 확인됨)을
갭 필링으로 복원 — 앞뒤로 존재가 확인된 짧은 부재 구간을 "영업 중"으로 메운 뒤
라벨(v3)과 상권 feature를 다시 계산한다.

원칙: v1/v2 라벨 파일, train_table_v2.csv는 전부 보존. 이 스크립트는 전부 새 파일(v3)로 저장.
매칭은 상가업소번호 기준만 사용(상호명+주소 기준은 오매칭 위험 있어 채우지 않고 보고만 함).

사용법:
    python ai/build_labels_v3.py
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
LABELS_V1_PATH = PROCESSED_DATA_DIR / "sbiz_labels.csv"
LABELS_V2_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v2.csv"
TRAIN_V2_PATH = PROCESSED_DATA_DIR / "train_table_v2.csv"

PANEL_FILLED_PATH = PROCESSED_DATA_DIR / "sbiz_panel_filled.csv"
LABELS_V3_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v3.csv"
TRAIN_V3_PATH = PROCESSED_DATA_DIR / "train_table_v3.csv"

CHOSEN_THRESHOLD = 8  # 0단계 갭분포 분석 근거로 기본값 4 대신 채택 (본문에서 근거 설명)
SENSITIVITY_THRESHOLDS = [2, 4, 8]

SBIZ_TO_CARD = {
    "한식": "음식점", "중식": "음식점", "일식": "음식점", "서양식": "음식점", "동남아시아": "음식점",
    "기타 간이": "음식점", "구내식당·뷔페": "음식점", "주점": "주점",
    "이용·미용": "미용", "일반 교육": "학원·교육", "기타 교육": "학원·교육",
    "의원": "의료", "병원": "의료", "기타 보건": "의료",
    "일반 숙박": "숙박", "기타 숙박": "숙박", "연료 소매": "연료판매",
    "자동차 수리·세차": "자동차", "모터사이클 수리": "자동차",
    "세탁": "수리서비스", "가전제품 수리": "수리서비스", "기타 가정용품 수리": "수리서비스",
    "컴퓨터 수리": "수리서비스", "통신장비 수리": "수리서비스",
    "식료품 소매": "식료품소매", "섬유·의복·신발 소매": "의류·잡화",
    "자동차 부품 소매": "자동차", "모터사이클 소매": "자동차", "종합 소매": "종합소매",
    "유원지·오락": "여가·스포츠", "스포츠 서비스": "여가·스포츠",
}


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def load_sbiz():
    df = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str,
        "상권업종대분류명": str, "상권업종중분류명": str, "상권업종소분류명": str,
        "지번주소": str, "기준분기": str,
    })
    return df


# ==================== 0단계: 갭 길이 분포 ====================

def gap_distribution(sbiz: pd.DataFrame, quarters, q_idx):
    print("\n" + "=" * 80)
    print("[0단계] 갭 길이 분포 (2023Q1 코호트 vs 타분기)")
    print("=" * 80)
    sbiz = sbiz.copy()
    sbiz["idx"] = sbiz["기준분기"].map(q_idx)

    records = []
    for store, idxs in sbiz.groupby("상가업소번호")["idx"]:
        idxs = sorted(idxs.tolist())
        for a, b in zip(idxs, idxs[1:]):
            gap = b - a - 1
            if gap > 0:
                start_missing_q = quarters[a + 1]
                cohort = "2023Q1" if start_missing_q == "2023Q1" else "기타"
                records.append((store, a, b, gap, cohort))

    gaps_df = pd.DataFrame(records, columns=["상가업소번호", "직전idx", "재등장idx", "gap", "cohort"])
    print(f"\n전체 갭(재등장 확인된) 이벤트 수: {len(gaps_df):,}")

    for cohort in ["2023Q1", "기타"]:
        sub = gaps_df[gaps_df["cohort"] == cohort]["gap"]
        print(f"\n[{cohort}] n={len(sub):,}, 평균 {sub.mean():.2f}, 중앙값 {sub.median():.1f}, 최대 {sub.max()}")
        print(sub.value_counts().sort_index().to_string())

    print(f"\n채택 임계값: {CHOSEN_THRESHOLD}분기 (근거는 보고 참고 — 기본 4분기 대신 채택)")
    return gaps_df


# ==================== 1단계: 존속 패널 복원 ====================

def build_filled_panel(sbiz: pd.DataFrame, quarters, q_idx, threshold: int, save: bool = True) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print(f"[1단계] 존속 패널 복원 (임계값={threshold}분기, 상가업소번호 기준만)")
    print("=" * 80)

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
                        "경도": base["경도"], "위도": base["위도"],
                        "is_filled": 1, "갭길이": gap,
                    })

    fill_df = pd.DataFrame(fill_rows)
    print(f"채워진 (점포x분기) 행 수: {len(fill_df):,}")
    if len(fill_df):
        print(f"갭 필링 대상 고유 점포 수: {fill_df['상가업소번호'].nunique():,} / 전체 점포 {sbiz['상가업소번호'].nunique():,}"
              f" ({fill_df['상가업소번호'].nunique() / sbiz['상가업소번호'].nunique() * 100:.1f}%)")
        by_q = fill_df["기준분기"].value_counts().sort_index(key=lambda s: s.map(quarter_sort_key))
        print("\n채워진 행이 몰린 분기(상위 10개):")
        print(by_q.sort_values(ascending=False).head(10).to_string())
        q1_2023_share = (fill_df["기준분기"] == "2023Q1").sum() / len(fill_df) * 100
        print(f"\n2023Q1에 채워진 비율: {q1_2023_share:.1f}% (나머지는 다른 분기)")

    keep_cols = ["상가업소번호", "기준분기", "행정동코드", "행정동명", "상권업종대분류명", "상권업종중분류명",
                 "상권업종소분류명", "지번주소", "경도", "위도", "is_filled", "갭길이"]
    panel = pd.concat([sbiz[keep_cols], fill_df[keep_cols]], ignore_index=True)
    panel = panel.sort_values(["상가업소번호", "기준분기"], key=lambda s: s if s.name != "기준분기" else s.map(quarter_sort_key))

    if save:
        PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        panel.to_csv(PANEL_FILLED_PATH, index=False, encoding="utf-8-sig")
        print(f"\n저장 완료: {PANEL_FILLED_PATH} ({len(panel):,}행, 원본 {len(sbiz):,} + 채움 {len(fill_df):,})")
    return panel


# ==================== 2단계: v3 라벨 ====================

def build_labels_v3(panel: pd.DataFrame, quarters, q_idx, save: bool = True) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print("[2단계] v3 라벨 (마지막 등장 이후 데이터 끝까지 재등장 없음 = 폐업)")
    print("=" * 80)

    panel = panel.copy()
    panel["idx"] = panel["기준분기"].map(q_idx)
    hold_out_idx = {len(quarters) - 2, len(quarters) - 1}
    hold_out_q = {quarters[i] for i in hold_out_idx}
    print(f"판정 보류 분기: {sorted(hold_out_q, key=quarter_sort_key)}")

    last_idx_by_store = panel.groupby("상가업소번호")["idx"].max()

    def label_row(row):
        if row["idx"] in hold_out_idx:
            return np.nan
        return 1 if row["idx"] == last_idx_by_store[row["상가업소번호"]] else 0

    panel["is_closed_v3"] = panel.apply(label_row, axis=1)
    panel = panel.drop(columns=["idx"])

    labeled = panel.dropna(subset=["is_closed_v3"])
    if save:
        panel.to_csv(LABELS_V3_PATH, index=False, encoding="utf-8-sig")
        print(f"저장 완료: {LABELS_V3_PATH} ({len(panel):,}행, 판정 {len(labeled):,}행)")
    print(f"v3 총 폐업 건수: {int(labeled['is_closed_v3'].sum()):,}")
    return panel


# ==================== 3단계: feature 재계산 ====================

def recompute_market_features(panel: pd.DataFrame, quarters, unit_col: str, prefix: str) -> pd.DataFrame:
    store_sets = (
        panel.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"]
        .apply(set).rename("점포집합").reset_index()
    )
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
                open_cnt = len(cur_set - prev_set)
                close_cnt = len(prev_set - cur_set)
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
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]

        g[f"{prefix}_순증감률_추세4"] = g[f"{prefix}_순증감률"].rolling(4, min_periods=2).apply(slope, raw=False)
        return g

    feat = feat.set_index(["행정동명", "업종"])
    feat = feat.groupby(level=[0, 1], group_keys=False).apply(per_group)
    feat = feat.reset_index()

    dong_total = feat.groupby(["행정동명", "B"])[f"{prefix}_점포수"].transform("sum")
    feat[f"{prefix}_업종밀도"] = feat[f"{prefix}_점포수"] / dong_total.replace(0, np.nan)
    return feat


def build_train_v3(panel: pd.DataFrame, labels_v3: pd.DataFrame, quarters):
    print("\n" + "=" * 80)
    print("[3단계] feature 재계산 (갭필링 패널 기준, 나머지는 v2 승계)")
    print("=" * 80)

    skeleton = panel.rename(columns={"기준분기": "B"}).copy()
    lv3 = labels_v3[["상가업소번호", "기준분기", "is_closed_v3"]].rename(columns={"기준분기": "B", "is_closed_v3": "label_h2_v3"})
    skeleton = skeleton.merge(lv3, on=["상가업소번호", "B"], how="left")

    jung_feat = recompute_market_features(panel, quarters, "상권업종중분류명", "중분류")
    dae_feat = recompute_market_features(panel, quarters, "상권업종대분류명", "대분류")
    print(f"  중분류 feature 재계산: {len(jung_feat):,}행 / 대분류: {len(dae_feat):,}행")

    skeleton = skeleton.merge(jung_feat, left_on=["행정동명", "상권업종중분류명", "B"],
                               right_on=["행정동명", "업종", "B"], how="left").drop(columns=["업종"])
    skeleton = skeleton.merge(dae_feat, left_on=["행정동명", "상권업종대분류명", "B"],
                               right_on=["행정동명", "업종", "B"], how="left").drop(columns=["업종"])

    print(f"\n[로드] {TRAIN_V2_PATH} (나머지 feature 승계용)")
    v2 = pd.read_csv(TRAIN_V2_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "B": str, "상가업소번호": str})

    store_level_cols = ["상가업소번호", "B", "업력_분기수", "업력_분기수_보정", "면적", "종사자수",
                         "대규모점포_행정동내개수", "대규모점포_최근4분기신규", "대규모점포_최근접거리km"]
    store_ref = v2[store_level_cols].drop_duplicates(subset=["상가업소번호", "B"])
    skeleton = skeleton.merge(store_ref, on=["상가업소번호", "B"], how="left")

    dong_level_cols = [c for c in v2.columns if c not in (
        "상가업소번호", "B", "행정동코드", "행정동명", "지번주소", "경도", "위도",
        "상권업종중분류명", "상권업종대분류명", "label_h1", "label_h2",
        *store_level_cols[2:], "카드매출_공통업종_후보",
        "카드매출_행정동내구성비", "카드매출_업종내행정동share", "카드매출_구성비_변화", "카드매출_구성비_추세4",
        "중분류_점포수", "중분류_개업수", "중분류_폐업수", "중분류_개업률", "중분류_회전율", "중분류_순증감률",
        "중분류_과거폐업률", "중분류_개업률_MA2", "중분류_개업률_MA4", "중분류_순증감률_MA4", "중분류_순증감률_추세4", "중분류_업종밀도",
        "대분류_점포수", "대분류_개업수", "대분류_폐업수", "대분류_개업률", "대분류_회전율", "대분류_순증감률",
        "대분류_과거폐업률", "대분류_개업률_MA2", "대분류_개업률_MA4", "대분류_순증감률_MA4", "대분류_순증감률_추세4", "대분류_업종밀도",
        "분기_Q",
    )]
    dong_ref = v2[["행정동명", "B"] + dong_level_cols].drop_duplicates(subset=["행정동명", "B"])
    skeleton = skeleton.merge(dong_ref, on=["행정동명", "B"], how="left")

    skeleton["카드매출_공통업종_후보"] = skeleton["상권업종중분류명"].map(SBIZ_TO_CARD)
    card_cols = ["행정동명", "공통업종", "B", "카드매출_행정동내구성비", "카드매출_업종내행정동share",
                 "카드매출_구성비_변화", "카드매출_구성비_추세4"]
    card_ref = v2.rename(columns={"카드매출_공통업종_후보": "공통업종"})
    card_ref = card_ref[[c for c in card_cols if c in card_ref.columns]].drop_duplicates(subset=["행정동명", "공통업종", "B"])
    skeleton = skeleton.merge(
        card_ref, left_on=["행정동명", "카드매출_공통업종_후보", "B"],
        right_on=["행정동명", "공통업종", "B"], how="left"
    ).drop(columns=["공통업종"])

    skeleton["분기_Q"] = skeleton["B"].str[-2:]

    skeleton.to_csv(TRAIN_V3_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {TRAIN_V3_PATH} ({len(skeleton):,}행, {len(skeleton.columns)}컬럼)")
    return skeleton


# ==================== 검증 ====================

def compare_v1_v2_v3(quarters):
    print("\n" + "=" * 80)
    print("[검증 1] v1 vs v2 vs v3 총 폐업 건수 및 연도별 폐업률")
    print("=" * 80)

    v1 = pd.read_csv(LABELS_V1_PATH, encoding="utf-8-sig", dtype={"기준분기": str})
    v2 = pd.read_csv(LABELS_V2_PATH, encoding="utf-8-sig", dtype={"기준분기": str})
    v3 = pd.read_csv(LABELS_V3_PATH, encoding="utf-8-sig", dtype={"기준분기": str})

    v1["연도"] = v1["기준분기"].str[:4]
    v2_l = v2.dropna(subset=["is_closed_v2"]).copy()
    v2_l["연도"] = v2_l["기준분기"].str[:4]
    v3_l = v3.dropna(subset=["is_closed_v3"]).copy()
    v3_l["연도"] = v3_l["기준분기"].str[:4]

    print(f"\n총 폐업 건수: v1={int(v1['is_closed'].sum()):,} / v2={int(v2_l['is_closed_v2'].sum()):,} / "
          f"v3={int(v3_l['is_closed_v3'].sum()):,}")

    y1 = (v1.groupby("연도")["is_closed"].mean() * 100).rename("v1")
    y2 = (v2_l.groupby("연도")["is_closed_v2"].mean() * 100).rename("v2")
    y3 = (v3_l.groupby("연도")["is_closed_v3"].mean() * 100).rename("v3")
    comp = pd.concat([y1, y2, y3], axis=1)
    print("\n연도별 폐업률(%):")
    print(comp.round(2).to_string())

    return comp


def compare_store_and_open_counts(sbiz: pd.DataFrame, panel: pd.DataFrame, quarters):
    print("\n" + "=" * 80)
    print("[검증 2·3] 분기별 점포수/개업수 추이 (원본 vs 필링후)")
    print("=" * 80)

    orig_cnt = sbiz.groupby("기준분기")["상가업소번호"].nunique().reindex(quarters)
    filled_cnt = panel.groupby("기준분기")["상가업소번호"].nunique().reindex(quarters)

    print("\n점포수(원본 vs 필링후):")
    print(pd.DataFrame({"원본": orig_cnt, "필링후": filled_cnt}).to_string())

    orig_sets = {q: set(sbiz.loc[sbiz["기준분기"] == q, "상가업소번호"]) for q in quarters}
    filled_sets = {q: set(panel.loc[panel["기준분기"] == q, "상가업소번호"]) for q in quarters}

    orig_open, filled_open = {}, {}
    for i in range(1, len(quarters)):
        q, pq = quarters[i], quarters[i - 1]
        orig_open[q] = len(orig_sets[q] - orig_sets[pq])
        filled_open[q] = len(filled_sets[q] - filled_sets[pq])

    print("\n개업수(원본 vs 필링후, 재등장을 개업으로 세지 않는지 확인):")
    print(pd.DataFrame({"원본_개업수": pd.Series(orig_open), "필링후_개업수": pd.Series(filled_open)}).to_string())


def sensitivity_analysis(sbiz: pd.DataFrame, quarters, q_idx):
    print("\n" + "=" * 80)
    print("[검증 5] 민감도 분석 — 임계값별 총 폐업 건수 및 연도별 폐업률")
    print("=" * 80)

    results = {}
    for th in SENSITIVITY_THRESHOLDS:
        panel = build_filled_panel(sbiz, quarters, q_idx, th, save=False)
        labels = build_labels_v3(panel, quarters, q_idx, save=False)
        labeled = labels.dropna(subset=["is_closed_v3"]).copy()
        labeled["연도"] = labeled["기준분기"].str[:4]
        total_closed = int(labeled["is_closed_v3"].sum())
        yearly = (labeled.groupby("연도")["is_closed_v3"].mean() * 100)
        results[th] = {"총폐업건수": total_closed, **yearly.to_dict()}

    result_df = pd.DataFrame(results).T
    print("\n임계값별 비교:")
    print(result_df.round(2).to_string())
    return result_df


def main():
    sbiz = load_sbiz()
    quarters = sorted(sbiz["기준분기"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}

    gap_distribution(sbiz, quarters, q_idx)

    panel = build_filled_panel(sbiz, quarters, q_idx, CHOSEN_THRESHOLD)
    labels_v3 = build_labels_v3(panel, quarters, q_idx)
    build_train_v3(panel, labels_v3, quarters)

    compare_v1_v2_v3(quarters)
    compare_store_and_open_counts(sbiz, panel, quarters)
    sensitivity_analysis(sbiz, quarters, q_idx)


if __name__ == "__main__":
    main()
