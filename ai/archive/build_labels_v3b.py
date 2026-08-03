"""
라벨 v3b: v3("데이터 끝까지 미재등장=폐업")의 최근분기 과대계상 편향을 보정.
고정 확인창 K=4분기: T 이후 4개 분기(T+1~T+4) 동안 한 번도 안 나타나면 폐업.
K창을 확보 못하는 마지막 4개 분기는 판정 보류.

sbiz_panel_filled.csv(갭필링된 패널, 임계값 8분기)를 그대로 재사용 — v3와 동일한
"진짜 존재" 기준 위에서, 확인 윈도우 길이만 가변(끝까지) -> 고정(4분기)으로 바꾼 것.
label_h1(1분기 선행판, next-quarter 부재)도 v3/v3b 둘 다 새로 계산해서 붙임(원래 없었음).

사용법:
    python ai/build_labels_v3b.py
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

PANEL_FILLED_PATH = PROCESSED_DATA_DIR / "sbiz_panel_filled.csv"
LABELS_V3_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v3.csv"
TRAIN_V3_PATH = PROCESSED_DATA_DIR / "train_table_v3.csv"

LABELS_V3B_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v3b.csv"
TRAIN_V3B_PATH = PROCESSED_DATA_DIR / "train_table_v3b.csv"

K = 4


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def main():
    print(f"[로드] {PANEL_FILLED_PATH}")
    panel = pd.read_csv(PANEL_FILLED_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str,
        "상권업종대분류명": str, "상권업종중분류명": str, "상권업종소분류명": str,
        "지번주소": str, "기준분기": str,
    })

    quarters = sorted(panel["기준분기"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}
    n_q = len(quarters)
    print(f"분기 수: {n_q} ({quarters[0]}~{quarters[-1]})")

    presence_pairs = set(zip(panel["상가업소번호"], panel["기준분기"]))

    panel["idx"] = panel["기준분기"].map(q_idx)

    # ---------------- label_h1 (1분기 선행, next-quarter 부재) ----------------
    def label_h1_of(row):
        nxt = row["idx"] + 1
        if nxt >= n_q:
            return np.nan
        return 0 if (row["상가업소번호"], quarters[nxt]) in presence_pairs else 1

    print("\nlabel_h1 계산 중...")
    panel["label_h1"] = panel.apply(label_h1_of, axis=1)

    # ---------------- label_h2_v3b (고정 K=4분기 확인창) ----------------
    print(f"label_h2_v3b 계산 중 (K={K}분기 고정 확인창)...")

    def label_v3b_of(row):
        start = row["idx"] + 1
        end = row["idx"] + K  # inclusive
        if end >= n_q:
            return np.nan  # K창 확보 불가 -> 판정 보류
        for i in range(start, end + 1):
            if (row["상가업소번호"], quarters[i]) in presence_pairs:
                return 0  # K분기 내 재등장 -> 폐업 아님
        return 1  # K분기 연속 미등장 -> 폐업

    panel["is_closed_v3b"] = panel.apply(label_v3b_of, axis=1)
    panel = panel.drop(columns=["idx"])

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_csv(LABELS_V3B_PATH, index=False, encoding="utf-8-sig")
    labeled = panel.dropna(subset=["is_closed_v3b"])
    print(f"\n저장 완료: {LABELS_V3B_PATH} ({len(panel):,}행, 판정 {len(labeled):,}행)")
    print(f"v3b 총 폐업 건수: {int(labeled['is_closed_v3b'].sum()):,}")

    hold_out = quarters[-K:]
    print(f"판정 보류 분기(K창 확보 불가): {hold_out}")

    # ---------------- v2/v3/v3b 연도별 폐업률 비교 ----------------
    print("\n" + "=" * 70)
    print("[비교] v2 vs v3 vs v3b 연도별 폐업률(%)")
    print("=" * 70)

    v2 = pd.read_csv(PROCESSED_DATA_DIR / "sbiz_labels_v2.csv", encoding="utf-8-sig", dtype={"기준분기": str})
    v3 = pd.read_csv(LABELS_V3_PATH, encoding="utf-8-sig", dtype={"기준분기": str})

    v2_l = v2.dropna(subset=["is_closed_v2"]).copy()
    v2_l["연도"] = v2_l["기준분기"].str[:4]
    v3_l = v3.dropna(subset=["is_closed_v3"]).copy()
    v3_l["연도"] = v3_l["기준분기"].str[:4]
    v3b_l = labeled.copy()
    v3b_l["연도"] = v3b_l["기준분기"].str[:4]

    comp = pd.concat([
        (v2_l.groupby("연도")["is_closed_v2"].mean() * 100).rename("v2"),
        (v3_l.groupby("연도")["is_closed_v3"].mean() * 100).rename("v3"),
        (v3b_l.groupby("연도")["is_closed_v3b"].mean() * 100).rename("v3b"),
    ], axis=1)
    print(comp.round(2).to_string())
    print(f"\n총 폐업 건수: v2={int(v2_l['is_closed_v2'].sum()):,} / v3={int(v3_l['is_closed_v3'].sum()):,} "
          f"/ v3b={int(labeled['is_closed_v3b'].sum()):,}")

    # ---------------- train_table_v3b.csv (v3와 동일 feature, 라벨만 v3b) ----------------
    print(f"\n[로드] {TRAIN_V3_PATH} (feature 재사용)")
    train_v3 = pd.read_csv(TRAIN_V3_PATH, encoding="utf-8-sig", dtype={
        "행정동코드": str, "B": str, "상가업소번호": str,
    })
    train_v3 = train_v3.drop(columns=["label_h2_v3"])

    lv3b = panel[["상가업소번호", "기준분기", "is_closed_v3b", "label_h1"]].rename(
        columns={"기준분기": "B", "is_closed_v3b": "label_h2_v3b", "label_h1": "label_h1_v3b"})
    train_v3b = train_v3.merge(lv3b, on=["상가업소번호", "B"], how="left")

    train_v3b.to_csv(TRAIN_V3B_PATH, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {TRAIN_V3B_PATH} ({len(train_v3b):,}행, {len(train_v3b.columns)}컬럼)")

    # v3에도 label_h1_v3 뒤늦게 붙여줌 (원래 h2만 있었음)
    lv3_h1 = panel[["상가업소번호", "기준분기", "label_h1"]].rename(
        columns={"기준분기": "B", "label_h1": "label_h1_v3"})
    train_v3_full = pd.read_csv(TRAIN_V3_PATH, encoding="utf-8-sig", dtype={
        "행정동코드": str, "B": str, "상가업소번호": str,
    })
    if "label_h1_v3" not in train_v3_full.columns:
        train_v3_full = train_v3_full.merge(lv3_h1, on=["상가업소번호", "B"], how="left")
        train_v3_full.to_csv(TRAIN_V3_PATH, index=False, encoding="utf-8-sig")
        print(f"\n{TRAIN_V3_PATH}에 label_h1_v3 컬럼 추가 저장 완료")


if __name__ == "__main__":
    main()
