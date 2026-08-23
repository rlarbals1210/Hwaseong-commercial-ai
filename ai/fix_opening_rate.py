"""개업률 데이터 결함 보정.

문제: 소진공 스냅샷 수록 지연으로 개업 수가 특정 분기에 몰린다(2024Q3 101건 / 2024Q4 9,090건).
      폐업 갭필링은 "사라졌다 재등장"만 메우므로 개업 방향에는 원리상 작동하지 않는다.

보정: 첫 등장 분기 대신 인허가 분기를 개업 시점으로 재배정한다.
      - 인허가 매칭분(82.7%): 첫 등장 이전의 가장 최근 인허가 분기로 재배정
        · 인허가가 데이터 시작 이전이면 관측 창 밖의 기존 점포이므로 개업에서 제외
      - 미매칭분(17.3%): 원본 첫 등장 분기 유지 (추정을 넣지 않는다)
      - 잔여 흔들림은 4분기 이동평균으로 흡수

출력: final_dataset.csv 에 컬럼 추가 (기존 컬럼은 변경하지 않는다)
      개업_율_보정 / 개업_율_보정_ma4 / 폐업_률_ma4 / 개업_보정_매칭률
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eda"))
import paths as eda_paths  # noqa: E402

MA_WINDOW = 4


def norm_addr(s) -> str:
    """build_dataset.py 와 동일한 지번주소 정규화."""
    if pd.isna(s):
        return ""
    s = re.sub(r"경기도|화성시|효행구|만세구|동탄구|병점구", "", str(s))
    m = re.search(r"\d+(-\d+)?", s)
    if m:
        s = s[: m.end()]
    return "".join(s.split())


def load_permits() -> pd.Series:
    """지번주소_norm -> 인허가 분기(qoffset) 오름차순 배열.

    build_age_lookup()은 주소별 '최초' 인허가만 남겨 주소 재사용 시 업력이 과대 추정된다.
    여기서는 전체 인허가 이력을 보존해 '첫 등장 이전의 가장 최근 인허가'를 고를 수 있게 한다.
    """
    frames = []
    for p in sorted(eda_paths.PERMIT_DIR.glob("*.csv")):
        if p.name.startswith("._"):
            continue
        df = None
        for enc in ("cp949", "utf-8"):
            try:
                df = pd.read_csv(p, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
        if df is None or "지번주소" not in df.columns or "인허가일자" not in df.columns:
            continue
        frames.append(df[["지번주소", "인허가일자"]])

    permits = pd.concat(frames, ignore_index=True)
    permits["norm"] = permits["지번주소"].map(norm_addr)
    permits["dt"] = pd.to_datetime(permits["인허가일자"], format="%Y-%m-%d", errors="coerce")
    permits = permits.dropna(subset=["dt"])
    permits = permits[permits["norm"] != ""]
    permits["pq"] = permits["dt"].dt.year * 4 + (permits["dt"].dt.month - 1) // 3 + 1
    return permits.groupby("norm")["pq"].apply(lambda s: np.array(sorted(s.unique())))


def quarter_to_code(q: str) -> int:
    return int(q[:4]) * 10 + int(q[5])


def assign_open_quarter(panel: pd.DataFrame, permits: pd.Series) -> pd.DataFrame:
    """점포별 개업 분기를 확정한다."""
    first = (
        panel.sort_values("idx")
        .drop_duplicates("상가업소번호", keep="first")
        .loc[:, ["상가업소번호", "기준분기", "행정동명", "상권업종중분류명", "지번주소", "idx"]]
        .copy()
    )
    first["first_qoff"] = first["기준분기"].map(lambda q: int(q[:4]) * 4 + int(q[5]))
    first["norm"] = first["지번주소"].map(norm_addr)

    def latest_permit_le(row):
        arr = permits.get(row["norm"])
        if arr is None:
            return np.nan
        ok = arr[arr <= row["first_qoff"]]
        return ok[-1] if len(ok) else np.nan

    first["permit_qoff"] = first.apply(latest_permit_le, axis=1)
    first["matched"] = first["permit_qoff"].notna()

    # 매칭분은 인허가 분기로, 미매칭분은 첫 등장 분기 그대로
    first["open_qoff"] = np.where(first["matched"], first["permit_qoff"], first["first_qoff"])
    return first


def main() -> None:
    panel = pd.read_csv(
        eda_paths.PROCESSED_DATA_DIR / "store_panel.csv",
        encoding="utf-8-sig",
        low_memory=False,
        usecols=["상가업소번호", "기준분기", "행정동명", "상권업종중분류명", "지번주소", "idx"],
    )
    quarters = sorted(panel["기준분기"].unique(), key=lambda q: (int(q[:4]), int(q[5])))
    qoff_of = {q: int(q[:4]) * 4 + int(q[5]) for q in quarters}
    code_of = {qoff_of[q]: quarter_to_code(q) for q in quarters}
    first_qoff = min(qoff_of.values())

    permits = load_permits()
    print(f"인허가 주소 {len(permits):,}건")

    first = assign_open_quarter(panel, permits)
    print(f"점포 {len(first):,} / 인허가 매칭 {first['matched'].mean() * 100:.1f}%")

    # 데이터 시작 분기의 점포는 '개업'을 판정할 수 없다(직전 분기가 없음)
    opens = first[first["idx"] > 0].copy()
    # 인허가가 관측 창보다 이전이면 기존 점포가 늦게 수록된 것이므로 개업이 아니다
    in_window = opens["open_qoff"] > first_qoff
    dropped = (~in_window).sum()
    opens = opens[in_window]
    print(f"신규등장 {len(first[first['idx'] > 0]):,} → 개업 인정 {len(opens):,} (창 밖 기존점포 {dropped:,} 제외)")

    opens["개업_분기코드"] = opens["open_qoff"].map(code_of)
    opens = opens.dropna(subset=["개업_분기코드"])
    opens["개업_분기코드"] = opens["개업_분기코드"].astype(int)

    open_cnt = (
        opens.groupby(["행정동명", "상권업종중분류명", "개업_분기코드"])
        .agg(개업수_보정=("상가업소번호", "size"), 매칭수=("matched", "sum"))
        .reset_index()
        .rename(columns={"상권업종중분류명": "통합카테고리", "개업_분기코드": "기준_년분기_코드"})
    )

    final = pd.read_csv(eda_paths.PROCESSED_DATA_DIR / "final_dataset.csv", encoding="utf-8-sig")
    final = final.sort_values(["행정동명", "통합카테고리", "기준_년분기_코드"])

    # 분모: 직전 분기 점포수 (원본 개업_율_평균과 동일 기준)
    final["점포수_직전"] = final.groupby(["행정동명", "통합카테고리"])["점포수"].shift(1)

    final = final.merge(open_cnt, on=["행정동명", "통합카테고리", "기준_년분기_코드"], how="left")
    final[["개업수_보정", "매칭수"]] = final[["개업수_보정", "매칭수"]].fillna(0)

    final["개업_율_보정"] = (final["개업수_보정"] / final["점포수_직전"].replace(0, np.nan)).round(4)
    final["개업_보정_매칭률"] = (final["매칭수"] / final["개업수_보정"].replace(0, np.nan)).round(3)

    grp = final.groupby(["행정동명", "통합카테고리"])
    for src, dst in (("개업_율_보정", "개업_율_보정_ma4"), ("폐업_률_평균", "폐업_률_ma4")):
        final[dst] = grp[src].transform(lambda s: s.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean()).round(4)

    final = final.drop(columns=["점포수_직전", "개업수_보정", "매칭수"])
    out = eda_paths.PROCESSED_DATA_DIR / "final_dataset.csv"
    final.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"저장: {out} {final.shape}")


if __name__ == "__main__":
    main()
