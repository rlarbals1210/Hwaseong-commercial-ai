"""
2022Q4 -> 2023Q1 화성시 상가 수 급감(41,660 -> 33,108, -8,552)이
실제 폐업인지 상가업소번호 재채번(원본 구조 변경) 때문인지 검증하는 1회성 분석 스크립트.

사용법:
    python ai/verify_2022q4_2023q1_gap.py
"""
import glob
import io
import zipfile
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = Path(glob.glob(str(PROJECT_ROOT / "**" / "소상공인시장진흥공단_상가*"), recursive=True)[0])

USECOLS = ["상가업소번호", "시군구명", "상호명", "지번주소"]
DTYPE = {c: str for c in USECOLS}


def find_gg_entry(namelist):
    return next(n for n in namelist if "경기" in n and n.endswith(".csv"))


def load_quarter(zip_name: str) -> pd.DataFrame:
    path = DATASET_DIR / zip_name
    with zipfile.ZipFile(path, metadata_encoding="cp949") as outer:
        nested = [n for n in outer.namelist() if n.endswith(".zip")]
        if nested:
            with zipfile.ZipFile(io.BytesIO(outer.read(nested[0])), metadata_encoding="cp949") as inner:
                name = find_gg_entry(inner.namelist())
                with inner.open(name) as f:
                    df = pd.read_csv(f, encoding="utf-8-sig", usecols=USECOLS, dtype=DTYPE, low_memory=False)
        else:
            name = find_gg_entry(outer.namelist())
            with outer.open(name) as f:
                df = pd.read_csv(f, encoding="utf-8-sig", usecols=USECOLS, dtype=DTYPE, low_memory=False)
    return df[df["시군구명"] == "화성시"].copy()


def normalize(s: str) -> str:
    if pd.isna(s):
        return ""
    return "".join(str(s).split())  # 공백 전부 제거 (띄어쓰기 표기 차이 흡수)


def main():
    print("2022Q4, 2023Q1 원본 로드 중...")
    q4 = load_quarter("소상공인시장진흥공단_상가(상권)정보_20221231.zip")
    q1 = load_quarter("소상공인시장진흥공단_상가(상권)정보_20230331.zip")
    print(f"  2022Q4 화성시: {len(q4):,}건 / 2023Q1 화성시: {len(q1):,}건")

    # 1) 상가업소번호 형식 비교
    print("\n=== 1. 상가업소번호 형식 비교 ===")
    len_q4 = q4["상가업소번호"].str.len().value_counts().to_dict()
    len_q1 = q1["상가업소번호"].str.len().value_counts().to_dict()
    print(f"  2022Q4 번호 길이 분포: {len_q4}")
    print(f"  2023Q1 번호 길이 분포: {len_q1}")
    print(f"  2022Q4 샘플: {q4['상가업소번호'].head(3).tolist()}")
    print(f"  2023Q1 샘플: {q1['상가업소번호'].head(3).tolist()}")

    prefix_len = 4
    pre_q4 = q4["상가업소번호"].str[:prefix_len].value_counts().head(5).to_dict()
    pre_q1 = q1["상가업소번호"].str[:prefix_len].value_counts().head(5).to_dict()
    print(f"  2022Q4 앞 {prefix_len}자리 최빈값: {pre_q4}")
    print(f"  2023Q1 앞 {prefix_len}자리 최빈값: {pre_q1}")

    set_q4 = set(q4["상가업소번호"])
    set_q1 = set(q1["상가업소번호"])
    retained_by_number = set_q4 & set_q1
    print(f"\n  2022Q4 번호 중 2023Q1에 그대로 남은 수: {len(retained_by_number):,} "
          f"({len(retained_by_number) / len(set_q4) * 100:.1f}%)")

    missing_by_number = set_q4 - set_q1
    print(f"  번호 기준 '사라진' 상가: {len(missing_by_number):,}건")

    # 2) 상호명+지번주소 키로 재매칭
    print("\n=== 2. 상호명+지번주소 키로 재매칭 ===")
    q4["_key"] = q4["상호명"].map(normalize) + "|" + q4["지번주소"].map(normalize)
    q1["_key"] = q1["상호명"].map(normalize) + "|" + q1["지번주소"].map(normalize)

    key_to_number_q1 = q1.groupby("_key")["상가업소번호"].apply(set).to_dict()

    missing_df = q4[q4["상가업소번호"].isin(missing_by_number)].copy()
    keys_q1 = set(q1["_key"])

    found_by_key = 0
    same_number_but_found = 0
    for _, row in missing_df.iterrows():
        if row["_key"] in keys_q1:
            found_by_key += 1

    print(f"  번호로는 사라졌지만 상호명+주소로는 2023Q1에 존재: {found_by_key:,}건 "
          f"({found_by_key / len(missing_df) * 100:.1f}% of 사라진 {len(missing_df):,}건)")
    still_missing = len(missing_df) - found_by_key
    print(f"  상호명+주소로도 못 찾음(실제 폐업 후보): {still_missing:,}건 "
          f"({still_missing / len(missing_df) * 100:.1f}%)")

    # 3) 판정
    print("\n=== 3. 판정 ===")
    recovery_rate = found_by_key / len(missing_df) * 100
    if recovery_rate >= 50:
        verdict = "번호 재채번(가짜 폐업) 가능성 높음"
    else:
        verdict = "실제 폐업 가능성 높음"
    print(f"  상호명+주소 재매칭 회복률: {recovery_rate:.1f}% -> {verdict}")


if __name__ == "__main__":
    main()
