"""
TO(행정동x월 카드매출 총계) 시계열이 상권활력 feature로 쓸만한지 검증.

확인 항목:
1. 커버리지: 행정동 x 전체 월 조합 중 TO행 존재 비율, 결측 행정동/월
2. 연속성: 구코드<->신코드 전환 경계에서 비정상 점프/급락 여부
3. 이상치: 0/음수/극단값

사용법:
    python ai/verify_to_series.py
"""
import sys
from pathlib import Path

import pandas as pd

CARD_PATH = None
for p in Path(".").glob("**/card_sales_hwaseong.csv"):
    CARD_PATH = p
    break
if CARD_PATH is None:
    raise FileNotFoundError("card_sales_hwaseong.csv를 찾을 수 없음")


def month_sort_key(ym: str) -> int:
    return int(ym)


def main():
    print(f"입력: {CARD_PATH}")
    card = pd.read_csv(CARD_PATH, encoding="utf-8-sig", dtype={"MDCLASS_INDUTYPE_CD": str, "ADMDONG_CD": str, "STD_YM": str})
    card["SALES_AMT"] = pd.to_numeric(card["SALES_AMT"], errors="coerce")

    to_df = card[card["MDCLASS_INDUTYPE_CD"] == "TO"].copy()
    print(f"TO 행 수: {len(to_df):,}")

    all_months = sorted(card["STD_YM"].unique(), key=month_sort_key)
    all_dongs = sorted(card["ADMDONG_CD"].unique())
    print(f"전체 월 수: {len(all_months)} ({all_months[0]} ~ {all_months[-1]})")
    print(f"전체 행정동 수: {len(all_dongs)}")

    # ---------- 1. 커버리지 ----------
    print("\n" + "=" * 70)
    print("[1] 커버리지: 행정동 x 월 조합 중 TO행 존재 비율")
    print("=" * 70)
    expected = len(all_months) * len(all_dongs)
    actual = len(to_df.drop_duplicates(subset=["ADMDONG_CD", "STD_YM"]))
    print(f"  기대 조합 수: {expected:,} (행정동 {len(all_dongs)} x 월 {len(all_months)})")
    print(f"  실제 TO 조합 수: {actual:,}")
    print(f"  커버리지: {actual / expected * 100:.1f}%")

    pivot = to_df.pivot_table(index="ADMDONG_CD", columns="STD_YM", values="SALES_AMT", aggfunc="size")
    missing_by_dong = pivot.isna().sum(axis=1).sort_values(ascending=False)
    dongs_with_gap = missing_by_dong[missing_by_dong > 0]
    print(f"\n  결측 있는 행정동 수: {len(dongs_with_gap)} / {len(all_dongs)}")
    if len(dongs_with_gap) > 0:
        print("  결측 많은 행정동 상위 10개:")
        for dong, cnt in dongs_with_gap.head(10).items():
            missing_months = pivot.columns[pivot.loc[dong].isna()].tolist()
            print(f"    {dong}: {cnt}개월 결측 (예: {missing_months[:5]})")

    missing_by_month = pivot.isna().sum(axis=0).sort_values(ascending=False)
    months_with_gap = missing_by_month[missing_by_month > 0]
    print(f"\n  결측 있는 월 수: {len(months_with_gap)} / {len(all_months)}")
    if len(months_with_gap) > 0:
        print("  결측 많은 월 상위 10개:")
        for ym, cnt in months_with_gap.head(10).items():
            print(f"    {ym}: {cnt}개 행정동 결측")

    # ---------- 2. 연속성 (구/신코드 경계) ----------
    print("\n" + "=" * 70)
    print("[2] 연속성: 구코드<->신코드 전환 경계에서 점프/급락 여부")
    print("=" * 70)

    NEW_SCHEME_CODES = {
        "D01","D02","D03","D04","D05","D06","D07","D08","D09","D10","D11","D12","D13","D14","D15","D16","D17","D18","D19",
        "F01","F02","F03","F04","F05","F06","F07","F08","F09","F10","F11","F12","F13","F14","F15","F16","F17",
        "O01","O02","O03","O04",
        "Q01","Q02","Q03","Q04","Q05","Q06","Q07","Q08","Q09","Q10","Q11","Q12","Q13","Q14","Q15","Q16",
        "R01","R02","R03","R04","R05","R06","R07","R08",
        "S01","S02","S03","S04","S05","S06",
        "T01","T02","T03","T04",
        "U01","U02","U03","U04",
        "Y01","Y02","Y03","Y04","Y05",
    }
    month_scheme = {}
    for ym, grp in card[card["MDCLASS_INDUTYPE_CD"] != "TO"].groupby("STD_YM"):
        codes = set(grp["MDCLASS_INDUTYPE_CD"].unique())
        month_scheme[ym] = "new" if codes & NEW_SCHEME_CODES else "old"

    months_sorted = sorted(month_scheme, key=month_sort_key)
    schemes_seq = [month_scheme[m] for m in months_sorted]
    transitions = [i for i in range(1, len(months_sorted)) if schemes_seq[i] != schemes_seq[i - 1]]
    print(f"  체계 전환 지점 수: {len(transitions)}")

    monthly_total = to_df.groupby("STD_YM")["SALES_AMT"].sum()

    for i in transitions:
        boundary_month = months_sorted[i]
        before_months = months_sorted[max(0, i - 3):i]
        after_months = months_sorted[i:i + 3]
        before_avg = monthly_total.reindex(before_months).mean()
        after_avg = monthly_total.reindex(after_months).mean()
        change_pct = (after_avg - before_avg) / before_avg * 100 if before_avg else float("nan")
        print(f"\n  전환: {schemes_seq[i-1]} -> {schemes_seq[i]} at {boundary_month}")
        print(f"    직전 3개월({before_months}) 평균: {before_avg:,.0f}")
        print(f"    직후 3개월({after_months}) 평균: {after_avg:,.0f}")
        print(f"    변화율: {change_pct:+.1f}%")

    # ---------- 3. 이상치 ----------
    print("\n" + "=" * 70)
    print("[3] 이상치: 0원 / 음수 / 극단값")
    print("=" * 70)
    zero_cnt = (to_df["SALES_AMT"] == 0).sum()
    neg_cnt = (to_df["SALES_AMT"] < 0).sum()
    na_cnt = to_df["SALES_AMT"].isna().sum()
    print(f"  0원: {zero_cnt:,}건 / 음수: {neg_cnt:,}건 / NaN: {na_cnt:,}건")

    desc = to_df["SALES_AMT"].describe()
    print(f"\n  기술통계:\n{desc}")

    q1, q3 = to_df["SALES_AMT"].quantile([0.25, 0.75])
    iqr = q3 - q1
    upper = q3 + 3 * iqr
    lower = q1 - 3 * iqr
    extreme = to_df[(to_df["SALES_AMT"] > upper) | (to_df["SALES_AMT"] < lower)]
    print(f"\n  IQR*3 기준 극단값: {len(extreme):,}건 ({len(extreme)/len(to_df)*100:.2f}%)")
    if len(extreme) > 0:
        print("  상위 5개:")
        print(extreme.nlargest(5, "SALES_AMT")[["ADMDONG_CD", "STD_YM", "SALES_AMT"]].to_string(index=False))

    # ---------- 판정 ----------
    print("\n" + "=" * 70)
    print("[판정]")
    print("=" * 70)
    coverage_ratio = actual / expected * 100
    max_jump = max((abs((monthly_total.reindex(months_sorted[i:i+3]).mean() -
                          monthly_total.reindex(months_sorted[max(0,i-3):i]).mean()) /
                         monthly_total.reindex(months_sorted[max(0,i-3):i]).mean() * 100)
                    for i in transitions), default=0)
    print(f"  커버리지 {coverage_ratio:.1f}%, 최대 경계 변화율 {max_jump:.1f}%")
    if coverage_ratio >= 95 and max_jump < 20:
        print("  -> 커버리지 높고 경계 단절 미미: TO를 상권활력 feature로 채택 가능")
    else:
        print("  -> 커버리지 부족 또는 경계 단절 존재: 단절 시점 이후 구간만 사용하거나 정규화 필요")


if __name__ == "__main__":
    main()
