"""
2023Q1 대량 이탈(2022Q4->2023Q1, 약 8,500개 순감/11,223개 총이탈)의 성격 규명 — 라벨 최종 판정.

검증 1: 이탈 코호트(2023Q1 vs 타분기) 업종·업력 프로파일 비교
검증 2(핵심): 인허가 데이터 교차검증 — 분기별 "폐업 확인율"
검증 3: 재등장 여부(상가업소번호 기준 / 상호명+주소 기준)

사용법:
    python ai/verify_2023q1_departure_nature.py
"""
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
DATASET_DIR = PROJECT_ROOT / "Hwaseong-commercial-ai-main-dataset"
PERMIT_DIR = DATASET_DIR / "화성시_인허가데이터"

ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
NAMES_PATH = PROCESSED_DATA_DIR / "sbiz_names.csv"

TARGET_DEPARTURE_Q = "2023Q1"  # 마지막으로 보인 분기=2022Q4, 사라진 채로 처음 확인된 분기=2023Q1


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def norm_addr(s) -> str:
    if pd.isna(s):
        return ""
    s = re.sub(r"경기도|화성시|효행구|만세구|동탄구|병점구", "", str(s))
    m = re.search(r"\d+(-\d+)?", s)
    if m:
        s = s[:m.end()]
    return "".join(s.split())


def norm_name(s) -> str:
    if pd.isna(s):
        return ""
    return "".join(str(s).split())


def to_date(s):
    return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")


def load_permits() -> pd.DataFrame:
    print("인허가 12종 통합 로드 중...")
    files = sorted(PERMIT_DIR.glob("*.csv"))
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, encoding="cp949", dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)
        out = pd.DataFrame({
            "사업장명": df.get("사업장명"),
            "인허가일자": df.get("인허가일자"),
            "폐업일자": df.get("폐업일자"),
            "영업상태명": df.get("영업상태명"),
            "지번주소_norm": df["지번주소"].map(norm_addr) if "지번주소" in df.columns else "",
            "사업장명_norm": df["사업장명"].map(norm_name) if "사업장명" in df.columns else "",
        })
        frames.append(out)
    permits = pd.concat(frames, ignore_index=True)
    permits["인허가일자_dt"] = to_date(permits["인허가일자"])
    permits["폐업일자_dt"] = to_date(permits["폐업일자"])
    permits["is_closed_permit"] = permits["폐업일자_dt"].notna() | (permits["영업상태명"] == "폐업")
    print(f"  통합 인허가 행 수: {len(permits):,}")
    return permits


def build_departure_cohorts(sbiz: pd.DataFrame, names: pd.DataFrame):
    quarters = sorted(sbiz["기준분기"].unique(), key=quarter_sort_key)
    q_idx = {q: i for i, q in enumerate(quarters)}
    next_map = {quarters[i]: quarters[i + 1] for i in range(len(quarters) - 1)}

    presence_pairs = set(zip(sbiz["상가업소번호"], sbiz["기준분기"]))
    first_seen = sbiz.groupby("상가업소번호")["기준분기"].apply(lambda s: min(s, key=quarter_sort_key))

    name_lookup = names.set_index(["상가업소번호", "기준분기"])["상호명"]

    sbiz_snap = sbiz.set_index(["상가업소번호", "기준분기"])

    rows = []
    for q in quarters:
        next_q = next_map.get(q)
        if next_q is None:
            continue
        present_at_q = set(sbiz.loc[sbiz["기준분기"] == q, "상가업소번호"])
        for store in present_at_q:
            if (store, next_q) not in presence_pairs:
                snap = sbiz_snap.loc[(store, q)]
                rows.append({
                    "상가업소번호": store,
                    "마지막분기": q,
                    "이탈시점": next_q,
                    "행정동명": snap["행정동명"],
                    "대분류": snap["상권업종대분류명"],
                    "중분류": snap["상권업종중분류명"],
                    "지번주소": snap["지번주소"],
                    "업력_분기수": q_idx[q] - q_idx[first_seen[store]],
                    "상호명": name_lookup.get((store, q), None),
                })
        print(f"  {q} -> {next_q}: 이탈 {sum(1 for r in rows if r['마지막분기']==q):,}건")

    dep = pd.DataFrame(rows)
    dep["지번주소_norm"] = dep["지번주소"].map(norm_addr)
    dep["상호명_norm"] = dep["상호명"].map(norm_name)
    return dep, quarters, q_idx, presence_pairs, name_lookup, next_map


