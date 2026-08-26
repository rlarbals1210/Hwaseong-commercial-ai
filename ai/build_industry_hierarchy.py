"""업종 계층(대분류 10 → 중분류 74) 산출.

## 왜 별도 산출물인가

노다지(서울)의 화면은 "구를 고르고 그 안의 행정동을 본다"는 2단 구조 위에 서 있다.
화성시는 구가 없는 단일 시라 그 자리가 비는데, 대신 업종에 2단 구조가 있다 —
상권업종 대분류 10개와 중분류 74개다. 사이드바의 2단 선택, 트렌드 화면의 토글,
지도의 드릴다운이 전부 이 계층을 쓴다.

계층 자체는 `store_panel.csv`(873,035행, 150MB)에 들어 있지만 그 파일은 점포 단위라
저장소에 커밋하지 않는다. 그래서 계층만 뽑아 작은 CSV로 남긴다 — `final_dataset.csv`
같은 다른 집계 산출물과 같은 취급이다. 이러면 팀원이 SSD 없이 pull만 받아도
`import_normalized_db.py`가 계층을 적재할 수 있다.

## 검증한 것 (2026-08-26)

- 고유 (대분류, 중분류) 쌍 74개 — 중분류 하나가 두 대분류에 걸치는 경우 0건
- `final_dataset.csv`의 통합카테고리 74개와 **완전 일치** (양방향 차집합 0)

두 번째가 중요하다. 계층에 없는 업종이 화면에 뜨면 그 업종은 어느 대분류를 골라도
안 보이게 되고, 반대면 빈 대분류가 생긴다.

## 실행

    python ai/build_industry_hierarchy.py

출력: data/processed/industry_hierarchy.csv
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORE_PANEL = PROJECT_ROOT / "data" / "processed" / "store_panel.csv"
FINAL_DATASET = PROJECT_ROOT / "data" / "processed" / "final_dataset.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "industry_hierarchy.csv"

MAJOR_COL = "상권업종대분류명"
MEDIUM_COL = "상권업종중분류명"


def build() -> list[dict]:
    if not STORE_PANEL.exists():
        raise SystemExit(
            f"{STORE_PANEL} 가 없습니다.\n"
            "이 스크립트는 점포 패널이 있는 환경에서만 돌립니다. 산출물"
            f"({OUT_PATH.name})은 저장소에 포함돼 있으니 팀원은 다시 만들 필요가 없습니다."
        )

    # 873,035행이라 DictReader 대신 인덱스로 읽는다. 필요한 컬럼은 둘뿐이다.
    pairs: Counter[tuple[str, str]] = Counter()
    with STORE_PANEL.open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.reader(fp)
        header = next(reader)
        i_major, i_medium = header.index(MAJOR_COL), header.index(MEDIUM_COL)
        for row in reader:
            pairs[(row[i_major], row[i_medium])] += 1

    # 중분류 하나가 두 대분류에 걸치면 계층이 성립하지 않는다. 조용히 넘기지 않는다.
    parents: defaultdict[str, set[str]] = defaultdict(set)
    for (major, medium), _ in pairs.items():
        parents[medium].add(major)
    conflicts = {m: sorted(p) for m, p in parents.items() if len(p) > 1}
    if conflicts:
        raise SystemExit(f"중분류가 두 개 이상의 대분류에 걸쳐 있습니다: {conflicts}")

    rows = [
        {"대분류명": major, "중분류명": medium, "점포수": count}
        for (major, medium), count in sorted(pairs.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]
    return rows


def verify(rows: list[dict]) -> None:
    """final_dataset의 통합카테고리와 양방향으로 대조한다."""
    if not FINAL_DATASET.exists():
        print(f"  ! {FINAL_DATASET.name} 없음 — 대조를 건너뜁니다", file=sys.stderr)
        return
    used = {r["통합카테고리"] for r in csv.DictReader(FINAL_DATASET.open(encoding="utf-8-sig"))}
    listed = {r["중분류명"] for r in rows}
    missing, extra = sorted(used - listed), sorted(listed - used)
    if missing:
        raise SystemExit(f"final_dataset에 있는데 계층에 없는 업종: {missing}")
    if extra:
        print(f"  ! 계층에만 있고 final_dataset에 없는 업종: {extra}", file=sys.stderr)
    print(f"  final_dataset 통합카테고리 {len(used)}개와 일치")


def main() -> None:
    rows = build()
    majors = sorted({r["대분류명"] for r in rows})
    print(f"대분류 {len(majors)}개 / 중분류 {len(rows)}개")
    for major in majors:
        children = [r for r in rows if r["대분류명"] == major]
        stores = sum(r["점포수"] for r in children)
        print(f"  {major:<16} 중분류 {len(children):>2}개  점포 {stores:>7,}")
    verify(rows)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["대분류명", "중분류명", "점포수"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n저장: {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
