"""
소진공 2022->2023 점포수 급감(-16.9%)이 실제 폐업 급증인지 소진공 자체 수록기준
변경 때문인지, 업종 범위가 가까운 통계청 도소매+숙박음식 사업체수로 외부 검증한다.

사용법:
    python ai/verify_2022_2023_drop_external.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
DATASET_DIR = PROJECT_ROOT / "Hwaseong-commercial-ai-main-dataset"

SBIZ_ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
BIZ_PATH = DATASET_DIR / "kosis_data" / "산업별_읍면동별_사업체수_및_종사자수_20260724063757.csv"

SBIZ_DOSOMAE_SUKBAK = {"소매", "음식", "숙박"}  # 통계청 도소매+숙박음식과 업종범위가 가장 가까운 소진공 대분류


def to_num(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s in ("-", ""):
        return 0.0
    if s.upper() == "X":
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_biz_dosomae_sukbak() -> pd.DataFrame:
    raw = pd.read_csv(BIZ_PATH, encoding="cp949", header=None)
    row_year, row_ind, row_meas, row_sub = raw.iloc[0], raw.iloc[1], raw.iloc[2], raw.iloc[3]
    data = raw.iloc[4:].reset_index(drop=True)
    dong_col = data[0]

    wanted = {"도매 및 소매업": "도소매_사업체수", "숙박 및 음식점업": "숙박음식_사업체수"}
    rows = []
    for j in range(1, raw.shape[1]):
        ind = row_ind[j]
        if ind not in wanted:
            continue
        if row_meas[j] != "사업체수 (개)" or row_sub[j] != "소계":
            continue
        year = row_year[j]
        colname = wanted[ind]
        for i, dong in enumerate(dong_col):
            if dong == "합계":
                continue
            rows.append((dong, year, colname, to_num(data.iloc[i, j])))

    long_df = pd.DataFrame(rows, columns=["행정동명", "연도", "key", "value"])
    wide = long_df.pivot_table(index=["행정동명", "연도"], columns="key", values="value", aggfunc="first").reset_index()
    wide["도소매숙박음식_합계"] = wide["도소매_사업체수"] + wide["숙박음식_사업체수"]
    return wide


def main():
    print(f"[로드] {SBIZ_ALL_PATH}")
    sbiz = pd.read_csv(SBIZ_ALL_PATH, encoding="utf-8-sig", dtype={"상가업소번호": str, "행정동명": str,
                                                                    "상권업종대분류명": str, "기준분기": str})
    sbiz["연도"] = sbiz["기준분기"].str[:4]
    sbiz["분기"] = sbiz["기준분기"].str[-2:]
    q4 = sbiz[sbiz["분기"] == "Q4"]

    sbiz_all_cnt = q4.groupby(["행정동명", "연도"])["상가업소번호"].nunique().rename("소진공_점포수전체").reset_index()

    sub = q4[q4["상권업종대분류명"].isin(SBIZ_DOSOMAE_SUKBAK)]
    sbiz_sub_cnt = sub.groupby(["행정동명", "연도"])["상가업소번호"].nunique().rename("소진공_도소매숙박음식_점포수").reset_index()

    print(f"[로드] {BIZ_PATH}")
    biz = parse_biz_dosomae_sukbak()

    merged = sbiz_all_cnt.merge(sbiz_sub_cnt, on=["행정동명", "연도"], how="left") \
        .merge(biz, on=["행정동명", "연도"], how="left")

    # ---------------- 1. 화성시 전체 연도별 비교표 ----------------
    print("\n" + "=" * 80)
    print("[1] 화성시 전체 연도별 비교표 (2020~2023, Q4 시점)")
    print("=" * 80)
    total = merged.groupby("연도")[
        ["소진공_점포수전체", "소진공_도소매숙박음식_점포수", "도소매_사업체수", "숙박음식_사업체수", "도소매숙박음식_합계"]
    ].sum().reindex(["2020", "2021", "2022", "2023"])

    for col in total.columns:
        total[f"{col}_증감률"] = total[col].pct_change() * 100

    show_cols = ["소진공_점포수전체", "소진공_점포수전체_증감률",
                 "소진공_도소매숙박음식_점포수", "소진공_도소매숙박음식_점포수_증감률",
                 "도소매_사업체수", "도소매_사업체수_증감률",
                 "숙박음식_사업체수", "숙박음식_사업체수_증감률",
                 "도소매숙박음식_합계", "도소매숙박음식_합계_증감률"]
    print(total[show_cols].round(2).to_string())

    # ---------------- 2. 행정동별 증감률 상관계수 (2022->2023) ----------------
    print("\n" + "=" * 80)
    print("[2] 행정동별 2022->2023 증감률 상관계수")
    print("=" * 80)
    p22 = merged[merged["연도"] == "2022"].set_index("행정동명")
    p23 = merged[merged["연도"] == "2023"].set_index("행정동명")
    common = p22.index.intersection(p23.index)

    chg_sbiz_all = (p23.loc[common, "소진공_점포수전체"] - p22.loc[common, "소진공_점포수전체"]) / p22.loc[common, "소진공_점포수전체"] * 100
    chg_sbiz_sub = (p23.loc[common, "소진공_도소매숙박음식_점포수"] - p22.loc[common, "소진공_도소매숙박음식_점포수"]) / p22.loc[common, "소진공_도소매숙박음식_점포수"] * 100
    chg_biz = (p23.loc[common, "도소매숙박음식_합계"] - p22.loc[common, "도소매숙박음식_합계"]) / p22.loc[common, "도소매숙박음식_합계"] * 100

    corr_all = chg_sbiz_all.corr(chg_biz, method="pearson")
    corr_sub = chg_sbiz_sub.corr(chg_biz, method="pearson")
    corr_all_sp = chg_sbiz_all.corr(chg_biz, method="spearman")
    corr_sub_sp = chg_sbiz_sub.corr(chg_biz, method="spearman")

    print(f"소진공(전체업종) 증감률 vs 통계청(도소매+숙박음식) 증감률: 피어슨={corr_all:.3f}, 스피어만={corr_all_sp:.3f}")
    print(f"소진공(도소매+숙박음식만) 증감률 vs 통계청(도소매+숙박음식) 증감률: 피어슨={corr_sub:.3f}, 스피어만={corr_sub_sp:.3f}")

    detail = pd.DataFrame({
        "소진공_전체_증감률": chg_sbiz_all,
        "소진공_도소매숙박음식_증감률": chg_sbiz_sub,
        "통계청_도소매숙박음식_증감률": chg_biz,
    }).sort_values("통계청_도소매숙박음식_증감률")
    print("\n행정동별 상세 (통계청 증감률 오름차순):")
    print(detail.round(1).to_string())

    # ---------------- 3. 판정 ----------------
    print("\n" + "=" * 80)
    print("[3] 판정")
    print("=" * 80)
    biz_change_pct = total.loc["2023", "도소매숙박음식_합계_증감률"]
    sbiz_sub_change_pct = total.loc["2023", "소진공_도소매숙박음식_점포수_증감률"]
    sbiz_all_change_pct = total.loc["2023", "소진공_점포수전체_증감률"]

    print(f"통계청 도소매+숙박음식 2022->2023 증감률: {biz_change_pct:+.1f}%")
    print(f"소진공 도소매+숙박음식(부분집합) 2022->2023 증감률: {sbiz_sub_change_pct:+.1f}%")
    print(f"소진공 전체업종 2022->2023 증감률: {sbiz_all_change_pct:+.1f}%")

    if biz_change_pct <= -10:
        print("\n-> 통계청 도소매+숙박음식도 두 자릿수 감소: 실제 폐업 급증 뒷받침, 라벨 유효 가능성 높음")
    else:
        print(f"\n-> 통계청은 완만({biz_change_pct:+.1f}%)한데 소진공만 급감"
              f"({sbiz_sub_change_pct:+.1f}% / 전체 {sbiz_all_change_pct:+.1f}%)"
              " : 소진공 수록기준 변경 의심, 2022->2023 라벨 재검토 필요")


if __name__ == "__main__":
    main()