def section1_profile(dep: pd.DataFrame):
    print("\n" + "=" * 80)
    print("[검증 1] 이탈 코호트 프로파일 비교 (2023Q1 vs 타분기)")
    print("=" * 80)

    target = dep[dep["이탈시점"] == TARGET_DEPARTURE_Q]
    other = dep[dep["이탈시점"] != TARGET_DEPARTURE_Q]

    print(f"\n2023Q1 이탈: {len(target):,}건 / 타분기 평균 이탈: {len(other) / dep['이탈시점'].nunique():,.0f}건")

    print("\n대분류 분포(%) 비교:")
    t_dae = target["대분류"].value_counts(normalize=True) * 100
    o_dae = other["대분류"].value_counts(normalize=True) * 100
    comp = pd.DataFrame({"2023Q1(%)": t_dae, "타분기평균(%)": o_dae}).fillna(0).sort_values("2023Q1(%)", ascending=False)
    print(comp.round(1).to_string())

    print("\n업력(분기수) 분포 비교:")
    print(f"  2023Q1: 평균 {target['업력_분기수'].mean():.1f}분기, 중앙값 {target['업력_분기수'].median():.1f}분기, "
          f"3년(12분기)미만 비율 {(target['업력_분기수'] < 12).mean() * 100:.1f}%")
    print(f"  타분기: 평균 {other['업력_분기수'].mean():.1f}분기, 중앙값 {other['업력_분기수'].median():.1f}분기, "
          f"3년(12분기)미만 비율 {(other['업력_분기수'] < 12).mean() * 100:.1f}%")

    return target, other


def section2_permit_crosscheck(dep: pd.DataFrame, permits: pd.DataFrame):
    print("\n" + "=" * 80)
    print("[검증 2, 핵심] 인허가 교차검증 — 분기별 폐업 확인율")
    print("=" * 80)

    # 참고: 인허가 전체에서 실제 폐업건의 업력 분포(3년미만 비율) 직접 산출 — 사용자가 준 48.8%와 대조
    closed_permits = permits[permits["is_closed_permit"] & permits["인허가일자_dt"].notna() & permits["폐업일자_dt"].notna()].copy()
    closed_permits["업력_년"] = (closed_permits["폐업일자_dt"] - closed_permits["인허가일자_dt"]).dt.days / 365.25
    under3_ratio = (closed_permits["업력_년"] < 3).mean() * 100
    print(f"참고: 인허가 전체 실제 폐업건 중 업력 3년미만 비율(직접 산출) = {under3_ratio:.1f}% "
          f"(n={len(closed_permits):,}, 배경에 제시된 48.8%와 대조용)")

    # 주소만 매칭(1순위 후보군), 그 중 이름도 일치하면 확신도 높은 매칭으로 표시
    # 성능: 행별 DataFrame 필터링은 이탈건수x인허가건수라 너무 느려 dict 기반 O(1) 조회로 구성
    permits_by_addr = permits[permits["지번주소_norm"] != ""]
    addr_groups = {addr: g for addr, g in permits_by_addr.groupby("지번주소_norm")}

    def match_one(addr, name):
        cands = addr_groups.get(addr)
        if cands is None:
            return None
        name_match = cands[cands["사업장명_norm"] == name]
        if not name_match.empty:
            return name_match.iloc[0]
        return cands.iloc[0]

    results = []
    for q, grp in dep.groupby("이탈시점"):
        n_total = len(grp)
        n_matched = 0
        n_confirmed_closed = 0
        n_still_operating = 0
        for _, row in grp.iterrows():
            m = match_one(row["지번주소_norm"], row["상호명_norm"])
            if m is None:
                continue
            n_matched += 1
            if m["is_closed_permit"]:
                n_confirmed_closed += 1
            elif m["영업상태명"] in ("영업/정상",):
                n_still_operating += 1
        results.append({
            "이탈시점": q, "이탈점포수": n_total, "인허가매칭": n_matched,
            "폐업확인": n_confirmed_closed, "영업중으로남음": n_still_operating,
            "폐업확인율(%)": n_confirmed_closed / n_total * 100 if n_total else np.nan,
            "매칭률(%)": n_matched / n_total * 100 if n_total else np.nan,
        })

    result_df = pd.DataFrame(results).sort_values("이탈시점", key=lambda s: s.map(quarter_sort_key))
    print("\n분기별 결과:")
    print(result_df.round(1).to_string(index=False))

    target_rate = result_df.loc[result_df["이탈시점"] == TARGET_DEPARTURE_Q, "폐업확인율(%)"].iloc[0]
    other_rate = result_df.loc[result_df["이탈시점"] != TARGET_DEPARTURE_Q, "폐업확인율(%)"].mean()
    target_still_open = result_df.loc[result_df["이탈시점"] == TARGET_DEPARTURE_Q, "영업중으로남음"].iloc[0]
    other_still_open_avg = result_df.loc[result_df["이탈시점"] != TARGET_DEPARTURE_Q, "영업중으로남음"].mean()

    print(f"\n2023Q1 폐업확인율: {target_rate:.1f}% vs 타분기 평균: {other_rate:.1f}%")
    print(f"2023Q1 '영업중으로 남음' 건수: {target_still_open} vs 타분기 평균: {other_still_open_avg:.1f}건")

    return result_df, target_rate, other_rate


