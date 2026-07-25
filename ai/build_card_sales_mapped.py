"""
카드매출 업종코드(구/신 체계)를 공통업종 14개로 매핑하고,
그 매핑이 신-구 체계 경계에서 시계열 연속성을 실제로 확보하는지 검증한다.

배경: card_sales_hwaseong.csv의 MDCLASS_INDUTYPE_CD는 시기에 따라 완전히 다른
두 체계(구코드/신코드)를 쓰고, 집계 대상 범위가 달라 TO(총계)만으로는 비교가 안 됨
(verify_to_series.py에서 확인: 경계에서 최대 +318% 요동). 공통업종 매핑표
(card_industry_mapping.csv, 사람이 검토해 확정한 14개 카테고리)를 적용해
고정 바스켓 방식이 TO보다 안정적인지 확인한다.

사용법:
    python ai/build_card_sales_mapped.py
"""
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

CARD_PATH = next(PROJECT_ROOT.glob("**/card_sales_hwaseong.csv"))
MAPPING_PATH = next(PROJECT_ROOT.glob("**/card_industry_mapping.csv"))
POP_PATH = next(PROJECT_ROOT.glob("**/화성시_인구동향_시계열.csv"))
FLOW_PATH = next(PROJECT_ROOT.glob("**/유동인구_화성시_행정동_시간대별.csv"))

OUT_PATH = PROCESSED_DATA_DIR / "card_sales_mapped.csv"
VALIDATION_A_PATH = PROCESSED_DATA_DIR / "card_industry_continuity_check.csv"

# 소진공/카드매출 신코드(83개) — verify_2022q4_2023q1_gap.py, verify_to_series.py와 동일 기준.
# 월별 code_system(old/new) 판정에 사용 (매핑표에 없는 코드가 섞여도 안정적으로 판별하기 위해
# 매핑표가 아닌 전체 신코드 목록으로 판정).
NEW_SCHEME_CODES = {
    "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10",
    "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18", "D19",
    "F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F10",
    "F11", "F12", "F13", "F14", "F15", "F16", "F17",
    "O01", "O02", "O03", "O04",
    "Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10",
    "Q11", "Q12", "Q13", "Q14", "Q15", "Q16",
    "R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08",
    "S01", "S02", "S03", "S04", "S05", "S06",
    "T01", "T02", "T03", "T04",
    "U01", "U02", "U03", "U04",
    "Y01", "Y02", "Y03", "Y04", "Y05",
}

OLD_STABLE_MONTHS = ["202110", "202111", "202112"]
NEW_STABLE_MONTHS = ["202401", "202402", "202403"]


def month_sort_key(ym: str) -> int:
    return int(ym)


def load_mapping():
    df = pd.read_csv(MAPPING_PATH, encoding="utf-8-sig", dtype=str)
    code_to_industry = {}
    confidence_by_industry = {}
    for _, row in df.iterrows():
        industry = row["공통업종"]
        confidence_by_industry[industry] = row["확신도"]
        for col in ["구코드", "신코드"]:
            codes = str(row[col]).split(",")
            for c in codes:
                c = c.strip()
                if c:
                    code_to_industry[c] = industry
    return code_to_industry, confidence_by_industry, df


def classify_month_scheme(card_no_to: pd.DataFrame) -> dict:
    month_scheme = {}
    for ym, grp in card_no_to.groupby("STD_YM"):
        codes = set(grp["MDCLASS_INDUTYPE_CD"].unique())
        month_scheme[ym] = "new" if codes & NEW_SCHEME_CODES else "old"
    return month_scheme


def build_mapped(card_no_to: pd.DataFrame, code_to_industry: dict, month_scheme: dict):
    card_no_to = card_no_to.copy()
    card_no_to["공통업종"] = card_no_to["MDCLASS_INDUTYPE_CD"].map(code_to_industry)

    mapped_mask = card_no_to["공통업종"].notna()
    mapped_df = card_no_to[mapped_mask]
    excluded_df = card_no_to[~mapped_mask]

    total_non_to = card_no_to["SALES_AMT"].sum()
    mapped_sum = mapped_df["SALES_AMT"].sum()
    excluded_sum = excluded_df["SALES_AMT"].sum()

    print(f"\nTO 제외 전체 매출: {total_non_to:,.0f}")
    print(f"매핑된 매출: {mapped_sum:,.0f} ({mapped_sum/total_non_to*100:.1f}%)")
    print(f"제외된 매출(매핑표 없음): {excluded_sum:,.0f} ({excluded_sum/total_non_to*100:.1f}%)")

    excluded_by_code = (
        excluded_df.groupby("MDCLASS_INDUTYPE_CD")["SALES_AMT"].sum()
        .sort_values(ascending=False)
    )
    print("\n제외된 코드 상위 5개 (매출액 기준):")
    for code, amt in excluded_by_code.head(5).items():
        print(f"  {code:<6} {amt:>18,.0f} ({amt/total_non_to*100:.2f}%)")

    agg = (
        mapped_df.groupby(["STD_YM", "ADMDONG_CD", "공통업종"])["SALES_AMT"]
        .sum().reset_index()
    )
    agg["code_system"] = agg["STD_YM"].map(month_scheme)
    agg = agg.rename(columns={"STD_YM": "기준년월", "ADMDONG_CD": "행정동코드", "SALES_AMT": "매출금액"})

    return agg, mapped_df, excluded_by_code, mapped_sum / total_non_to * 100, excluded_sum / total_non_to * 100


