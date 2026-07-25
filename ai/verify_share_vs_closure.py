"""
카드매출 share 변화가 실제 폐업률과 관계 있는지 검증 (feature 유효성 1차 확인).
동탄1동의 share 하락이 '건강한 희석'인지 '실제 쇠퇴'인지 판별.

입력:
    data/processed/dong_share_shift_ranked.csv (identify_share_shift_dongs.py 산출물)
    data/processed/sbiz_labels_v2.csv (폐업 라벨 v2)
    data/processed/sbiz_hwaseong_all.csv (분기별 점포)
    Hwaseong-commercial-ai-main-dataset/화성시_인구동향_시계열.csv
    (읍면동 단위 인구가 이미 이 파일 안에 있음 — 별도 KOSIS 파일 불필요, 확인함)

사용법:
    python ai/verify_share_vs_closure.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

SHARE_PATH = PROCESSED_DATA_DIR / "dong_share_shift_ranked.csv"
LABELS_V2_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v2.csv"
ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
POP_PATH = next(PROJECT_ROOT.glob("**/화성시_인구동향_시계열.csv"))

DONGTAN1 = "동탄1동"


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def load_population_by_dong():
    # 주의: 2026.02 행정구역 개편(구 신설)으로 일부 동은 같은 이름의 행이 두 줄
    # 존재함(옛 경계분/새 경계분, 기간이 안 겹침 — 예: 동탄1동은 ~2025.12행과
    # 2026.03~행이 별도). 우리가 보는 2021.12/2024.03 시점엔 둘 중 값이 채워진
    # 쪽만 유효하므로, 이름별로 두 컬럼 다 값이 있는 행을 우선 채택.
    pop = pd.read_csv(POP_PATH, encoding="cp949", dtype=str)
    row = pop[(pop["5세별"] == "계") & (pop["항목"] == "총인구수[명]")].copy()
    for col in ["2021.12 월", "2024.03 월"]:
        row[col] = pd.to_numeric(row[col].str.replace(",", ""), errors="coerce")
    row = row.dropna(subset=["2021.12 월", "2024.03 월"])
    row = row.drop_duplicates(subset="행정구역(동읍면)별", keep="first")
    row = row.set_index("행정구역(동읍면)별")[["2021.12 월", "2024.03 월"]]
    row["인구증감률"] = (row["2024.03 월"] - row["2021.12 월"]) / row["2021.12 월"] * 100
    return row


def load_population_series(dong: str):
    pop = pd.read_csv(POP_PATH, encoding="cp949", dtype=str)
    rows = pop[(pop["행정구역(동읍면)별"] == dong) & (pop["5세별"] == "계") & (pop["항목"] == "총인구수[명]")]
    if rows.empty:
        return None
    cols = [c for c in pop.columns if "월" in c]
    numeric = rows[cols].apply(lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce"))
    # 옛/새 경계 행이 나뉘어 있어도 시점별로 값 있는 쪽을 골라 하나의 연속 시계열로 합침
    return numeric.bfill().iloc[0]


def main():
    print("입력 로드 중...")
    share_df = pd.read_csv(SHARE_PATH, encoding="utf-8-sig", dtype={"행정동코드": str})
    labels = pd.read_csv(LABELS_V2_PATH, encoding="utf-8-sig", dtype={"상가업소번호": str})
    all_df = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype={"상가업소번호": str})

    # ---------- 1. 행정동별 폐업률 추이 (2021 vs 2024) ----------
    print("\n[1] 행정동별 폐업률 추이 (2021 vs 2024)")
    labels_labeled = labels.dropna(subset=["is_closed_v2"]).copy()
    labels_labeled["연도"] = labels_labeled["기준분기"].str[:4]
    closure_2021 = labels_labeled[labels_labeled["연도"] == "2021"].groupby("행정동명")["is_closed_v2"].mean() * 100
    closure_2024 = labels_labeled[labels_labeled["연도"] == "2024"].groupby("행정동명")["is_closed_v2"].mean() * 100
    closure_change = (closure_2024 - closure_2021).rename("폐업률변화(%p)")

    # ---------- 2. 행정동별 점포수 추이 (2021Q4 vs 2024Q1) ----------
    print("[2] 행정동별 점포수 추이 (2021Q4 vs 2024Q1)")
    store_2021q4 = all_df[all_df["기준분기"] == "2021Q4"].groupby("행정동명")["상가업소번호"].nunique()
    store_2024q1 = all_df[all_df["기준분기"] == "2024Q1"].groupby("행정동명")["상가업소번호"].nunique()
    store_change_pct = ((store_2024q1 - store_2021q4) / store_2021q4 * 100).rename("점포수증감률(%)")

    # ---------- 3. 행정동별 인구 추이 ----------
    print("[3] 행정동별 인구 추이 (2021.12 vs 2024.03)")
    pop_by_dong = load_population_by_dong()

    # ---------- 결합 ----------
    merged = share_df.set_index("행정동명")[["평균share변화(pp)"]].copy()
    merged = merged.join(closure_change, how="left")
    merged = merged.join(store_change_pct, how="left")
    merged = merged.join(pop_by_dong["인구증감률"], how="left")
    merged = merged.dropna()

    print("\n" + "=" * 90)
    print("행정동별 4개 지표 결합 테이블")
    print("=" * 90)
    print(merged.sort_values("평균share변화(pp)", ascending=False).to_string())

    # ---------- 4. 상관관계 ----------
    print("\n" + "=" * 90)
    print("[4] share변화 vs (폐업률변화 / 점포수증감률 / 인구증감률) 상관관계")
    print("=" * 90)
    for col in ["폐업률변화(%p)", "점포수증감률(%)", "인구증감률"]:
        pearson = merged["평균share변화(pp)"].corr(merged[col], method="pearson")
        spearman = merged["평균share변화(pp)"].corr(merged[col], method="spearman")
        print(f"  share변화 vs {col}: 피어슨={pearson:.3f}, 스피어만={spearman:.3f} (n={len(merged)})")

    # ---------- 동탄1동 집중분석 ----------
    print("\n" + "=" * 90)
    print(f"[동탄1동 집중분석]")
    print("=" * 90)

    dt1_stores = all_df[all_df["행정동명"] == DONGTAN1].groupby("기준분기")["상가업소번호"].nunique()
    dt1_stores = dt1_stores.reindex(sorted(dt1_stores.index, key=quarter_sort_key))
    print("\n분기별 점포수:")
    print(dt1_stores.to_string())

    dt1_labels = labels[labels["행정동명"] == DONGTAN1].dropna(subset=["is_closed_v2"])
    dt1_closure = dt1_labels.groupby("기준분기")["is_closed_v2"].mean() * 100
    dt1_closure = dt1_closure.reindex(sorted(dt1_closure.index, key=quarter_sort_key))
    print("\n분기별 폐업률(%):")
    print(dt1_closure.round(2).to_string())

    dt1_pop = load_population_series(DONGTAN1)
    print("\n인구 추이 (분기말 근접 시점만):")
    if dt1_pop is not None:
        quarter_end_cols = [c for c in dt1_pop.index if c.split(".")[1].strip(" 월") in ("03", "06", "09", "12")]
        print(dt1_pop[quarter_end_cols].to_string())
    else:
        print("  인구 데이터 없음")

    store_change_dt1 = store_change_pct.get(DONGTAN1, float("nan"))
    closure_change_dt1 = closure_change.get(DONGTAN1, float("nan"))
    pop_change_dt1 = pop_by_dong["인구증감률"].get(DONGTAN1, float("nan"))
    share_change_dt1 = share_df.set_index("행정동명")["평균share변화(pp)"].get(DONGTAN1, float("nan"))

    print(f"\n요약: share변화 {share_change_dt1:+.2f}%p, 점포수증감 {store_change_dt1:+.1f}%, "
          f"폐업률변화 {closure_change_dt1:+.2f}%p, 인구증감 {pop_change_dt1:+.1f}%")

    if store_change_dt1 >= -5 and closure_change_dt1 <= 1:
        verdict = "건강한 희석 (점포수 유지/증가, 폐업률 안정)"
    else:
        verdict = "실제 쇠퇴 신호 있음 (점포수 감소 또는 폐업률 상승)"
    print(f"판정: {verdict}")

    # ---------- 5. 폐업률 상승 top5 vs share 하락 top group 비교 ----------
    print("\n" + "=" * 90)
    print("[5] 폐업률이 실제로 가장 많이 오른 행정동 top5")
    print("=" * 90)
    top5_closure_up = closure_change.sort_values(ascending=False).head(5)
    print(top5_closure_up.round(2).to_string())

    share_down_group = set(share_df.sort_values("평균share변화(pp)").head(5)["행정동명"])
    overlap = share_down_group & set(top5_closure_up.index)
    print(f"\nshare 하락 top5: {share_down_group}")
    print(f"폐업률 상승 top5: {set(top5_closure_up.index)}")
    print(f"겹치는 행정동: {overlap} ({len(overlap)}개 / 5개 중)")

    out_path = PROCESSED_DATA_DIR / "share_vs_closure_check.csv"
    merged.to_csv(out_path, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
