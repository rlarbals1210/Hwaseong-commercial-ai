"""
train_table.csv 보강: 읍면동 통계 2종(산업별 사업체수·종사자수 / 세대·등록인구) 결합.

KOSIS 원본은 4행 다중헤더(연도/산업분류/측정단위/성별-구분) 구조라 header=None으로
읽어 수동 파싱한다. 2019~2023 연도별 값만 있고, train_table의 관측분기는
2020Q4~2025Q4까지라 2024~2025는 2023년 값을 carry-forward(플래그로 표시)한다.

주의: "전년대비 증감" feature는 만들지 않음 — carry-forward 구간에서 증감이 0으로
고정돼 왜곡되기 때문(지시사항). 절대 수준과 비율만 사용.

기존 train_table.csv는 보존하고 결과는 train_table_v2.csv로 저장.

사용법:
    python ai/add_kosis_features.py
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
DATASET_DIR = PROJECT_ROOT / "Hwaseong-commercial-ai-main-dataset"

TRAIN_PATH = PROCESSED_DATA_DIR / "train_table.csv"
SBIZ_ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
BIZ_PATH = DATASET_DIR / "kosis_data" / "산업별_읍면동별_사업체수_및_종사자수_20260724063757.csv"
POP_PATH = DATASET_DIR / "kosis_data" / "읍·면·동별_세대_및_등록인구_20260724063340.csv"

OUT_PATH = PROCESSED_DATA_DIR / "train_table_v2.csv"

YEARS_AVAILABLE = ["2019", "2020", "2021", "2022", "2023"]
CARRY_FORWARD_YEARS = ["2024", "2025"]


def to_num(v):
    if pd.isna(v):
        return np.nan
    s = str(v).strip()
    if s in ("-", ""):
        return 0.0
    if s.upper() == "X":
        return np.nan
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


# ==================== 1. 산업별 사업체수·종사자수 ====================

def parse_biz() -> pd.DataFrame:
    print(f"[로드] {BIZ_PATH}")
    raw = pd.read_csv(BIZ_PATH, encoding="cp949", header=None)
    row_year, row_ind, row_meas, row_sub = raw.iloc[0], raw.iloc[1], raw.iloc[2], raw.iloc[3]
    data = raw.iloc[4:].reset_index(drop=True)
    dong_col = data[0]

    industries_wanted = {"합계": "전체", "도매 및 소매업": "도소매", "숙박 및 음식점업": "숙박음식"}

    rows = []
    for j in range(1, raw.shape[1]):
        ind = row_ind[j]
        if ind not in industries_wanted:
            continue
        meas = row_meas[j]
        sub = row_sub[j]
        if meas not in ("사업체수 (개)", "종사자수 (명)"):
            continue
        if sub not in ("소계", "계"):
            continue
        year = row_year[j]
        label = industries_wanted[ind]
        metric = "사업체수" if "사업체수" in meas else "종사자수"
        colname = f"{label}_{metric}"
        for i, dong in enumerate(dong_col):
            if dong == "합계":
                continue
            rows.append((dong, year, colname, to_num(data.iloc[i, j])))

    long_df = pd.DataFrame(rows, columns=["행정동명", "연도", "key", "value"])
    wide = long_df.pivot_table(index=["행정동명", "연도"], columns="key", values="value", aggfunc="first").reset_index()

    wide["전체_사업체당평균종사자수"] = wide["전체_종사자수"] / wide["전체_사업체수"].replace(0, np.nan)
    print(f"  파싱 완료: {wide['행정동명'].nunique()}개 행정동 x {wide['연도'].nunique()}개 연도")
    return wide


# ==================== 2. 세대·등록인구 ====================

def parse_population() -> pd.DataFrame:
    print(f"[로드] {POP_PATH}")
    raw = pd.read_csv(POP_PATH, encoding="cp949", header=None)
    row_year, row_meas, row_sub1, row_sub2 = raw.iloc[0], raw.iloc[1], raw.iloc[2], raw.iloc[3]
    data = raw.iloc[4:].reset_index(drop=True)
    dong_col = data[0]

    wanted = {
        ("세대 수 (세대)", "소계", "소계"): "세대수",
        ("등록인구 (명)", "합계", "소계"): "등록인구",
        ("등록인구 (명)", "외국인", "소계"): "외국인수",
        ("세대당인구 (명)", "소계", "소계"): "세대당인구",
        ("65세 이상 고령자 (명)", "소계", "소계"): "고령인구",
    }

    rows = []
    for j in range(1, raw.shape[1]):
        key = (row_meas[j], row_sub1[j], row_sub2[j])
        if key not in wanted:
            continue
        colname = wanted[key]
        year = row_year[j]
        for i, dong in enumerate(dong_col):
            if dong == "합계":
                continue
            rows.append((dong, year, colname, to_num(data.iloc[i, j])))

    long_df = pd.DataFrame(rows, columns=["행정동명", "연도", "key", "value"])
    wide = long_df.pivot_table(index=["행정동명", "연도"], columns="key", values="value", aggfunc="first").reset_index()

    wide["외국인비율"] = wide["외국인수"] / wide["등록인구"].replace(0, np.nan)
    wide["고령비율_kosis"] = wide["고령인구"] / wide["등록인구"].replace(0, np.nan)
    print(f"  파싱 완료: {wide['행정동명'].nunique()}개 행정동 x {wide['연도'].nunique()}개 연도")
    return wide


# ==================== 3. carry-forward 확장 ====================

def expand_with_carry_forward(wide: pd.DataFrame) -> pd.DataFrame:
    base_2023 = wide[wide["연도"] == "2023"].copy()
    frames = [wide.assign(carry_forward=0)]
    for y in CARRY_FORWARD_YEARS:
        cf = base_2023.copy()
        cf["연도"] = y
        cf["carry_forward"] = 1
        frames.append(cf)
    return pd.concat(frames, ignore_index=True)


# ==================== 검증 ====================

def check_dong_matching(biz: pd.DataFrame, pop: pd.DataFrame, train_dongs: set):
    print("\n" + "=" * 70)
    print("[검증] 행정동 매칭 확인")
    print("=" * 70)
    biz_dongs = set(biz["행정동명"].unique())
    pop_dongs = set(pop["행정동명"].unique())
    print(f"사업체 파일 행정동 수: {len(biz_dongs)}")
    print(f"인구 파일 행정동 수: {len(pop_dongs)}")
    print(f"train_table 행정동 수: {len(train_dongs)}")

    missing_in_biz = train_dongs - biz_dongs
    missing_in_pop = train_dongs - pop_dongs
    print(f"\ntrain_table에는 있는데 사업체파일에 없는 행정동: {missing_in_biz if missing_in_biz else '없음(29개 전부 매칭)'}")
    print(f"train_table에는 있는데 인구파일에 없는 행정동: {missing_in_pop if missing_in_pop else '없음(29개 전부 매칭)'}")


def compare_store_counts(sbiz_all: pd.DataFrame, biz: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[검증] 소진공 점포수 vs 통계청 사업체수 비교 (연도말 분기 기준)")
    print("=" * 70)
    sbiz_all = sbiz_all.copy()
    sbiz_all["연도"] = sbiz_all["기준분기"].str[:4]
    sbiz_all["분기"] = sbiz_all["기준분기"].str[-2:]
    year_end = sbiz_all[sbiz_all["분기"] == "Q4"]
    sbiz_cnt = year_end.groupby(["행정동명", "연도"])["상가업소번호"].nunique().rename("소진공_점포수").reset_index()

    merged = sbiz_cnt.merge(biz[["행정동명", "연도", "전체_사업체수"]], on=["행정동명", "연도"], how="inner")
    merged["소진공_통계청_비율"] = merged["소진공_점포수"] / merged["전체_사업체수"].replace(0, np.nan)

    dong_total = merged.groupby("연도")[["소진공_점포수", "전체_사업체수"]].sum()
    dong_total["비율"] = dong_total["소진공_점포수"] / dong_total["전체_사업체수"]
    print("\n화성시 전체 합계(연도별, Q4 시점):")
    print(dong_total.round(3).to_string())

    print("\n행정동별 비율 분포(2023년 기준):")
    y2023 = merged[merged["연도"] == "2023"].sort_values("소진공_통계청_비율", ascending=False)
    print(y2023[["행정동명", "소진공_점포수", "전체_사업체수", "소진공_통계청_비율"]].round(3).to_string(index=False))


def main():
    biz = parse_biz()
    pop = parse_population()

    biz_ext = expand_with_carry_forward(biz)
    pop_ext = expand_with_carry_forward(pop)

    print(f"\n[로드] {TRAIN_PATH}")
    train = pd.read_csv(TRAIN_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "B": str})
    print(f"  train_table 행 수: {len(train):,}")

    train_dongs = set(train["행정동명"].unique())
    check_dong_matching(biz, pop, train_dongs)

    print(f"\n[로드] {SBIZ_ALL_PATH} (교차검증용)")
    sbiz_all = pd.read_csv(SBIZ_ALL_PATH, encoding="utf-8-sig", dtype={"상가업소번호": str, "행정동명": str, "기준분기": str})
    compare_store_counts(sbiz_all, biz)

    train["_연도"] = train["B"].str[:4]

    biz_cols = [c for c in biz_ext.columns if c not in ("행정동명", "연도", "carry_forward")]
    pop_cols = [c for c in pop_ext.columns if c not in ("행정동명", "연도", "carry_forward")]

    train = train.merge(
        biz_ext.rename(columns={"carry_forward": "사업체통계_carry_forward"}),
        left_on=["행정동명", "_연도"], right_on=["행정동명", "연도"], how="left"
    ).drop(columns=["연도"])
    # train_table.csv에 이미 동명의 '세대당인구'(전부 NaN 플레이스홀더, 원본에 세대수 컬럼이
    # 없어 산출 불가했던 것)가 있어 그대로 merge하면 _x/_y로 충돌함 — 옛 플레이스홀더 제거.
    if "세대당인구" in train.columns:
        train = train.drop(columns=["세대당인구"])

    train = train.merge(
        pop_ext.rename(columns={"carry_forward": "인구통계_carry_forward"}),
        left_on=["행정동명", "_연도"], right_on=["행정동명", "연도"], how="left"
    ).drop(columns=["연도"])
    train = train.drop(columns=["_연도"])

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    train.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUT_PATH} ({len(train):,}행, {len(train.columns)}컬럼)")

    new_cols = biz_cols + pop_cols + ["사업체통계_carry_forward", "인구통계_carry_forward"]
    print("\n" + "=" * 70)
    print("[검증] 추가된 feature 목록 및 결측률")
    print("=" * 70)
    miss = train[new_cols].isna().mean().sort_values(ascending=False) * 100
    print(miss.round(2).to_string())


if __name__ == "__main__":
    main()