def section3_reappearance(dep: pd.DataFrame, presence_pairs, sbiz: pd.DataFrame, names: pd.DataFrame, quarters):
    print("\n" + "=" * 80)
    print("[검증 3] 재등장 여부")
    print("=" * 80)

    target = dep[dep["이탈시점"] == TARGET_DEPARTURE_Q].copy()
    all_store_quarters = set(zip(sbiz["상가업소번호"], sbiz["기준분기"]))

    later_quarters_by_store = {}
    q_after = quarters[quarters.index(TARGET_DEPARTURE_Q):]

    reappear_by_number = target["상가업소번호"].map(
        lambda s: any((s, q) in all_store_quarters for q in q_after)
    )
    rate_number = reappear_by_number.mean() * 100
    print(f"상가업소번호 기준 재등장 비율: {rate_number:.1f}% ({reappear_by_number.sum():,}/{len(target):,})")

    merged_names = sbiz.merge(names, on=["상가업소번호", "기준분기"], how="left")
    merged_names["지번주소_norm"] = merged_names["지번주소"].map(norm_addr)
    merged_names["상호명_norm"] = merged_names["상호명"].map(norm_name)
    key_quarters = merged_names.groupby(["지번주소_norm", "상호명_norm"])["기준분기"].apply(set)

    def reappear_by_key(row):
        key = (row["지번주소_norm"], row["상호명_norm"])
        qs = key_quarters.get(key, set())
        return any(q in qs for q in q_after if q != row["마지막분기"])

    reappear_by_name_addr = target.apply(reappear_by_key, axis=1)
    rate_name_addr = reappear_by_name_addr.mean() * 100
    print(f"상호명+주소 기준 재등장 비율: {rate_name_addr:.1f}% ({reappear_by_name_addr.sum():,}/{len(target):,})")

    return rate_number, rate_name_addr


def main():
    print(f"[로드] {ALL_PATH}")
    sbiz = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동명": str, "상권업종대분류명": str, "상권업종중분류명": str,
        "지번주소": str, "기준분기": str,
    })
    print(f"[로드] {NAMES_PATH}")
    names = pd.read_csv(NAMES_PATH, encoding="utf-8-sig", dtype={"상가업소번호": str, "기준분기": str, "상호명": str})

    print("\n분기별 이탈 코호트 구축 중...")
    dep, quarters, q_idx, presence_pairs, name_lookup, next_map = build_departure_cohorts(sbiz, names)
    print(f"\n전체 이탈 레코드: {len(dep):,}건")

    target, other = section1_profile(dep)

    permits = load_permits()
    result_df, target_rate, other_rate = section2_permit_crosscheck(dep, permits)

    rate_number, rate_name_addr = section3_reappearance(dep, presence_pairs, sbiz, names, quarters)

    print("\n" + "=" * 80)
    print("[종합 판정]")
    print("=" * 80)
    diff = target_rate - other_rate
    print(f"폐업확인율 차이(2023Q1 - 타분기평균): {diff:+.1f}%p")
    if abs(diff) <= 10:
        verdict = "실제 폐업 (라벨 유효) — 2023Q1 확인율이 타분기와 비슷"
    elif diff < -10:
        verdict = "데이터 정리 의심 (라벨 무효 가능성) — 2023Q1 확인율만 현저히 낮음"
    else:
        verdict = "판단 보류 — 2023Q1 확인율이 오히려 더 높음, 추가 조사 필요"
    print(f"판정: {verdict}")
    print(f"(참고: 재등장 비율 - 번호기준 {rate_number:.1f}%, 상호명+주소기준 {rate_name_addr:.1f}%)")


if __name__ == "__main__":
    main()
