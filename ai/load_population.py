"""읍면동 배후인구(KOSIS 등록인구) 분기 시계열을 DB에 적재한다.

사용법:
    alembic upgrade head
    python ai/load_population.py

무엇에 쓰는가 —
등급·상권유형 판정에는 관여하지 않는다. 셀 상세에서 "같은 위험 등급이라도 원인 방향이
다르다"를 보이는 설명 근거다. 인구증감과 폐업률의 순위상관은 +0.238로 약하고 부호도
직관과 반대라(정남면 인구 -9.8%인데 폐업률 0.04, 봉담읍 +25.9%인데 0.05) 판정 축으로
쓸 근거가 없다.

원천 파일의 두 가지 함정 —

① 같은 읍면동이 두 번 나온다.
   2026년 화성시에 구(만세구·효행구·병점구·동탄구)가 생기면서 KOSIS 표가 두 블록으로
   갈렸다. 구 아래 블록은 2026.03부터만, 구 없는 평면 블록은 2025.12까지만 값이 있다.
   중복이 아니라 **상호 보완**이므로 이름 기준으로 합쳐야 전 구간이 나온다.
   (실측: 봉담읍 평면 블록 2020.12~2025.12, 구 블록 2026.03~2026.06)

② 결측을 0으로 채우면 안 된다.
   동탄9동은 2023.09부터 값이 있다. 그 전은 인구가 0명이었던 게 아니라 동이 없었다.
   0으로 채우면 화면에 "인구 폭증"으로 그려진다 — 개업률에서 이미 겪은 결함이다.
   여기서는 해당 분기 행 자체를 넣지 않는다.

컬럼 헤더는 "2020.12 월" 형태의 분기말 월이다. 03->Q1 06->Q2 09->Q3 12->Q4로 옮긴다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "ai"))

from backend.database import engine  # noqa: E402
from backend.models import AdminArea, AreaPopulationQuarter  # noqa: E402
from eda import paths as eda_paths  # noqa: E402
from import_normalized_db import _upsert  # noqa: E402

# 구는 읍면동의 상위 단위라 셀(행정동x업종)과 붙지 않는다. 합산 중복을 막으려고 제외한다.
GU_NAMES = {"만세구", "효행구", "병점구", "동탄구"}
CITY_NAME = "화성시"

MONTH_TO_QUARTER = {3: 1, 6: 2, 9: 3, 12: 4}
SOURCE = "kosis_registered"


def quarter_code_from_header(header: str) -> int | None:
    """'2020.12 월' -> 20204. 형식이 다르면 None."""
    m = re.match(r"\s*(\d{4})\.(\d{2})", str(header))
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    quarter = MONTH_TO_QUARTER.get(month)
    return year * 10 + quarter if quarter else None


def read_population_series() -> pd.DataFrame:
    """읍면동 x 분기코드 총인구 표를 만든다. 값이 없는 칸은 NaN으로 남긴다."""
    df = pd.read_csv(eda_paths.POP_TREND_CSV, encoding="cp949")
    name_col, age_col, item_col = df.columns[0], df.columns[1], df.columns[2]

    quarter_cols = {c: quarter_code_from_header(c) for c in df.columns}
    quarter_cols = {c: q for c, q in quarter_cols.items() if q is not None}
    if not quarter_cols:
        raise SystemExit("분기 컬럼을 찾지 못했습니다. 원천 파일 헤더 형식을 확인하세요.")

    total = df[
        (df[age_col].astype(str).str.strip() == "계")
        & (df[item_col].astype(str).str.strip() == "총인구수[명]")
    ].copy()
    total["_name"] = total[name_col].astype(str).str.strip()
    total = total[~total["_name"].isin(GU_NAMES) & (total["_name"] != CITY_NAME)]

    # groupby.first()는 NaN을 건너뛴다 — 이것이 두 블록을 합치는 지점이다(위 주석 ①).
    merged = total.groupby("_name")[list(quarter_cols)].first()
    merged.columns = [quarter_cols[c] for c in merged.columns]
    return merged.sort_index(axis=1)


def main() -> None:
    series = read_population_series()
    print(f"원천 읍면동 {len(series)}개 · 분기 {len(series.columns)}개")

    with Session(engine) as session:
        # admin_areas에는 읍/면/동만 있다(구는 넣지 않았다). is_current로 과거 행정구역 행을 배제한다.
        areas = {
            a.area_name: a.id
            for a in session.query(AdminArea).filter(AdminArea.is_current.is_(True)).all()
        }

        rows: list[dict] = []
        matched, missing = [], []
        for name, values in series.iterrows():
            area_id = areas.get(name)
            if area_id is None:
                missing.append(name)
                continue
            matched.append(name)
            for quarter_code, value in values.items():
                if pd.isna(value):
                    continue  # 위 주석 ② — 0으로 채우지 않는다
                rows.append({
                    "area_id": area_id,
                    "quarter_code": int(quarter_code),
                    "total_population": int(value),
                    "source": SOURCE,
                })

        if missing:
            print(f"[경고] admin_areas에 없는 읍면동 {len(missing)}개: {', '.join(missing)}")
        unmatched_db = sorted(set(areas) - set(matched))
        if unmatched_db:
            print(f"[경고] 인구 자료가 없는 DB 읍면동 {len(unmatched_db)}개: {', '.join(unmatched_db)}")

        _upsert(
            session,
            AreaPopulationQuarter,
            rows,
            key_columns=["area_id", "quarter_code"],
            update_columns=["total_population", "source"],
        )
        session.commit()

    expected = int(series.loc[matched].notna().sum().sum()) if matched else 0
    print(f"적재 {len(rows)}행 (읍면동 {len(matched)}개) · 매칭된 원천 유효칸 {expected}개")
    if len(rows) != expected:
        print("[경고] 적재 행수가 원천 유효칸과 맞지 않습니다.")
    blank = int(series.loc[matched].isna().sum().sum()) if matched else 0
    if blank:
        print(f"자료 없는 칸 {blank}개는 넣지 않았습니다(0이 아니라 미산출).")


if __name__ == "__main__":
    main()