def get_period_avg(df: pd.DataFrame, months: list, value_col="매출금액", group_col="공통업종") -> pd.Series:
    sub = df[df["기준년월"].isin(months)]
    monthly_total = sub.groupby(["기준년월", group_col])[value_col].sum().reset_index()
    return monthly_total.groupby(group_col)[value_col].mean()


def load_population_growth():
    pop = pd.read_csv(POP_PATH, encoding="cp949", dtype=str)
    row = pop[(pop["행정구역(동읍면)별"] == "화성시") & (pop["5세별"] == "계") & (pop["항목"] == "총인구수[명]")]
    if row.empty:
        return None
    before = pd.to_numeric(row["2021.12 월"].values[0].replace(",", ""))
    after = pd.to_numeric(row["2024.03 월"].values[0].replace(",", ""))
    return (after - before) / before * 100, before, after


def load_floating_pop_growth():
    flow = pd.read_csv(FLOW_PATH, encoding="utf-8-sig", dtype=str)
    flow = flow[flow["시간대코드"] == "TOT"].copy()
    flow["유동인구수"] = pd.to_numeric(flow["유동인구수"].str.replace(",", ""), errors="coerce")
    before = flow[flow["기준년월"].isin(OLD_STABLE_MONTHS)].groupby("기준년월")["유동인구수"].sum().mean()
    after = flow[flow["기준년월"].isin(NEW_STABLE_MONTHS)].groupby("기준년월")["유동인구수"].sum().mean()
    return (after - before) / before * 100, before, after


