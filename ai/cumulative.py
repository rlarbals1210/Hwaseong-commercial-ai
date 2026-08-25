"""4분기 누적 지표와 등급 기준선 — build_risk_index.py와 import_normalized_db.py의 공용 모듈.

두 스크립트가 각자 등급을 계산하고 있었다. build_risk_index는 risk_index.csv(레거시 테이블용)를,
import_normalized_db는 정규화 DB의 commercial_quarters.risk_grade를 만드는데, 로직이 따로
살아 있으면 한쪽만 고쳤을 때 화면과 CSV가 다른 등급을 보여준다. 실제로 2026-08-20에
build_risk_index만 4분기 누적으로 바꿨더니 화면은 그대로 단일 분기 등급이었다.

risk_index.csv는 .gitignore 대상이라 import_normalized_db가 그 파일을 읽게 만들 수는 없다
(팀원이 pull만 받아서는 파일이 없다). 그래서 파일 의존 대신 이 모듈을 공유한다.

────────────────────────────────────────────────────────────────────────────
왜 4분기 누적인가 (2026-08-20 검증)

  분기 간 순위 상관    단일 분기 +0.296  ->  4분기 누적 +0.857
  Top10 유지          단일 분기 1.0개   ->  4분기 누적 5.4개

"신호가 느려지는 것 아니냐"는 실측으로 반박됐다. 과거 N분기로 미래 폐업률을 예측할 때
상관이 1분기 +0.319 / 4분기 +0.345 / 8분기 +0.501로, 긴 창이 오히려 미래를 더 잘 맞힌다.
급변은 대부분 평균으로 회귀한다(급등 셀 3.0% -> 9.7% -> 5.5%, 변화의 미래 설명력 p=0.11).
이 데이터에서 폐업은 급성이 아니라 만성이다.

왜 분위수 기준인가

  분기 시평균 x 2      기준선 6.88~14.38%   위험 셀  5~17개
  고정 임계값 8.31%     기준선 고정          위험 셀  2~85개   <- 42배 요동
  상위 10% 분위수       기준선 6.27~12.03%   위험 셀 22~26개   <- 채택

2025년 폐업 급증이 데이터 결함인지 판정 불가한 상태다(이탈이 평시의 1.85배인데,
과거 같은 패턴 2건은 3~4분기 뒤 재등장으로 결함이 확인됐고 2025년분은 관측 기간이 부족하다).
고정 기준을 쓰면 그 미확인 급증이 그대로 "위험 셀 85개"라는 정책 판단이 된다.
분위수 기준은 모든 셀이 같이 움직이면 상대 위치가 보존되므로 그 오염에 면역이다.

주의: 등급은 절대 임계가 아니라 화성시 내 상대 순위다. 화면에 반드시 명시할 것.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 누적 창 길이(분기). 4 = 최근 1년.
# 8분기가 미래 적중은 더 높았으나(+0.501 vs +0.345) 2년 전 실적으로 현재 예산을 짜는 셈이 되고
# 신규 상권이 통째로 빠진다. 정책 주기(반기~1년)와도 4분기가 맞는다.
WINDOW = 4

# 등급 분위수. 위험 = 상위 10%, 주의 = 상위 30%.
DANGER_Q = 0.90
CAUTION_Q = 0.70

# 신뢰하한 z (1.96 = 95% 신뢰구간 하한)
WILSON_Z = 1.96

KEY = ["행정동명", "통합카테고리"]


def wilson_lower(successes, trials, z: float = WILSON_Z):
    """이항 비율의 Wilson 신뢰구간 하한.

    "운이 나빴을 가능성을 빼면 최소 이만큼은 진짜"에 해당한다. 표본이 작을수록 많이 깎이므로
    점포 50곳에서 5곳이 닫힌 것(10% -> 4.35%)과 1000곳에서 100곳(10% -> 8.29%)을 구분한다.
    정렬·순위에만 쓰고 등급 판정에는 쓰지 않는다 — 등급은 관측 사실이어야 감사에 방어된다.
    """
    trials = np.asarray(trials, dtype=float)
    successes = np.asarray(successes, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.divide(successes, trials, out=np.zeros_like(trials), where=trials > 0)
        centre = (p + z * z / (2 * trials)) / (1 + z * z / trials)
        margin = z / (1 + z * z / trials) * np.sqrt(
            p * (1 - p) / trials + z * z / (4 * trials * trials)
        )
        lower = centre - margin
    return np.where(trials > 0, np.maximum(lower, 0.0), np.nan)


def add_cumulative(df: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """final_dataset 형태의 프레임에 셀×분기별 누적 지표를 붙인다.

    비율의 평균이 아니라 건수합/분모합으로 낸다. 분기마다 점포수가 다르므로
    비율을 그냥 평균내면 점포가 적은 분기가 과대 반영된다.

    분모는 "직전 분기 점포수"다 — build_dataset.py의 trailing stats가
    폐업_률_평균 = (직전분기 - 현재분기 차집합) / 직전분기 점포수로 정의돼 있다.

    추가 컬럼: 누적폐업건수 / 누적분모 / 누적폐업률_pct / 위험도_하한_pct
    """
    required = {"행정동명", "통합카테고리", "기준_년분기_코드", "점포수", "폐업_률_평균"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"누적 지표 계산에 필요한 컬럼이 없습니다: {missing}")

    df = df.sort_values(KEY + ["기준_년분기_코드"]).copy()
    grouped = df.groupby(KEY, sort=False)
    prev_stores = grouped["점포수"].shift(1)
    closures = df["폐업_률_평균"] * prev_stores

    df["_직전점포수"] = prev_stores
    df["_폐업건수"] = closures
    grouped = df.groupby(KEY, sort=False)
    cum_closures = grouped["_폐업건수"].transform(
        lambda s: s.rolling(window, min_periods=window).sum()
    )
    cum_base = grouped["_직전점포수"].transform(
        lambda s: s.rolling(window, min_periods=window).sum()
    )

    df["누적폐업건수"] = cum_closures.round()
    df["누적분모"] = cum_base
    df["누적폐업률_pct"] = (cum_closures / cum_base * 100).round(2)
    df["위험도_하한_pct"] = (wilson_lower(cum_closures, cum_base) * 100).round(2)
    df.loc[cum_base.isna(), ["누적폐업률_pct", "위험도_하한_pct", "누적폐업건수"]] = np.nan
    return df.drop(columns=["_직전점포수", "_폐업건수"])


def compute_thresholds(
    latest_cells: pd.DataFrame,
    sample_min: int,
    danger_q: float = DANGER_Q,
    caution_q: float = CAUTION_Q,
) -> dict:
    """표본충분 셀 집합의 분위수로 등급 기준선을 낸다. 하드코딩 금지."""
    eligible = latest_cells[
        (latest_cells["점포수"] >= sample_min) & latest_cells["누적폐업률_pct"].notna()
    ]
    if len(eligible) < 30:
        raise ValueError(
            f"표본충분 셀이 {len(eligible)}개뿐이라 분위수 기준선을 낼 수 없습니다. "
            f"{WINDOW}분기 누적을 낼 만큼 분기가 쌓였는지 확인하세요."
        )
    return {
        "danger_pct": round(float(eligible["누적폐업률_pct"].quantile(danger_q)), 2),
        "caution_pct": round(float(eligible["누적폐업률_pct"].quantile(caution_q)), 2),
        "avg_pct": round(float(eligible["누적폐업률_pct"].mean()), 2),
        "eligible_cells": int(len(eligible)),
    }


def grade(value, sample_ok: bool, danger_pct: float, caution_pct: float) -> str:
    """누적 폐업률 기준 등급. 예측값이 아닌 실측치로만 판정한다."""
    if not sample_ok or value is None or pd.isna(value):
        return "표본부족"
    if value >= danger_pct:
        return "위험"
    if value >= caution_pct:
        return "주의"
    return "안정"


# ────────────────────────────────────────────────────────────────────────────
# 상권 유형 4분류 (2026-08-20)
#
# 지금까지는 위험도 한 축뿐이라 어느 셀이든 결론이 "현장 확인" 하나였다.
# 개업률 축을 얹으면 같은 "위험"이라도 처방이 갈린다.
#
#   고회전  폐업↑ 개업↑   나가는 만큼 들어옴. 상권 자체는 살아있음
#   쇠퇴    폐업↑ 개업↓   나가고 안 들어옴. 진짜 위험
#   성장    폐업↓ 개업↑   건강하게 커지는 중
#   정체    폐업↓ 개업↓   물갈이 자체가 없음
#
# 기준은 각 분기 표본충분 셀의 중위값이다. 고정 임계값(시평균 3.22%)을 쓰면
# 성장 유형이 4셀로 붕괴해 4분면이 성립하지 않는다(실측: 106/76/4/45).
# 중위값 기준은 33/18/18/32로 갈린다.
#
# 개업률은 반드시 보정 4분기 이동평균(개업_율_보정_ma4)을 쓴다. 단일 분기는 셀의 25%가
# 개업률 0이라 분류가 무의미하고, 원본 개업률은 2024Q3/Q4 수록 지연 결함이 그대로 들어온다.
# 최근 분기는 보정 개업률이 구조적으로 과소 추정되지만, 중위값 상대 분류라 모든 셀이 같이
# 내려가면 상대 위치가 보존되므로 분류에는 영향이 없다(실측으로 확인).
#
# 검증: 고회전 비중이 동탄7동 70% / 동탄4동 67% / 동탄9동 60%로 신흥개발지에 몰리고,
# 서신면·우정읍·팔탄면은 0%다. 기존에 확인한 "최근 개발지 vs 성숙 상권" 구도와 일치한다.
# 유형별 실제 폐업률도 고회전 4.6% / 쇠퇴 4.1% / 성장 2.9% / 정체 2.0%로 논리가 맞는다.

OPENING_COLUMN = "개업_율_보정_ma4"

CELL_TYPES = {
    "고회전": {
        "summary": "나가는 만큼 새로 들어오는 상권입니다.",
        "advice": "개별 점포 지원의 효과가 상권 단위에서는 상쇄될 수 있어, "
                  "창업 사전상담과 업종 과밀 관리를 먼저 검토하시길 권장합니다.",
        "avoid": "개별 점포 자금 지원",
    },
    "쇠퇴": {
        "summary": "나간 자리가 채워지지 않고 있습니다.",
        "advice": "상권 활성화 사업과 시설·환경 개선을 우선 검토하시길 권장합니다.",
        "avoid": "창업 유도",
    },
    "성장": {
        "summary": "새로 들어오는 곳이 나가는 곳보다 많습니다.",
        "advice": "당장의 개입보다 과열 조짐 관찰을 권장합니다.",
        "avoid": "선제 개입",
    },
    "정체": {
        "summary": "드나듦이 모두 적어 세대교체가 일어나지 않고 있습니다.",
        "advice": "신규 유입 유도를 검토하시길 권장합니다.",
        "avoid": "위험으로 단정",
    },
    "유형판정보류": {
        "summary": "유형을 판정할 자료가 부족합니다.",
        "advice": "누적 개업·폐업률이 산출되지 않았습니다. 현장 확인을 권장합니다.",
        "avoid": "",
    },
}


def add_cell_type(latest_cells: pd.DataFrame, sample_min: int) -> pd.DataFrame:
    """최신 분기 셀에 상권 유형과 판정 기준을 붙인다.

    add_cumulative()를 먼저 돌려 누적폐업률_pct가 있어야 한다.
    """
    df = latest_cells.copy()
    if OPENING_COLUMN not in df.columns:
        raise ValueError(
            f"{OPENING_COLUMN}가 없습니다. ai/fix_opening_rate.py를 먼저 실행하세요 "
            "(docs/datasetting.md 3절)."
        )

    eligible = df[
        (df["점포수"] >= sample_min)
        & df["누적폐업률_pct"].notna()
        & df[OPENING_COLUMN].notna()
    ]
    if len(eligible) < 30:
        df["상권유형"] = "유형판정보류"
        df["유형_개업기준"] = np.nan
        df["유형_폐업기준"] = np.nan
        return df

    open_cut = float(eligible[OPENING_COLUMN].median())
    close_cut = float(eligible["누적폐업률_pct"].median())

    high_open = df[OPENING_COLUMN] >= open_cut
    high_close = df["누적폐업률_pct"] >= close_cut
    judged = df["누적폐업률_pct"].notna() & df[OPENING_COLUMN].notna() & (df["점포수"] >= sample_min)

    df["상권유형"] = "유형판정보류"
    df.loc[judged & high_close & high_open, "상권유형"] = "고회전"
    df.loc[judged & high_close & ~high_open, "상권유형"] = "쇠퇴"
    df.loc[judged & ~high_close & high_open, "상권유형"] = "성장"
    df.loc[judged & ~high_close & ~high_open, "상권유형"] = "정체"
    df["유형_개업기준"] = round(open_cut * 100, 2)
    df["유형_폐업기준"] = round(close_cut, 2)
    return df
