"""
스케일 불변 feature(비중/share) 사용 가능성 검증.

배경: 카드매출·유동인구 모두 2022~2023년 집계방식 변경으로 절대값 비교 불가
(build_card_sales_mapped.py, verify_to_series.py에서 확인). 절대값 대신
"비중(share)"은 전체 스케일이 바뀌어도 분자·분모가 같이 스케일되면 보존되는
성질이 있으므로, 이걸로 전 기간 연속 feature를 만들 수 있는지 확인한다.

검증 1: 업종 내 행정동 비중 (핵심 5개 업종)
검증 2: 유동인구 행정동 비중
검증 3: 행정동 내 업종 구성비 (보조, 낮게 나올 것으로 예상)

사용법:
    python ai/verify_scale_invariant_share.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

MAPPED_PATH = PROCESSED_DATA_DIR / "card_sales_mapped.csv"
FLOW_PATH = next(PROJECT_ROOT.glob("**/유동인구_화성시_행정동_시간대별.csv"))

OLD_STABLE_MONTHS = ["202110", "202111", "202112"]
NEW_STABLE_MONTHS = ["202401", "202402", "202403"]
CORE_INDUSTRIES = ["음식점", "미용", "학원·교육", "의료", "종합소매"]


def judge(corr: float, mean_abs_diff_pp: float) -> str:
    if pd.isna(corr):
        return "데이터 부족"
    if corr >= 0.8 and mean_abs_diff_pp <= 5:
        return "보존됨 (share 기반 feature 사용 가능)"
    return "보존 안 됨 (share도 못 씀)"


def verify_1(mapped: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[검증 1] 업종 내 행정동 비중(share) 안정성 — 핵심 5개 업종")
    print("=" * 70)

    rows = []
    for industry in CORE_INDUSTRIES:
        sub = mapped[mapped["공통업종"] == industry]
        if sub.empty:
            print(f"\n■ {industry}: 데이터 없음")
            continue

        month_dong_total = sub.groupby(["기준년월", "행정동코드"])["매출금액"].sum().reset_index()
        month_total = month_dong_total.groupby("기준년월")["매출금액"].transform("sum")
        month_dong_total["share"] = month_dong_total["매출금액"] / month_total

        old = month_dong_total[month_dong_total["기준년월"].isin(OLD_STABLE_MONTHS)]
        new = month_dong_total[month_dong_total["기준년월"].isin(NEW_STABLE_MONTHS)]

        old_share = old.groupby("행정동코드")["share"].mean()
        new_share = new.groupby("행정동코드")["share"].mean()

        common = old_share.index.intersection(new_share.index)
        old_c = old_share.loc[common]
        new_c = new_share.loc[common]

        corr = old_c.corr(new_c, method="spearman") if len(common) >= 3 else float("nan")
        diff_pp = (new_c - old_c) * 100
        mean_abs_diff = diff_pp.abs().mean()

        verdict = judge(corr, mean_abs_diff)
        print(f"\n■ {industry} (행정동 {len(common)}개 비교)")
        print(f"  순위 상관계수(스피어만): {corr:.3f}" if not pd.isna(corr) else "  상관계수 계산 불가")
        print(f"  평균 |share 변화|: {mean_abs_diff:.2f}%p")
        print(f"  판정: {verdict}")

        diff_sorted = diff_pp.sort_values()
        print(f"  share 변화 하위(감소) 5곳:\n{diff_sorted.head(5).to_string()}")
        print(f"  share 변화 상위(증가) 5곳:\n{diff_sorted.tail(5).to_string()}")

        rows.append({"업종": industry, "행정동수": len(common), "순위상관계수": corr,
                      "평균share변화(pp)": mean_abs_diff, "판정": verdict})

    return pd.DataFrame(rows)


def verify_2():
    print("\n" + "=" * 70)
    print("[검증 2] 유동인구 행정동 비중(share) 안정성")
    print("=" * 70)

    flow_raw = pd.read_csv(FLOW_PATH, encoding="utf-8-sig", dtype={"기준년월": str, "행정동코드": str})
    # 주의: TOT행은 행정동별 값이 아니라 그 달 화성시 전체 총계가 모든 행정동 행에
    # 그대로 복제되어 있음(확인됨 - 전 행정동 동일값, 유동인구수비율도 항상 100.0).
    # 행정동별 실제 분포는 시간대 구간(TZ01~TZ10) 합산으로 구해야 함.
    flow = flow_raw[flow_raw["시간대코드"] != "TOT"].copy()
    flow["유동인구수"] = pd.to_numeric(flow["유동인구수"].astype(str).str.replace(",", ""), errors="coerce")
    flow = flow.groupby(["기준년월", "행정동코드"])["유동인구수"].sum().reset_index()

    month_total = flow.groupby("기준년월")["유동인구수"].transform("sum")
    flow["share"] = flow["유동인구수"] / month_total

    old = flow[flow["기준년월"].isin(OLD_STABLE_MONTHS)]
    new = flow[flow["기준년월"].isin(NEW_STABLE_MONTHS)]

    old_share = old.groupby("행정동코드")["share"].mean()
    new_share = new.groupby("행정동코드")["share"].mean()

    common = old_share.index.intersection(new_share.index)
    old_c = old_share.loc[common]
    new_c = new_share.loc[common]

    corr = old_c.corr(new_c, method="spearman")
    diff_pp = (new_c - old_c) * 100
    mean_abs_diff = diff_pp.abs().mean()
    verdict = judge(corr, mean_abs_diff)

    print(f"  행정동 {len(common)}개 비교")
    print(f"  순위 상관계수(스피어만): {corr:.3f}")
    print(f"  평균 |share 변화|: {mean_abs_diff:.2f}%p")
    print(f"  판정: {verdict}")

    diff_sorted = diff_pp.sort_values()
    print(f"\n  share 변화 하위(감소) 5곳:\n{diff_sorted.head(5).to_string()}")
    print(f"  share 변화 상위(증가) 5곳:\n{diff_sorted.tail(5).to_string()}")

    return {"항목": "유동인구", "행정동수": len(common), "순위상관계수": corr,
            "평균share변화(pp)": mean_abs_diff, "판정": verdict}


def verify_3(mapped: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[검증 3, 보조] 행정동 내 업종 구성비 안정성")
    print("=" * 70)

    dong_month_industry = mapped.groupby(["행정동코드", "기준년월", "공통업종"])["매출금액"].sum().reset_index()
    dong_month_total = dong_month_industry.groupby(["행정동코드", "기준년월"])["매출금액"].transform("sum")
    dong_month_industry["share"] = dong_month_industry["매출금액"] / dong_month_total

    old = dong_month_industry[dong_month_industry["기준년월"].isin(OLD_STABLE_MONTHS)]
    new = dong_month_industry[dong_month_industry["기준년월"].isin(NEW_STABLE_MONTHS)]

    old_share = old.groupby(["행정동코드", "공통업종"])["share"].mean()
    new_share = new.groupby(["행정동코드", "공통업종"])["share"].mean()

    common = old_share.index.intersection(new_share.index)
    old_c = old_share.loc[common]
    new_c = new_share.loc[common]

    corr = old_c.corr(new_c, method="spearman")
    diff_pp = (new_c - old_c) * 100
    mean_abs_diff = diff_pp.abs().mean()
    verdict = judge(corr, mean_abs_diff)

    print(f"  (행정동x업종) 조합 {len(common)}개 비교")
    print(f"  순위 상관계수(스피어만): {corr:.3f}")
    print(f"  평균 |구성비 변화|: {mean_abs_diff:.2f}%p")
    print(f"  판정: {verdict}")

    return {"항목": "업종구성비(행정동내)", "조합수": len(common), "순위상관계수": corr,
            "평균share변화(pp)": mean_abs_diff, "판정": verdict}


def main():
    print(f"입력: {MAPPED_PATH}")
    mapped = pd.read_csv(MAPPED_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "기준년월": str})

    result_1 = verify_1(mapped)
    result_2 = verify_2()
    result_3 = verify_3(mapped)

    out_path = PROCESSED_DATA_DIR / "share_invariance_check.csv"
    combined = pd.concat([
        result_1.rename(columns={"업종": "항목"}),
        pd.DataFrame([result_2]),
        pd.DataFrame([result_3]),
    ], ignore_index=True)
    combined.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")

    print("\n" + "=" * 70)
    print("[종합 판정]")
    print("=" * 70)
    print(combined.to_string(index=False))


if __name__ == "__main__":
    main()
