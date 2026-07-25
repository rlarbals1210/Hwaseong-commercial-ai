"""
업종코드 체계 분석 및 매핑(안) 제안 — 확정 아님, 사람 검토용 초안 생성.

배경: 폐업 예측 feature를 만들려면 소진공 상가정보(자체 상권업종 대/중/소분류)와
카드매출(MDCLASS_INDUTYPE_CD, 알파벳+숫자 코드)을 공통 업종 기준으로 조인해야 하는데
두 체계가 서로 다르다. 이 스크립트는 매핑을 "확정"하지 않고 분석 결과 + 후보표만
제안한다 — 임의 추측을 코드에 하드코딩하지 않기 위해, 신뢰할 수 있는 코드값 정의서가
로컬에 없는 항목은 확신도를 낮게 표시한다.

사용법:
    python ai/analyze_industry_mapping.py
"""
import glob
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
SBIZ_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"

# 사용자가 준 경로(data/raw/gg/...)가 없으면 실제 위치(collect_gg_api.py 결과물)를 탐색
CARD_CANDIDATES = [
    Path("data/raw/gg/card_sales_hwaseong.csv"),
]
CARD_CANDIDATES += [
    Path(p) for p in glob.glob(str(PROJECT_ROOT / "**" / "card_sales_hwaseong.csv"), recursive=True)
]

MAPPING_DRAFT_PATH = PROCESSED_DATA_DIR / "industry_mapping_draft.csv"
SUMMARY_MD_PATH = PROCESSED_DATA_DIR / "industry_mapping_analysis.md"


def find_card_sales_path() -> Path:
    for p in CARD_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("card_sales_hwaseong.csv를 찾을 수 없음")


def load_sbiz() -> pd.DataFrame:
    df = pd.read_csv(
        SBIZ_PATH, encoding="utf-8-sig",
        usecols=["상권업종대분류명", "상권업종중분류명", "상권업종소분류명"],
        dtype=str,
    )
    return df


def load_card_sales(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"MDCLASS_INDUTYPE_CD": str}, usecols=["MDCLASS_INDUTYPE_CD", "SALES_AMT"])


