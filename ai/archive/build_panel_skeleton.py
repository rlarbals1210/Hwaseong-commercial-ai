"""
feature 테이블 1단계: 업종 체계 파악 -> 업종 단위(대/중분류) 진단 -> 카드매출 14개 업종
대응 후보 제안 -> 행정동x업종x분기 뼈대 생성 -> B+1/B+2 폐업률 라벨 집계.

이번 단계에서는 feature는 붙이지 않음(뼈대 + 라벨까지만).

최종 목표 그레인: 행정동 x 업종 x 관측분기(B)
  label_h2 = B+2분기 closure_rate (메인)
  label_h1 = B+1분기 closure_rate (비교군)

사용법:
    python ai/build_panel_skeleton.py
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))

ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
LABELS_V2_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v2.csv"
DONG_LIST_PATH = next(PROJECT_ROOT.glob("**/경기도_읍면동_리스트.csv"))

SKELETON_OUT = PROCESSED_DATA_DIR / "panel_skeleton.csv"
MAPPING_OUT = PROCESSED_DATA_DIR / "sbiz_card_industry_map_draft.csv"

CARD_14 = ["음식점", "주점", "미용", "학원·교육", "의료", "숙박", "연료판매",
           "수리서비스", "식료품소매", "의류·잡화", "자동차", "여가·스포츠", "종합소매", "온라인소비"]


def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def load_all():
    df = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str,
        "상권업종대분류명": str, "상권업종중분류명": str, "상권업종소분류명": str,
        "기준분기": str,
    })
    return df


def section_1(df: pd.DataFrame):
    print("\n" + "=" * 80)
    print("[1] 소진공 업종 체계 파악")
    print("=" * 80)
    print(f"대분류 고유값: {df['상권업종대분류명'].nunique()}개")
    print(f"중분류 고유값: {df['상권업종중분류명'].nunique()}개")
    print(f"소분류 고유값: {df['상권업종소분류명'].nunique()}개")

    dae_counts = df.groupby("상권업종대분류명")["상가업소번호"].nunique().sort_values(ascending=False)
    tree = df.groupby(["상권업종대분류명", "상권업종중분류명"])["상가업소번호"].nunique().reset_index(name="점포수")

    print("\n대분류 > 중분류 트리 (점포수=distinct 상가업소번호, 전체기간 기준):")
    for dae in dae_counts.index:
        sub = tree[tree["상권업종대분류명"] == dae].sort_values("점포수", ascending=False)
        print(f"\n■ {dae} (대분류 합계 {dae_counts[dae]:,}개 점포)")
        for _, row in sub.iterrows():
            print(f"    - {row['상권업종중분류명']:<20} {row['점포수']:>7,}개")

    print("\n화성시 점포 수 상위 30개 중분류:")
    jung_counts = df.groupby("상권업종중분류명")["상가업소번호"].nunique().sort_values(ascending=False)
    for i, (jung, cnt) in enumerate(jung_counts.head(30).items(), 1):
        print(f"  {i:>2}. {jung:<20} {cnt:>7,}개")

    return dae_counts, jung_counts


def diagnose_unit(df: pd.DataFrame, unit_col: str, label: str):
    print(f"\n--- {label} 기준 (행정동 x {unit_col} x 분기 셀) ---")
    cell = df.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"].nunique().reset_index(name="점포수")

    n_cells = len(cell)
    total_stores = cell["점포수"].sum()
    print(f"셀 개수: {n_cells:,}")
    print(f"셀당 점포수 — 평균 {cell['점포수'].mean():.2f}, 중앙값 {cell['점포수'].median():.1f}, "
          f"최소 {cell['점포수'].min()}, 최대 {cell['점포수'].max()}")

    hist_bins = [0, 1, 2, 5, 10, 20, 50, 100, cell["점포수"].max() + 1]
    hist = pd.cut(cell["점포수"], bins=hist_bins, right=False).value_counts().sort_index()
    print("점포수 분포(히스토그램):")
    for interval, cnt in hist.items():
        print(f"    {interval}: {cnt:,}개 셀")

    print("\n최소 점포수 임계값별 잔존 셀 수 / 커버리지:")
    for th in [5, 10, 20]:
        survive = cell[cell["점포수"] >= th]
        n_survive = len(survive)
        coverage = survive["점포수"].sum() / total_stores * 100
        below_ratio = (cell["점포수"] < th).mean() * 100
        print(f"  임계값 {th}개 미만 비율: {below_ratio:.1f}% | "
              f"{th}개 이상 남는 셀: {n_survive:,}개({n_survive/n_cells*100:.1f}%) | "
              f"점포수 기준 커버리지: {coverage:.1f}%")

    return cell


def section_2(df: pd.DataFrame):
    print("\n" + "=" * 80)
    print("[2] 업종 단위 결정을 위한 진단 (대분류 vs 중분류)")
    print("=" * 80)
    cell_dae = diagnose_unit(df, "상권업종대분류명", "대분류")
    cell_jung = diagnose_unit(df, "상권업종중분류명", "중분류")
    return cell_dae, cell_jung


def section_3(dae_counts, jung_counts):
    print("\n" + "=" * 80)
    print("[3] 카드매출 14개 공통업종과의 대응 후보 (제안 — 확정 아님)")
    print("=" * 80)

    # 사람 검토 전 초안. 근거는 업종명 의미 대조 기준이며, 실제 매출 스케일/구성비
    # 검증(card_industry_mapping.csv에서 이미 검증한 카드매출 쪽과 달리)은 안 거쳤음.
    rows = [
        ("음식", "한식", "음식점", "상", "명칭 그대로 대응"),
        ("음식", "중식", "음식점", "상", "명칭 그대로 대응"),
        ("음식", "일식", "음식점", "상", "명칭 그대로 대응"),
        ("음식", "서양식", "음식점", "상", "명칭 그대로 대응"),
        ("음식", "동남아시아", "음식점", "상", "명칭 그대로 대응"),
        ("음식", "기타 간이", "음식점", "중상", "분식/패스트푸드류로 추정, 카드매출 Q측 세분류와 다대일"),
        ("음식", "비알코올", "음식점", "중", "카페/음료 — 카드매출 Q13(커피/음료)과 대응 가능하나 음식점 대분류에 넣을지 별도로 뺄지 검토 필요"),
        ("음식", "구내식당·뷔페", "음식점", "상", "카드매출 Q05(부페)와 대응"),
        ("음식", "주점", "주점", "상", "명칭 그대로 대응"),
        ("수리·개인", "이용·미용", "미용", "상", "명칭 그대로 대응"),
        ("교육", "일반 교육", "학원·교육", "상", "명칭 그대로 대응"),
        ("교육", "기타 교육", "학원·교육", "상", "명칭 그대로 대응"),
        ("교육", "교육 지원", "학원·교육", "중", "직접 교습이 아닌 지원업 — 카드매출 쪽 매칭 애매"),
        ("보건의료", "의원", "의료", "상", "명칭 그대로 대응"),
        ("보건의료", "병원", "의료", "상", "명칭 그대로 대응"),
        ("보건의료", "기타 보건", "의료", "중", "범위가 넓어 카드매출 S06(기타의료) 수준 대응"),
        ("숙박", "일반 숙박", "숙박", "상", "명칭 그대로 대응"),
        ("숙박", "기타 숙박", "숙박", "상", "명칭 그대로 대응"),
        ("소매", "연료 소매", "연료판매", "상", "명칭 그대로 대응"),
        ("수리·개인", "자동차 수리·세차", "자동차", "중상", "카드매출쪽은 자동차 판매·정비 통합이라 이쪽도 자동차로 묶는 편이 일관적"),
        ("수리·개인", "모터사이클 수리", "자동차", "중", "위와 동일 논리, 다만 이륜차라 세부는 다를 수 있음"),
        ("수리·개인", "세탁", "수리서비스", "상", "명칭 그대로 대응"),
        ("수리·개인", "가전제품 수리", "수리서비스", "상", "명칭 그대로 대응"),
        ("수리·개인", "기타 가정용품 수리", "수리서비스", "상", "명칭 그대로 대응"),
        ("수리·개인", "컴퓨터 수리", "수리서비스", "상", "명칭 그대로 대응"),
        ("수리·개인", "통신장비 수리", "수리서비스", "상", "명칭 그대로 대응"),
        ("수리·개인", "욕탕·신체관리", "수리서비스", "중", "카드매출 F05(사우나/휴게시설)에 가까움, 미용과 헷갈릴 수 있음"),
        ("수리·개인", "장례식장", "-", "하", "카드매출 14개 업종 중 대응 없음(F08 가례서비스와 유사하나 14개 목록엔 미포함)"),
        ("수리·개인", "기타 개인", "-", "하", "범위 불분명, 대응 보류"),
        ("소매", "식료품 소매", "식료품소매", "상", "명칭 그대로 대응"),
        ("소매", "섬유·의복·신발 소매", "의류·잡화", "상", "명칭 그대로 대응"),
        ("소매", "자동차 부품 소매", "자동차", "상", "카드매출 매핑표에서도 자동차로 통합함"),
        ("소매", "모터사이클 소매", "자동차", "중", "위와 동일 논리"),
        ("소매", "종합 소매", "종합소매", "상", "명칭 그대로 대응"),
        ("예술·스포츠", "유원지·오락", "여가·스포츠", "상", "카드매출 O04(취미/오락)와 대응"),
        ("예술·스포츠", "스포츠 서비스", "여가·스포츠", "상", "카드매출 O03(일반스포츠)와 대응"),
        ("예술·스포츠", "도서관·사적지", "-", "하", "카드매출 매핑에서 T계열(전시·공연)은 성격 달라 제외한다고 명시함 — 동일 논리로 제외"),
    ]
    map_df = pd.DataFrame(rows, columns=["소진공대분류명", "소진공중분류명", "카드매출_공통업종_후보", "확신도", "근거"])

    unmatched_dae = ["과학·기술", "부동산", "시설관리·임대"]
    print("\n대응 후보 (일부 발췌, 전체는 저장 파일 참고):")
    print(map_df.to_string(index=False))

    print(f"\n카드매출 14개 업종 어디에도 대응 안 되는 소진공 대분류(전체): {unmatched_dae}")
    print("  -> 과학·기술(컨설팅/디자인/광고 등 B2B 서비스업), 부동산(중개업),")
    print("     시설관리·임대(청소/고용알선/대여업)는 소상공인 폐업 예측 맥락에서는")
    print("     의미 있지만 '카드매출로 소비자 지출 패턴을 보는' 14개 업종 체계 자체가")
    print("     다루는 영역이 아님 — 카드매출 feature와는 무관하게 소진공 데이터 자체")
    print("     피처(점포수/폐업률 추세 등)로만 활용 가능.")

    no_match_rows = map_df[map_df["카드매출_공통업종_후보"] == "-"]
    print(f"\n소진공 중분류 중 카드매출 14개와 대응 안 되는 것(위 표 내에서): "
          f"{no_match_rows['소진공중분류명'].tolist()}")

    map_df.to_csv(MAPPING_OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {MAPPING_OUT}")
    return map_df


def build_skeleton(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print("[4] 뼈대 테이블 생성 (행정동 x 업종(중분류) x 분기, 실제 존재하는 조합만)")
    print("=" * 80)

    skeleton = (
        df.groupby(["행정동명", "상권업종중분류명", "기준분기"])["상가업소번호"]
        .nunique().reset_index(name="기초점포수")
    )
    skeleton = skeleton.rename(columns={"상권업종중분류명": "업종", "기준분기": "관측분기"})
    print(f"뼈대 행 수: {len(skeleton):,} (행정동 {skeleton['행정동명'].nunique()}개 x "
          f"업종 {skeleton['업종'].nunique()}개 x 분기 {skeleton['관측분기'].nunique()}개, "
          f"실제 존재 조합만)")
    return skeleton


def build_closure_agg(labels_v2: pd.DataFrame) -> pd.DataFrame:
    labeled = labels_v2.dropna(subset=["is_closed_v2"]).copy()
    agg = (
        labeled.groupby(["행정동명", "상권업종중분류명", "기준분기"])["is_closed_v2"]
        .agg(closure_count="sum", store_count="count").reset_index()
    )
    agg["closure_rate"] = agg["closure_count"] / agg["store_count"]
    agg = agg.rename(columns={"상권업종중분류명": "업종", "기준분기": "분기"})
    return agg


def attach_labels(skeleton: pd.DataFrame, closure_agg: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 80)
    print("[5] 라벨 집계 (B+1 / B+2 폐업률)")
    print("=" * 80)

    quarters_sorted = sorted(skeleton["관측분기"].unique(), key=quarter_sort_key)
    next_map = {quarters_sorted[i]: quarters_sorted[i + 1] for i in range(len(quarters_sorted) - 1)}
    next2_map = {quarters_sorted[i]: quarters_sorted[i + 2] for i in range(len(quarters_sorted) - 2)}

    closure_lookup = closure_agg.set_index(["행정동명", "업종", "분기"])["closure_rate"]

    def lookup(row, offset_map):
        target_q = offset_map.get(row["관측분기"])
        if target_q is None:
            return np.nan
        key = (row["행정동명"], row["업종"], target_q)
        return closure_lookup.get(key, np.nan)

    skeleton["label_h1"] = skeleton.apply(lambda r: lookup(r, next_map), axis=1)
    skeleton["label_h2"] = skeleton.apply(lambda r: lookup(r, next2_map), axis=1)

    print(f"label_h1 결측 아닌 행: {skeleton['label_h1'].notna().sum():,} / {len(skeleton):,}")
    print(f"label_h2 결측 아닌 행: {skeleton['label_h2'].notna().sum():,} / {len(skeleton):,}")

    return skeleton


def section_6(skeleton: pd.DataFrame, df: pd.DataFrame):
    print("\n" + "=" * 80)
    print("[6] 라벨 분포 진단")
    print("=" * 80)

    labeled = skeleton.dropna(subset=["label_h2"])
    print(f"\nlabel_h2 분포 (n={len(labeled):,}):")
    print(labeled["label_h2"].describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95]).to_string())
    zero_ratio = (labeled["label_h2"] == 0).mean() * 100
    print(f"\nlabel_h2 == 0 비율: {zero_ratio:.1f}%")

    print("\n최소 점포수 임계값별 label_h2 분포 변화 (기초점포수 기준 필터):")
    for th in [5, 10, 20]:
        sub = labeled[labeled["기초점포수"] >= th]
        z = (sub["label_h2"] == 0).mean() * 100 if len(sub) else float("nan")
        print(f"  임계값 {th}: n={len(sub):,}, 평균 {sub['label_h2'].mean():.4f}, "
              f"중앙값 {sub['label_h2'].median():.4f}, 0%비율 {z:.1f}%")

    print("\n업종별 평균 폐업률(label_h2, 전체 기간):")
    by_industry = labeled.groupby("업종")["label_h2"].mean().sort_values(ascending=False)
    for ind, v in by_industry.items():
        print(f"  {ind:<20} {v*100:.2f}%")

    print("\n연도별(관측분기 기준) 평균 폐업률(label_h2):")
    labeled = labeled.copy()
    labeled["연도"] = labeled["관측분기"].str[:4]
    by_year = labeled.groupby("연도")["label_h2"].mean().sort_index()
    for y, v in by_year.items():
        print(f"  {y}: {v*100:.2f}%")


def main():
    print(f"입력: {ALL_PATH}")
    df = load_all()

    dae_counts, jung_counts = section_1(df)
    cell_dae, cell_jung = section_2(df)
    section_3(dae_counts, jung_counts)

    skeleton = build_skeleton(df)

    print(f"\n라벨 입력: {LABELS_V2_PATH}")
    labels_v2 = pd.read_csv(LABELS_V2_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str, "상권업종중분류명": str, "기준분기": str,
    })
    closure_agg = build_closure_agg(labels_v2)
    skeleton = attach_labels(skeleton, closure_agg)

    section_6(skeleton, df)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    skeleton.to_csv(SKELETON_OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {SKELETON_OUT} ({len(skeleton):,}행)")


if __name__ == "__main__":
    main()
