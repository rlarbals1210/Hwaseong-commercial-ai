"""
신규 유동인구 데이터(TB25BPTPOPDAYDONGM, 요일별 집계) 연속성 확인.
0단계 기본파악 -> 1단계 절대값 연속성(핵심) -> (단차 있으면) 2단계 share 검증.

사용법:
    python ai/verify_new_flow_pop_continuity.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOW_PATH = next(PROJECT_ROOT.glob("**/floating_pop_hwaseong.csv"))

OLD_STABLE_MONTHS = ["202110", "202111", "202112"]
NEW_STABLE_MONTHS = ["202401", "202402", "202403"]


def month_sort_key(ym: str) -> int:
    return int(ym)


def main():
    print(f"입력: {FLOW_PATH}")
    df = pd.read_csv(FLOW_PATH, encoding="utf-8-sig", dtype={"STD_YM": str, "ADMDONG_CD": str})

    # ---------- 0단계: 기본 파악 ----------
    print("\n" + "=" * 70)
    print("[0단계] 기본 파악")
    print("=" * 70)
    print(f"컬럼: {df.columns.tolist()}")
    months = sorted(df["STD_YM"].unique(), key=month_sort_key)
    print(f"기간: {months[0]} ~ {months[-1]} (총 {len(months)}개월)")
    print(f"요일코드: {sorted(df['WDAY_CD'].unique())}")
    print(f"행정동 수: {df['ADMDONG_CD'].nunique()}")

    # 단위 추정: 한 달 x 한 행정동에 요일별 행이 몇 개 있고, 합치면 얼마나 되는지
    sample_month = months[len(months) // 2]
    sample_dong = df["ADMDONG_CD"].iloc[0]
    sample = df[(df["STD_YM"] == sample_month) & (df["ADMDONG_CD"] == sample_dong)]
    print(f"\n샘플 ({sample_dong}, {sample_month}) 요일별 값:")
    print(sample[["WDAY_CD", "DYNMC_POPLTN_CNT"]].to_string(index=False))
    print(f"  요일 7개 합: {sample['DYNMC_POPLTN_CNT'].sum():,.1f}")
    print(f"  요일 7개 평균: {sample['DYNMC_POPLTN_CNT'].mean():,.1f}")

    # ---------- 1단계: 절대값 연속성 ----------
    print("\n" + "=" * 70)
    print("[1단계] 화성시 전체 합계 월별 추이 및 단차 확인")
    print("=" * 70)

    # 주의: WDAY_CD=='TOT'를 요일 7개와 함께 합치면 안 됨.
    # 2018-01~2021-11엔 TOT ≈ 요일 평균(요일합의 1/7 수준)이었다가, 2021-12(결측)를
    # 건너뛰고 2022-01부터 TOT/요일합 비율이 갑자기 ~4.4배로 뛰어 그대로 굳어짐.
    # TOT+요일 7개를 그대로 더하면 두 구간의 반대방향 요동이 서로 상쇄돼 "단차 없음"으로
    # 잘못 보임(실제 확인된 착시). 요일 7개 합만 기준으로 삼음(TOT 제외).
    df_no_tot = df[df["WDAY_CD"] != "TOT"]
    monthly_total = df_no_tot.groupby("STD_YM")["DYNMC_POPLTN_CNT"].sum().reindex(months)

    print("\n월별 화성시 합계 (앞 5개월 / 뒤 5개월):")
    print(monthly_total.head(5).to_string())
    print("...")
    print(monthly_total.tail(5).to_string())

    old_avg = monthly_total.reindex(OLD_STABLE_MONTHS).mean()
    new_avg = monthly_total.reindex(NEW_STABLE_MONTHS).mean()
    change_pct = (new_avg - old_avg) / old_avg * 100
    print(f"\n2021-10~12 평균: {old_avg:,.1f}")
    print(f"2024-01~03 평균: {new_avg:,.1f}")
    print(f"변화율: {change_pct:+.1f}%")

    print("\n전월대비 변화율 전 기간 스캔 (절대값 20% 초과만 표시):")
    mom_change = monthly_total.pct_change() * 100
    big_changes = mom_change[mom_change.abs() > 20]
    if len(big_changes) == 0:
        print("  없음 — 전 기간 전월비 변화 20% 이내")
    else:
        for ym, chg in big_changes.items():
            print(f"  {ym}: {chg:+.1f}%")

    has_discontinuity = len(big_changes) > 0 or abs(change_pct) > 20
    print(f"\n판정: {'단차 있음 -> 2단계 진행' if has_discontinuity else '단차 없음 -> 절대값 그대로 사용 가능, 종료'}")

    if not has_discontinuity:
        return

    # ---------- 2단계: share 검증 ----------
    print("\n" + "=" * 70)
    print("[2단계] 행정동별 share 검증")
    print("=" * 70)

    dong_month_total = df_no_tot.groupby(["STD_YM", "ADMDONG_CD"])["DYNMC_POPLTN_CNT"].sum().reset_index()
    month_total = dong_month_total.groupby("STD_YM")["DYNMC_POPLTN_CNT"].transform("sum")
    dong_month_total["share"] = dong_month_total["DYNMC_POPLTN_CNT"] / month_total

    old_share = dong_month_total[dong_month_total["STD_YM"].isin(OLD_STABLE_MONTHS)] \
        .groupby("ADMDONG_CD")["share"].mean()
    new_share = dong_month_total[dong_month_total["STD_YM"].isin(NEW_STABLE_MONTHS)] \
        .groupby("ADMDONG_CD")["share"].mean()

    common = old_share.index.intersection(new_share.index)
    old_c = old_share.loc[common]
    new_c = new_share.loc[common]

    corr = old_c.corr(new_c, method="spearman")
    diff_pp = (new_c - old_c) * 100
    mean_abs_diff = diff_pp.abs().mean()

    print(f"행정동 {len(common)}개 비교")
    print(f"순위 상관계수(스피어만): {corr:.3f}")
    print(f"평균 |share 변화|: {mean_abs_diff:.2f}%p")

    if corr >= 0.8 and mean_abs_diff <= 5:
        verdict = "보존됨 (share 기반 feature 사용 가능)"
    else:
        verdict = "보존 안 됨 (share도 못 씀)"
    print(f"판정: {verdict}")

    diff_sorted = diff_pp.sort_values()
    print(f"\nshare 변화 하위(감소) 5곳:\n{diff_sorted.head(5).to_string()}")
    print(f"\nshare 변화 상위(증가) 5곳:\n{diff_sorted.tail(5).to_string()}")


if __name__ == "__main__":
    main()