def print_sbiz_hierarchy(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[1-A] 소진공 상권업종 계층 구조 (대분류 > 중분류) — 점포 수 기준")
    print("=" * 70)

    dae_counts = df["상권업종대분류명"].value_counts()
    print(f"\n대분류 고유값 수: {df['상권업종대분류명'].nunique()}개")
    print(f"중분류 고유값 수: {df['상권업종중분류명'].nunique()}개")
    print(f"소분류 고유값 수: {df['상권업종소분류명'].nunique()}개")

    tree = df.groupby(["상권업종대분류명", "상권업종중분류명"]).size().reset_index(name="점포행수")

    for dae in dae_counts.index:
        sub = tree[tree["상권업종대분류명"] == dae].sort_values("점포행수", ascending=False)
        print(f"\n■ {dae}  (총 {dae_counts[dae]:,}행)")
        for _, row in sub.iterrows():
            print(f"    - {row['상권업종중분류명']:<20} {row['점포행수']:>8,}행")

    return dae_counts, tree


def print_card_sales_codes(card_df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("[1-B] 카드매출 MDCLASS_INDUTYPE_CD 코드 분포")
    print("=" * 70)

    card_df["SALES_AMT"] = pd.to_numeric(card_df["SALES_AMT"], errors="coerce")
    agg = card_df.groupby("MDCLASS_INDUTYPE_CD").agg(
        건수=("SALES_AMT", "size"), 총매출=("SALES_AMT", "sum")
    ).sort_values("총매출", ascending=False)

    print(f"\n고유 코드 수: {card_df['MDCLASS_INDUTYPE_CD'].nunique()}개")
    print("\n⚠ 로컬에 MDCLASS_INDUTYPE_CD 코드값 정의서(경기데이터드림 '코드값' 탭)가 없어")
    print("  코드→업종명 매핑을 할 수 없음. 코드와 매출 규모만 나열함 — 업종명은")
    print("  data.gg.go.kr 해당 서비스 페이지의 '코드값' 탭을 받아와야 확정 가능.")
    print(f"\n{'코드':<6} {'건수':>10} {'총매출(원)':>18}")
    for code, row in agg.iterrows():
        print(f"{code:<6} {int(row['건수']):>10,} {row['총매출']:>18,.0f}")

    return agg


def build_mapping_draft(dae_counts: pd.Series, tree: pd.DataFrame, card_agg: pd.DataFrame) -> pd.DataFrame:
    """
    카드매출 쪽 코드명을 알 수 없으므로(정의서 미확보) 이 초안은
    "소진공 중분류 목록 + 카드매출 코드 목록"을 나란히 배치한 작업용 템플릿이다.
    실제 대응관계는 전부 확신도="하"로 표시 — 코드값 정의서 확보 후 사람이 채워야 함.
    """
    rows = []
    for _, r in tree.sort_values("점포행수", ascending=False).iterrows():
        rows.append({
            "소진공중분류명": r["상권업종중분류명"],
            "소진공대분류명": r["상권업종대분류명"],
            "카드매출코드": "미정 (코드값 정의서 필요)",
            "카드매출업종명": "미상",
            "확신도": "하",
            "근거": "카드매출 코드값 정의서 미확보 — 명칭 대조 불가, 사람이 data.gg.go.kr 코드값 탭 확인 후 채울 것",
        })
    return pd.DataFrame(rows)


def write_summary_md(dae_counts, tree, card_agg, mapping_df, priority_categories):
    lines = []
    lines.append("# 업종 매핑 분석 요약 (초안, 확정 아님)\n")
    lines.append("## 1. 데이터별 업종 체계 규모\n")
    lines.append(f"- 소진공 상권업종: 대분류 {dae_counts.shape[0]}개, "
                 f"중분류 {tree['상권업종중분류명'].nunique()}개\n")
    lines.append(f"- 카드매출 MDCLASS_INDUTYPE_CD: {card_agg.shape[0]}개 코드\n")

    lines.append("\n## 2. 핵심 문제\n")
    lines.append(
        "카드매출 쪽 코드(`MDCLASS_INDUTYPE_CD`)의 이름을 확인할 **코드값 정의서가 로컬에 없음**. "
        "경기데이터드림 `TB25BPTCARDDONGM` 서비스 페이지의 '코드값' 탭에서 받아와야 실제 매핑이 가능함. "
        "그 전까지는 코드→업종명 대응을 임의로 지어내지 않고 보류.\n"
    )

    lines.append("\n## 3. 소진공 대분류 대비 예상 우선순위 업종\n")
    for cat in priority_categories:
        if cat in dae_counts.index:
            lines.append(f"- **{cat}**: {dae_counts[cat]:,}행 — 폐업 예측 핵심 업종, 카드매출 코드 대응 확인 최우선\n")

    lines.append("\n## 4. 공통 업종 카테고리(안)\n")
    lines.append(
        "소진공 대분류(10개 내외)를 기준 뼈대로 삼고, 카드매출 코드가 이보다 세분화돼 있다면 "
        "N:1로 묶는 방향을 제안. 정의서 확보 후 다음 절차로 확정 권장:\n"
        "1. 카드매출 코드값 정의서 확보\n"
        "2. 코드명을 소진공 대분류/중분류명과 문자열 유사도 + 사람 검토로 매칭\n"
        "3. `industry_mapping_draft.csv`에 실제 대응관계와 확신도(상/중/하) 채워 넣기\n"
        "4. 팀 검토 후 `CATEGORY_MAP`(ai/build_dataset.py 참고 패턴)으로 코드 확정\n"
    )

    lines.append("\n## 5. 산출물\n")
    lines.append(f"- `{MAPPING_DRAFT_PATH}` — 매핑 작업용 템플릿(초안)\n")

    SUMMARY_MD_PATH.write_text("".join(lines), encoding="utf-8")
    print(f"\n요약 마크다운 저장: {SUMMARY_MD_PATH}")


def main():
    print(f"소진공 데이터 로드: {SBIZ_PATH}")
    sbiz_df = load_sbiz()

    card_path = find_card_sales_path()
    print(f"카드매출 데이터 로드: {card_path}")
    card_df = load_card_sales(card_path)

    dae_counts, tree = print_sbiz_hierarchy(sbiz_df)
    card_agg = print_card_sales_codes(card_df)

    print("\n" + "=" * 70)
    print("[2] 매핑 방안 — 코드값 정의서 미확보로 '확신도 하' 템플릿만 생성")
    print("=" * 70)
    mapping_df = build_mapping_draft(dae_counts, tree, card_agg)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    mapping_df.to_csv(MAPPING_DRAFT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n매핑 초안 저장: {MAPPING_DRAFT_PATH} ({len(mapping_df)}행)")

    priority_categories = ["음식", "소매", "수리·개인"]
    write_summary_md(dae_counts, tree, card_agg, mapping_df, priority_categories)


if __name__ == "__main__":
    main()
