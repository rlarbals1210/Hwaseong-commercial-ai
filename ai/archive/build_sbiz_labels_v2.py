"""
폐업 라벨 v2: "연속 2분기 이상 부재 시 폐업" 규칙으로 v1(1분기 부재=폐업)을 보강.

v1(sbiz_labels.csv, is_closed)은 1분기만 명단에서 빠져도 폐업으로 잡아 일시휴업/
명단 누락을 폐업으로 오분류하는 문제가 있었음. v2는 T+1, T+2 두 분기 모두 부재일 때만
폐업으로 판정해 이 노이즈를 줄인다. 원칙: v1 파일은 절대 덮어쓰지 않고 v2를 별도 파일로 저장,
얼마나 줄었는지(=휴업 노이즈 규모) 비교 가능하도록 유지.

입력: data/processed/sbiz_hwaseong_all.csv (재생성 없이 그대로 사용)
출력: data/processed/sbiz_labels_v2.csv (점포x분기 패널, is_closed_v2 포함,
      마지막 2개 분기는 판정 근거 부족으로 NaN)

사용법:
    python ai/build_sbiz_labels_v2.py
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
V1_PATH = PROCESSED_DATA_DIR / "sbiz_labels.csv"
V2_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v2.csv"

DTYPE = {"상가업소번호": str, "기준분기": str}


def quarter_sort_key(q: str) -> tuple[int, int]:
    year, q_num = q.split("Q")
    return int(year), int(q_num)


def build_v2(all_df: pd.DataFrame) -> pd.DataFrame:
    quarters_sorted = sorted(all_df["기준분기"].unique(), key=quarter_sort_key)
    print(f"  분기 순서: {quarters_sorted[0]} ... {quarters_sorted[-1]} (총 {len(quarters_sorted)}개)")

    hold_out = set(quarters_sorted[-2:])  # 2025Q3, 2025Q4: 판정 보류
    print(f"  판정 보류 분기(T+2 데이터 부족): {sorted(hold_out, key=quarter_sort_key)}")

    next_map = {quarters_sorted[i]: quarters_sorted[i + 1] for i in range(len(quarters_sorted) - 1)}
    next2_map = {quarters_sorted[i]: quarters_sorted[i + 2] for i in range(len(quarters_sorted) - 2)}

    presence_pairs = set(zip(all_df["상가업소번호"], all_df["기준분기"]))

    df = all_df.copy()
    is_closed_v2 = np.full(len(df), np.nan)

    biz_arr = df["상가업소번호"].to_numpy()
    q_arr = df["기준분기"].to_numpy()

    for i in range(len(df)):
        q = q_arr[i]
        if q in hold_out:
            continue  # NaN 유지 (판정 보류)
        biz = biz_arr[i]
        next_q = next_map[q]
        next2_q = next2_map[q]
        absent_next = (biz, next_q) not in presence_pairs
        absent_next2 = (biz, next2_q) not in presence_pairs
        is_closed_v2[i] = 1 if (absent_next and absent_next2) else 0

    df["is_closed_v2"] = is_closed_v2
    return df


def main():
    print(f"입력 로드: {ALL_PATH}")
    all_df = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype=DTYPE)
    print(f"  전체 행 수: {len(all_df):,}")

    print("\nv2 라벨(연속 2분기 부재) 생성 중...")
    v2_df = build_v2(all_df)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    v2_df.to_csv(V2_PATH, index=False, encoding="utf-8-sig")
    labeled_v2 = v2_df["is_closed_v2"].notna().sum()
    print(f"저장 완료: {V2_PATH} (전체 {len(v2_df):,}행, 판정된 라벨 {labeled_v2:,}행)")

    # ================= v1 대비 비교 =================
    print("\n=== v1 vs v2 비교 ===")
    v1_df = pd.read_csv(V1_PATH, encoding="utf-8-sig", dtype=DTYPE)

    v1_closed_total = int(v1_df["is_closed"].sum())
    v2_labeled_df = v2_df.dropna(subset=["is_closed_v2"]).copy()
    v2_closed_total = int(v2_labeled_df["is_closed_v2"].sum())
    decrease = v1_closed_total - v2_closed_total
    decrease_rate = decrease / v1_closed_total * 100

    print(f"\n1) 총 폐업 건수: v1 {v1_closed_total:,}건 -> v2 {v2_closed_total:,}건 "
          f"(감소 {decrease:,}건, {decrease_rate:.1f}% 감소)")

    print("\n2) 연도별 폐업률(%) v1 vs v2")
    v1_df["연도"] = v1_df["기준분기"].str[:4]
    v2_labeled_df["연도"] = v2_labeled_df["기준분기"].str[:4]

    v1_yearly = v1_df.groupby("연도")["is_closed"].agg(["sum", "count"])
    v1_yearly["폐업률(%)"] = (v1_yearly["sum"] / v1_yearly["count"] * 100).round(2)

    v2_yearly = v2_labeled_df.groupby("연도")["is_closed_v2"].agg(["sum", "count"])
    v2_yearly["폐업률(%)"] = (v2_yearly["sum"] / v2_yearly["count"] * 100).round(2)

    years = sorted(set(v1_yearly.index) | set(v2_yearly.index))
    print(f"  {'연도':>6} | {'v1 폐업률':>10} {'(건수/표본)':>14} | {'v2 폐업률':>10} {'(건수/표본)':>14}")
    for y in years:
        v1_row = v1_yearly.loc[y] if y in v1_yearly.index else None
        v2_row = v2_yearly.loc[y] if y in v2_yearly.index else None
        v1_str = f"{v1_row['폐업률(%)']}%" if v1_row is not None else "-"
        v1_cnt = f"({int(v1_row['sum']):,}/{int(v1_row['count']):,})" if v1_row is not None else ""
        v2_str = f"{v2_row['폐업률(%)']}%" if v2_row is not None else "-"
        v2_cnt = f"({int(v2_row['sum']):,}/{int(v2_row['count']):,})" if v2_row is not None else ""
        print(f"  {y:>6} | {v1_str:>10} {v1_cnt:>14} | {v2_str:>10} {v2_cnt:>14}")

    print("\n3) v1=폐업 -> v2=폐업아님 (휴업 추정) 건수")
    merged = v1_df.merge(
        v2_labeled_df[["상가업소번호", "기준분기", "is_closed_v2"]],
        on=["상가업소번호", "기준분기"], how="inner",
    )
    reversed_mask = (merged["is_closed"] == 1) & (merged["is_closed_v2"] == 0)
    reversed_count = int(reversed_mask.sum())
    v1_closed_comparable = int((merged["is_closed"] == 1).sum())
    print(f"  휴업 추정(v1=폐업, v2=폐업아님): {reversed_count:,}건 "
          f"(v1 폐업 중 {reversed_count / v1_closed_comparable * 100:.1f}%, "
          f"비교 가능한 공통 분기 기준)")

    print("\n4) 2022년 폐업률 변화 (원 급감 구간)")
    v1_2022 = v1_yearly.loc["2022"] if "2022" in v1_yearly.index else None
    v2_2022 = v2_yearly.loc["2022"] if "2022" in v2_yearly.index else None
    if v1_2022 is not None:
        print(f"  v1: {v1_2022['폐업률(%)']}% ({int(v1_2022['sum']):,}/{int(v1_2022['count']):,})")
    if v2_2022 is not None:
        print(f"  v2: {v2_2022['폐업률(%)']}% ({int(v2_2022['sum']):,}/{int(v2_2022['count']):,})")


if __name__ == "__main__":
    main()