def validation_a(agg: pd.DataFrame, confidence_by_industry: dict, ref_growth: float):
    print("\n" + "=" * 70)
    print("[검증 A] 업종별 구코드(2021Q4) vs 신코드(2024Q1) 연속성")
    print("=" * 70)

    old_avg = get_period_avg(agg, OLD_STABLE_MONTHS)
    new_avg = get_period_avg(agg, NEW_STABLE_MONTHS)

    rows = []
    for industry in sorted(set(old_avg.index) | set(new_avg.index)):
        o = old_avg.get(industry, float("nan"))
        n = new_avg.get(industry, float("nan"))
        if pd.isna(o) or pd.isna(n) or o == 0:
            change = float("nan")
        else:
            change = (n - o) / o * 100
        lower, upper = ref_growth - 30, ref_growth + 30
        if pd.isna(change):
            verdict = "데이터 부족"
        elif lower <= change <= upper:
            verdict = "연속(정상)"
        else:
            verdict = "의심(매핑 불일치 가능)"
        rows.append({
            "공통업종": industry, "확신도": confidence_by_industry.get(industry, ""),
            "2021Q4평균": o, "2024Q1평균": n, "변화율%": round(change, 1) if not pd.isna(change) else None,
            "연속성판정": verdict,
        })

    result = pd.DataFrame(rows).sort_values("2024Q1평균", ascending=False)
    print(f"\n(참고 기준: 화성시 인구/유동인구 증가율 ± 30%p 범위 = [{ref_growth-30:.1f}%, {ref_growth+30:.1f}%])\n")
    print(result.to_string(index=False))
    result.to_csv(VALIDATION_A_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장: {VALIDATION_A_PATH}")
    return result


def validation_b(agg: pd.DataFrame, card_no_to: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[검증 B] 고정 바스켓(14개 업종 합) vs TO — 어느 쪽이 연속적인가")
    print("=" * 70)

    basket_monthly = agg.groupby("기준년월")["매출금액"].sum()
    basket_old = basket_monthly.reindex(OLD_STABLE_MONTHS).mean()
    basket_new = basket_monthly.reindex(NEW_STABLE_MONTHS).mean()
    basket_change = (basket_new - basket_old) / basket_old * 100

    to_monthly = card_no_to.groupby("STD_YM")["SALES_AMT"].sum()
    # TO는 card_no_to(=TO 제외본)에 없으므로 원본에서 별도 로드 필요 -> main에서 전달
    print(f"고정 바스켓: 2021Q4 평균 {basket_old:,.0f} -> 2024Q1 평균 {basket_new:,.0f} ({basket_change:+.1f}%)")
    return basket_change


def validation_c(agg: pd.DataFrame, month_scheme: dict):
    print("\n" + "=" * 70)
    print("[검증 C] 혼재구간(2022-01~2023-12) 내부 run별 안정성")
    print("=" * 70)

    mixed_months = sorted([m for m in month_scheme if "202201" <= m <= "202312"], key=month_sort_key)
    runs = []
    cur_scheme = None
    cur_run = []
    for m in mixed_months:
        s = month_scheme[m]
        if s != cur_scheme:
            if cur_run:
                runs.append((cur_scheme, cur_run))
            cur_run = [m]
            cur_scheme = s
        else:
            cur_run.append(m)
    if cur_run:
        runs.append((cur_scheme, cur_run))

    basket_monthly = agg.groupby("기준년월")["매출금액"].sum()

    print(f"혼재구간 run 수: {len(runs)}")
    usable_runs = []
    for scheme, months in runs:
        if len(months) < 2:
            print(f"  run({scheme}, {months}): 1개월뿐 -> 전월비 계산 불가, 판단 보류")
            continue
        vals = basket_monthly.reindex(months)
        pct_changes = vals.pct_change().dropna() * 100
        max_abs = pct_changes.abs().max() if len(pct_changes) else float("nan")
        ok = bool((pct_changes.abs() <= 30).all()) if len(pct_changes) else False
        usable_runs.append((scheme, months, ok))
        status = "정상 범위(사용 가능)" if ok else "이상 변동 있음(주의)"
        print(f"  run({scheme}, {months[0]}~{months[-1]}, {len(months)}개월): 최대 전월비 변화 {max_abs:.1f}% -> {status}")

    return usable_runs


def rank_industries(agg: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[참고] 업종별 화성시 매출 규모 순위 (매핑 전체 기간 합계)")
    print("=" * 70)
    rank = agg.groupby("공통업종")["매출금액"].sum().sort_values(ascending=False)
    for industry, amt in rank.items():
        print(f"  {industry:<8} {amt:>20,.0f}")
    return rank


def main():
    t0 = time.time()

    print(f"카드매출: {CARD_PATH}")
    print(f"매핑표: {MAPPING_PATH}")

    card = pd.read_csv(
        CARD_PATH, encoding="utf-8-sig",
        dtype={"MDCLASS_INDUTYPE_CD": str, "ADMDONG_CD": str, "STD_YM": str},
    )
    card["SALES_AMT"] = pd.to_numeric(card["SALES_AMT"], errors="coerce")

    card_no_to = card[card["MDCLASS_INDUTYPE_CD"] != "TO"].copy()
    to_only = card[card["MDCLASS_INDUTYPE_CD"] == "TO"].copy()

    print("\n매핑표 로드 중...")
    code_to_industry, confidence_by_industry, mapping_df = load_mapping()
    print(f"  공통업종 {mapping_df['공통업종'].nunique()}개, 코드 {len(code_to_industry)}개 등록")

    print("\n월별 code_system(구/신) 판정 중...")
    month_scheme = classify_month_scheme(card_no_to)

    print("\n업종 매핑 적용 및 집계 중...")
    agg, mapped_df, excluded_by_code, mapped_pct, excluded_pct = build_mapped(card_no_to, code_to_industry, month_scheme)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    agg.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUT_PATH} ({len(agg):,}행)")

    print("\n참고 성장률(2021-12 vs 2024-03) 계산 중...")
    pop_growth, pop_before, pop_after = load_population_growth()
    print(f"  화성시 총인구: {pop_before:,.0f} -> {pop_after:,.0f} ({pop_growth:+.1f}%)")
    flow_growth, flow_before, flow_after = load_floating_pop_growth()
    print(f"  화성시 유동인구(TOT, 2021Q4avg vs 2024Q1avg): {flow_before:,.0f} -> {flow_after:,.0f} ({flow_growth:+.1f}%)")

    print(f"  ⚠ 유동인구 데이터 자체가 2022~2023년 사이 동일 시기에 스케일이 약 13배 오락가락"
          f"(카드매출 신/구코드 전환과 같은 시기) — 참고 기준에서 제외, 인구증가율만 사용")
    ref_growth = pop_growth
    print(f"  참고 기준(화성시 총인구 증가율만 사용): {ref_growth:+.1f}%")

    result_a = validation_a(agg, confidence_by_industry, ref_growth)
    basket_change = validation_b(agg, card_no_to)

    to_monthly = to_only.groupby("STD_YM")["SALES_AMT"].sum()
    to_old = to_monthly.reindex(OLD_STABLE_MONTHS).mean()
    to_new = to_monthly.reindex(NEW_STABLE_MONTHS).mean()
    to_change = (to_new - to_old) / to_old * 100
    print(f"TO 총계: 2021Q4 평균 {to_old:,.0f} -> 2024Q1 평균 {to_new:,.0f} ({to_change:+.1f}%)")
    print(f"\n비교: 고정 바스켓 {basket_change:+.1f}% vs TO {to_change:+.1f}% "
          f"(참고 기준 {ref_growth:+.1f}%)")
    if abs(basket_change - ref_growth) < abs(to_change - ref_growth):
        print("  -> 고정 바스켓이 TO보다 참고 성장률에 더 가까움 (더 안정적)")
    else:
        print("  -> TO가 고정 바스켓보다 참고 성장률에 더 가까움 (예상과 다름, 재검토 필요)")

    usable_runs = validation_c(agg, month_scheme)

    rank = rank_industries(agg)

    elapsed = time.time() - t0
    print(f"\n총 소요 시간: {elapsed:.1f}초")


if __name__ == "__main__":
    main()
