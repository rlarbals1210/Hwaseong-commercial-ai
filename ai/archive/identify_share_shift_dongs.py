"""
카드매출 share 검증(verify_scale_invariant_share.py)에서 반복적으로 상승/하락한
행정동들의 실제 동네 이름을 확인하고, 화성시 전체 행정동에 대해 5개 핵심 업종
평균 share 변화를 정렬해 지리적 패턴을 파악한다.

사용법:
    python ai/identify_share_shift_dongs.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

MAPPED_PATH = PROCESSED_DATA_DIR / "card_sales_mapped.csv"
DONG_LIST_PATH = next(PROJECT_ROOT.glob("**/경기도_읍면동_리스트.csv"))

OLD_STABLE_MONTHS = ["202110", "202111", "202112"]
NEW_STABLE_MONTHS = ["202401", "202402", "202403"]
CORE_INDUSTRIES = ["음식점", "미용", "학원·교육", "의료", "종합소매"]

HIGHLIGHT_UP = {"4159060000", "4159061000", "4159058800"}
HIGHLIGHT_DOWN = {"4159058500", "4159052000", "4159026200"}


def load_dong_names() -> dict:
    df = pd.read_csv(DONG_LIST_PATH, encoding="cp949", dtype=str)
    return dict(zip(df["읍면동코드"], df["읍면동명"]))


def main():
    print(f"입력: {MAPPED_PATH}")
    mapped = pd.read_csv(MAPPED_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "기준년월": str})

    dong_names = load_dong_names()

    print("\n하이라이트 행정동 이름 조회")
    print("share 상승 그룹:")
    for code in HIGHLIGHT_UP:
        print(f"  {code} -> {dong_names.get(code, '이름 미확인')}")
    print("share 하락 그룹:")
    for code in HIGHLIGHT_DOWN:
        print(f"  {code} -> {dong_names.get(code, '이름 미확인')}")

    core = mapped[mapped["공통업종"].isin(CORE_INDUSTRIES)]

    rows = []
    for industry in CORE_INDUSTRIES:
        sub = core[core["공통업종"] == industry]
        month_dong_total = sub.groupby(["기준년월", "행정동코드"])["매출금액"].sum().reset_index()
        month_total = month_dong_total.groupby("기준년월")["매출금액"].transform("sum")
        month_dong_total["share"] = month_dong_total["매출금액"] / month_total

        old_share = month_dong_total[month_dong_total["기준년월"].isin(OLD_STABLE_MONTHS)] \
            .groupby("행정동코드")["share"].mean()
        new_share = month_dong_total[month_dong_total["기준년월"].isin(NEW_STABLE_MONTHS)] \
            .groupby("행정동코드")["share"].mean()

        common = old_share.index.intersection(new_share.index)
        diff_pp = (new_share.loc[common] - old_share.loc[common]) * 100
        rows.append(diff_pp.rename(industry))

    industry_diff_df = pd.concat(rows, axis=1)
    avg_diff = industry_diff_df.mean(axis=1)

    # 2024Q1 평균 매출 규모 (핵심 5개 업종 합, 참고용)
    q1_2024 = core[core["기준년월"].isin(NEW_STABLE_MONTHS)]
    q1_2024_by_dong_month = q1_2024.groupby(["행정동코드", "기준년월"])["매출금액"].sum().reset_index()
    q1_2024_avg = q1_2024_by_dong_month.groupby("행정동코드")["매출금액"].mean()

    result = pd.DataFrame({
        "행정동명": [dong_names.get(c, "이름 미확인") for c in avg_diff.index],
        "행정동코드": avg_diff.index,
        "평균share변화(pp)": avg_diff.values,
        "2024Q1매출규모": q1_2024_avg.reindex(avg_diff.index).values,
    })
    result = result.sort_values("평균share변화(pp)", ascending=False).reset_index(drop=True)
    result["순위"] = result.index + 1

    print("\n" + "=" * 90)
    print("화성시 행정동별 5개 핵심업종 평균 share 변화 (2021Q4 -> 2024Q1), 매출규모 순 아님 - 변화량 순")
    print("=" * 90)
    with pd.option_context("display.float_format", "{:,.2f}".format):
        print(result[["순위", "행정동명", "행정동코드", "평균share변화(pp)", "2024Q1매출규모"]].to_string(index=False))

    out_path = PROCESSED_DATA_DIR / "dong_share_shift_ranked.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
