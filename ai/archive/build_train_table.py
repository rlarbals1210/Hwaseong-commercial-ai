"""
feature 테이블 2단계: 점포x분기 단위 학습 테이블 구축.

학습 단위: 개별 점포 x 분기 (관측분기 B). 라벨은 B+1/B+2 시점 폐업여부.
예측 확률은 이후 단계에서 행정동x업종으로 집계해 대시보드에 쓴다(이번 스크립트 범위 아님).

데이터 누수 방지 원칙 (반드시 지킬 것):
  - 모든 feature는 관측분기 B 및 그 이전 스냅샷만 사용.
  - "폐업수(Q)"는 Q-1 스냅샷과 Q 스냅샷의 차집합으로 계산 — Q 자신의 스냅샷만 있으면
    되므로 B 시점 feature에 Q<=B로 사용해도 안전(미래 스냅샷 불필요).
  - 반면 sbiz_labels_v2.csv의 is_closed_v2는 "T, T+1, T+2 모두 확인해야" 정의되는
    라벨 전용 값이라 feature로 재사용하면 안 됨(라벨에만 사용).
  - 이동평균/추세는 항상 window 끝을 B로 고정.
  - year는 feature로 넣지 않음. 분기(Q1~Q4)만 사용.

사용법:
    python ai/build_train_table.py
"""
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pyproj import Transformer

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
DATASET_DIR = PROJECT_ROOT / "Hwaseong-commercial-ai-main-dataset"

ALL_PATH = PROCESSED_DATA_DIR / "sbiz_hwaseong_all.csv"
LABELS_V2_PATH = PROCESSED_DATA_DIR / "sbiz_labels_v2.csv"
SKELETON_PATH = PROCESSED_DATA_DIR / "panel_skeleton.csv"  # 1단계 산출물, 보존 재사용
CARD_MAPPED_PATH = PROCESSED_DATA_DIR / "card_sales_mapped.csv"
FLOW_PATH = DATASET_DIR / "화성시_유동인구" / "floating_pop_hwaseong.csv"
POP_PATH = DATASET_DIR / "화성시_인구동향_시계열.csv"
DONG_LIST_PATH = DATASET_DIR / "경기도_읍면동_리스트.csv"
PERMIT_DIR = DATASET_DIR / "화성시_인허가데이터"

OUT_PATH = PROCESSED_DATA_DIR / "train_table.csv"

TRANSFORMER_2097_TO_4326 = Transformer.from_crs("EPSG:2097", "EPSG:4326", always_xy=True)


# ==================== 공통 유틸 ====================

def quarter_sort_key(q: str) -> tuple:
    y, qn = q.split("Q")
    return int(y), int(qn)


def month_to_quarter(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:6])
    return f"{y}Q{(m - 1) // 3 + 1}"


_GU_PATTERN = "효행구|만세구|동탄구|병점구"


def norm_addr(s) -> str:
    """지번주소 정규화. 인허가 주소엔 2026.02 신설된 '구'(효행구/만세구/동탄구/병점구)와
    건물명/층/호 등 소진공 주소에 없는 접미사가 붙어있어, 그대로 비교하면 매칭이 거의
    안 됨(확인됨) — '경기도/화성시/구' 제거 후 첫 지번번호(숫자-숫자)까지만 남긴다."""
    if pd.isna(s):
        return ""
    s = re.sub(r"경기도|화성시|" + _GU_PATTERN, "", str(s))
    m = re.search(r"\d+(-\d+)?", s)
    if m:
        s = s[:m.end()]
    return "".join(s.split())


def haversine(lon1, lat1, lon2, lat2):
    """lon1/lat1: 배열, lon2/lat2: 스칼라(대상 하나) -> km 단위 거리 배열"""
    R = 6371.0
    lon1r, lat1r, lon2r, lat2r = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2r - lon1r
    dlat = lat2r - lat1r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


_DONG_CODE_TO_NAME = None


def dong_code_to_name_map() -> dict:
    """10자리 표준 행정동코드(경기데이터드림/카드매출/유동인구 쪽에서 씀) -> 행정동명.
    주의: sbiz_hwaseong_all.csv의 '행정동코드'는 이 표준 10자리 코드와 다른 체계(8자리)라
    코드로 직접 조인이 안 됨(확인됨) — 행정동명을 공통 키로 써야 함."""
    global _DONG_CODE_TO_NAME
    if _DONG_CODE_TO_NAME is None:
        names = pd.read_csv(DONG_LIST_PATH, encoding="cp949", dtype=str)
        names = names[names["상세주소"].str.contains("화성시", na=False)]
        _DONG_CODE_TO_NAME = dict(zip(names["읍면동코드"], names["읍면동명"]))
    return _DONG_CODE_TO_NAME


def to_date(s):
    # 인허가데이터 12종 전부 'YYYY-MM-DD' 형식 확인됨(하이픈 포함) — YYYYMMDD로 파싱하면 전부 NaT됨
    return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")


# ==================== 0. 로드 ====================

def load_base():
    print(f"[로드] {ALL_PATH}")
    all_df = pd.read_csv(ALL_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str,
        "상권업종대분류명": str, "상권업종중분류명": str, "상권업종소분류명": str,
        "지번주소": str, "기준분기": str,
    })
    all_df["경도"] = pd.to_numeric(all_df["경도"], errors="coerce")
    all_df["위도"] = pd.to_numeric(all_df["위도"], errors="coerce")

    print(f"[로드] {LABELS_V2_PATH}")
    labels_v2 = pd.read_csv(LABELS_V2_PATH, encoding="utf-8-sig", dtype={
        "상가업소번호": str, "행정동코드": str, "행정동명": str,
        "상권업종중분류명": str, "상권업종대분류명": str, "기준분기": str,
    })
    return all_df, labels_v2


QUARTERS = None  # main()에서 채움
NEXT_Q, NEXT2_Q, PREV_Q = {}, {}, {}


def build_quarter_maps(quarters):
    global QUARTERS, NEXT_Q, NEXT2_Q, PREV_Q
    QUARTERS = quarters
    NEXT_Q.clear(); NEXT2_Q.clear(); PREV_Q.clear()
    for i, q in enumerate(quarters):
        if i + 1 < len(quarters):
            NEXT_Q[q] = quarters[i + 1]
        if i + 2 < len(quarters):
            NEXT2_Q[q] = quarters[i + 2]
        if i - 1 >= 0:
            PREV_Q[q] = quarters[i - 1]


# ==================== 1. 뼈대(점포x분기) + 라벨 ====================

def build_skeleton(all_df: pd.DataFrame, labels_v2: pd.DataFrame) -> pd.DataFrame:
    print("\n[1] 학습 테이블 뼈대(점포x분기) 생성")
    train = all_df[["상가업소번호", "기준분기", "행정동코드", "행정동명",
                     "상권업종중분류명", "상권업종대분류명", "지번주소", "경도", "위도"]].copy()
    train = train.rename(columns={"기준분기": "B"})

    # label_h2: is_closed_v2 그대로(정의상 이미 "T,T+1,T+2 확인 후 폐업 확정" 값 — 라벨 전용)
    lv2 = labels_v2[["상가업소번호", "기준분기", "is_closed_v2"]].rename(
        columns={"기준분기": "B", "is_closed_v2": "label_h2"})
    train = train.merge(lv2, on=["상가업소번호", "B"], how="left")

    # label_h1: 단순 1분기 부재 규칙(v1식) — 상가업소번호가 B+1에 존재하는지만 확인
    presence_pairs = set(zip(all_df["상가업소번호"], all_df["기준분기"]))

    def label_h1_of(row):
        next_q = NEXT_Q.get(row["B"])
        if next_q is None:
            return np.nan
        return 0 if (row["상가업소번호"], next_q) in presence_pairs else 1

    train["label_h1"] = train.apply(label_h1_of, axis=1)

    print(f"  행 수: {len(train):,}, 점포 수: {train['상가업소번호'].nunique():,}, "
          f"분기 범위: {min(QUARTERS)}~{max(QUARTERS)}")
    print(f"  label_h1 결측 아님: {train['label_h1'].notna().sum():,} / label_h2 결측 아님: {train['label_h2'].notna().sum():,}")
    return train


# ==================== 2. 점포 개별 feature ====================

def add_store_age(train: pd.DataFrame) -> pd.DataFrame:
    print("\n[2] 점포 개별 feature — 업력(소진공 최초등장 기준)")
    q_idx = {q: i for i, q in enumerate(QUARTERS)}
    first_seen = train.groupby("상가업소번호")["B"].min().rename("최초등장분기")
    train = train.merge(first_seen, on="상가업소번호", how="left")
    train["업력_분기수"] = train["B"].map(q_idx) - train["최초등장분기"].map(q_idx)
    return train


def load_permits():
    print("\n  인허가 12종 통합 로드 중...")
    files = sorted(PERMIT_DIR.glob("*.csv"))
    frames = []
    for f in files:
        industry = f.stem.replace("_경기화성시", "")
        try:
            df = pd.read_csv(f, encoding="cp949", dtype=str)
        except UnicodeDecodeError:
            df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)

        area_col = next((c for c in ["소재지면적", "시설총규모", "약국영업면적", "건축물연면적"] if c in df.columns), None)
        area = pd.to_numeric(df[area_col], errors="coerce") if area_col else np.nan

        male = pd.to_numeric(df["남성종사자수"], errors="coerce") if "남성종사자수" in df.columns else 0
        female = pd.to_numeric(df["여성종사자수"], errors="coerce") if "여성종사자수" in df.columns else 0
        emp = (male if isinstance(male, pd.Series) else 0) + (female if isinstance(female, pd.Series) else 0)
        if not isinstance(emp, pd.Series):
            emp = pd.Series(np.nan, index=df.index)

        out = pd.DataFrame({
            "인허가업종": industry,
            "인허가일자": df.get("인허가일자"),
            "폐업일자": df.get("폐업일자"),
            "영업상태명": df.get("영업상태명"),
            "지번주소_norm": df["지번주소"].map(norm_addr) if "지번주소" in df.columns else "",
            "면적": area,
            "종사자수": emp,
        })
        frames.append(out)

    permits = pd.concat(frames, ignore_index=True)
    permits = permits[permits["지번주소_norm"] != ""]
    permits["인허가일자_dt"] = to_date(permits["인허가일자"])
    print(f"  통합 인허가 행 수: {len(permits):,}")
    return permits


def attach_permit_features(train: pd.DataFrame, permits: pd.DataFrame) -> pd.DataFrame:
    print("\n  인허가 매칭(지번주소 정규화 exact match) 및 업력 보정")
    train["지번주소_norm"] = train["지번주소"].map(norm_addr)

    permits_dedup = permits.dropna(subset=["지번주소_norm"]).drop_duplicates(subset="지번주소_norm", keep="first")
    match_cols = permits_dedup[["지번주소_norm", "인허가일자_dt", "면적", "종사자수"]]

    train = train.merge(match_cols, on="지번주소_norm", how="left")
    matched = train["인허가일자_dt"].notna().sum()
    print(f"  인허가 매칭 성공: {matched:,} / {len(train):,} 행 ({matched/len(train)*100:.1f}%)")

    q_idx = {q: i for i, q in enumerate(QUARTERS)}
    b_quarter_end_month = train["B"].map(lambda q: pd.Timestamp(int(q[:4]), int(q[5]) * 3, 1) + pd.offsets.MonthEnd(0))
    permit_q_idx = train["인허가일자_dt"].dt.to_period("Q").astype(str)  # 예: '2021Q3' (분기 표기 다름 주의)

    # 인허가일자를 화성시 데이터의 기준분기 문자열(YYYYQn, n=1~4 캘린더분기)로 정규화
    def date_to_our_quarter(dt):
        if pd.isna(dt):
            return None
        return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"

    train["인허가_분기"] = train["인허가일자_dt"].map(date_to_our_quarter)
    train["업력_분기수_보정"] = train["업력_분기수"]
    has_permit_q = train["인허가_분기"].isin(q_idx)
    valid = has_permit_q & (train["인허가_분기"].map(q_idx).fillna(-1) <= train["B"].map(q_idx))
    train.loc[valid, "업력_분기수_보정"] = train.loc[valid, "B"].map(q_idx) - train.loc[valid, "인허가_분기"].map(q_idx)

    train = train.drop(columns=["지번주소_norm", "인허가일자_dt", "인허가_분기"])
    return train


# ==================== 3. 소진공 상권 feature (중분류/대분류 각각) ====================

def build_market_features(all_df: pd.DataFrame, unit_col: str, prefix: str) -> pd.DataFrame:
    print(f"\n[3] 소진공 상권 feature — {prefix} 단위")
    store_sets = (
        all_df.groupby(["행정동명", unit_col, "기준분기"])["상가업소번호"]
        .apply(set).rename("점포집합").reset_index()
    )
    store_sets = store_sets.rename(columns={unit_col: "업종", "기준분기": "분기"})

    rows = []
    grouped = store_sets.groupby(["행정동명", "업종"])
    for (dong, industry), g in grouped:
        g = g.set_index("분기").reindex(QUARTERS)
        prev_set = None
        for q in QUARTERS:
            cur_set = g.loc[q, "점포집합"]
            cur_set = cur_set if isinstance(cur_set, set) else set()
            store_cnt = len(cur_set)
            if prev_set is None:
                open_cnt, close_cnt = np.nan, np.nan
            else:
                open_cnt = len(cur_set - prev_set)
                close_cnt = len(prev_set - cur_set)
            rows.append((dong, industry, q, store_cnt, open_cnt, close_cnt))
            prev_set = cur_set

    feat = pd.DataFrame(rows, columns=["행정동명", "업종", "B", f"{prefix}_점포수", f"{prefix}_개업수", f"{prefix}_폐업수"])
    feat[f"{prefix}_개업률"] = feat[f"{prefix}_개업수"] / feat[f"{prefix}_점포수"].replace(0, np.nan)
    feat[f"{prefix}_회전율"] = (feat[f"{prefix}_개업수"] + feat[f"{prefix}_폐업수"]) / feat[f"{prefix}_점포수"].replace(0, np.nan)
    feat[f"{prefix}_순증감률"] = (feat[f"{prefix}_개업수"] - feat[f"{prefix}_폐업수"]) / feat[f"{prefix}_점포수"].replace(0, np.nan)

    feat = feat.sort_values(["행정동명", "업종", "B"], key=lambda s: s if s.name != "B" else s.map(quarter_sort_key))

    def per_group(g):
        cur_closerate = (g[f"{prefix}_폐업수"] / g[f"{prefix}_점포수"].replace(0, np.nan))
        g[f"{prefix}_과거폐업률"] = g[f"{prefix}_폐업수"].expanding().sum() / g[f"{prefix}_점포수"].expanding().sum()
        g[f"{prefix}_개업률_MA2"] = g[f"{prefix}_개업률"].rolling(2, min_periods=1).mean()
        g[f"{prefix}_개업률_MA4"] = g[f"{prefix}_개업률"].rolling(4, min_periods=1).mean()
        g[f"{prefix}_순증감률_MA4"] = g[f"{prefix}_순증감률"].rolling(4, min_periods=1).mean()

        def slope(s):
            y = s.dropna().values
            if len(y) < 2:
                return np.nan
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]

        g[f"{prefix}_순증감률_추세4"] = g[f"{prefix}_순증감률"].rolling(4, min_periods=2).apply(slope, raw=False)
        return g

    # pandas 3.0: groupby(열).apply()는 그룹핑에 쓴 열을 하위 프레임에서 제외함 ->
    # 인덱스로 그룹핑해서 열 손실을 피함(반드시 필요, 안 그러면 이후 merge 키가 사라짐)
    feat = feat.set_index(["행정동명", "업종"])
    feat = feat.groupby(level=[0, 1], group_keys=False).apply(per_group)
    feat = feat.reset_index()

    dong_total = feat.groupby(["행정동명", "B"])[f"{prefix}_점포수"].transform("sum")
    feat[f"{prefix}_업종밀도"] = feat[f"{prefix}_점포수"] / dong_total.replace(0, np.nan)

    print(f"  생성 행 수: {len(feat):,}, 업종수: {feat['업종'].nunique()}")
    return feat


# ==================== 4. 인허가 기반 상권 feature (대규모점포) ====================

def load_malls():
    print("\n[4] 대규모점포 feature 준비")
    path = PERMIT_DIR / "생활_대규모점포_경기화성시.csv"
    df = pd.read_csv(path, encoding="cp949", dtype=str)
    x = pd.to_numeric(df["좌표정보(X)"], errors="coerce")
    y = pd.to_numeric(df["좌표정보(Y)"], errors="coerce")
    lon, lat = TRANSFORMER_2097_TO_4326.transform(x.values, y.values)
    df["경도"] = lon
    df["위도"] = lat
    df["인허가일자_dt"] = to_date(df["인허가일자"])
    df["폐업일자_dt"] = to_date(df.get("폐업일자"))

    dong_names_df = pd.read_csv(DONG_LIST_PATH, encoding="cp949", dtype=str)
    hwaseong_dongs = dong_names_df[dong_names_df["상세주소"].str.contains("화성시", na=False)]["읍면동명"].tolist()

    def find_dong(addr):
        if pd.isna(addr):
            return None
        for d in hwaseong_dongs:
            if d in addr:
                return d
        return None

    df["행정동명"] = df["지번주소"].map(find_dong)
    df = df.dropna(subset=["경도", "위도"])
    print(f"  대규모점포 {len(df)}개 로드, 행정동 매칭 {df['행정동명'].notna().sum()}개, 좌표변환(EPSG:2097->4326) 완료")
    return df


def attach_mall_features(train: pd.DataFrame, malls: pd.DataFrame) -> pd.DataFrame:
    q_idx = {q: i for i, q in enumerate(QUARTERS)}

    def quarter_end_date(q):
        y, qn = q.split("Q")
        return pd.Timestamp(int(y), int(qn) * 3, 1) + pd.offsets.MonthEnd(0)

    q_end = {q: quarter_end_date(q) for q in QUARTERS}
    q_start_minus4 = {q: quarter_end_date(QUARTERS[max(0, q_idx[q] - 4)]) for q in QUARTERS}

    dong_count_col = np.full(len(train), np.nan)
    recent_open_col = np.zeros(len(train), dtype=bool)
    dist_col = np.full(len(train), np.nan)

    train_b = train["B"].values
    train_dong = train["행정동명"].values
    train_lon = train["경도"].values
    train_lat = train["위도"].values

    cache = {}
    for q in QUARTERS:
        end = q_end[q]
        open_mask = (malls["인허가일자_dt"] <= end) & (malls["폐업일자_dt"].isna() | (malls["폐업일자_dt"] > end))
        open_malls = malls[open_mask]
        recent_mask = open_mask & (malls["인허가일자_dt"] > q_start_minus4[q])
        recent_open_dongs = set(malls.loc[recent_mask, "행정동명"].dropna())
        dong_counts = open_malls["행정동명"].value_counts().to_dict()
        cache[q] = (open_malls[["경도", "위도"]].dropna().values, dong_counts, recent_open_dongs)

    for i in range(len(train)):
        q = train_b[i]
        coords, dong_counts, recent_open_dongs = cache[q]
        dong = train_dong[i]
        dong_count_col[i] = dong_counts.get(dong, 0)
        recent_open_col[i] = dong in recent_open_dongs
        if len(coords) > 0 and not (np.isnan(train_lon[i]) or np.isnan(train_lat[i])):
            dists = haversine(coords[:, 0], coords[:, 1], train_lon[i], train_lat[i])
            dist_col[i] = dists.min()

    train["대규모점포_행정동내개수"] = dong_count_col
    train["대규모점포_최근4분기신규"] = recent_open_col
    train["대규모점포_최근접거리km"] = dist_col
    return train


# ==================== 5. 유동인구 share feature ====================

def build_flow_features():
    print("\n[5] 유동인구 share feature (절대값 사용 금지 — share만)")
    flow = pd.read_csv(FLOW_PATH, encoding="utf-8-sig", dtype={"STD_YM": str, "ADMDONG_CD": str})
    flow = flow[flow["WDAY_CD"] != "TOT"].copy()  # TOT 요일합과 별개 취급(검증된 이슈)
    flow["분기"] = flow["STD_YM"].map(month_to_quarter)
    flow["행정동명"] = flow["ADMDONG_CD"].map(dong_code_to_name_map())

    weekday = flow[flow["WDAY_CD"].isin(["MON", "TUE", "WED", "THU", "FRI"])]
    weekend = flow[flow["WDAY_CD"].isin(["SAT", "SUN"])]

    q_total = flow.groupby(["행정동명", "분기"])["DYNMC_POPLTN_CNT"].sum().rename("유동인구_분기합").reset_index()
    wd_sum = weekday.groupby(["행정동명", "분기"])["DYNMC_POPLTN_CNT"].sum().rename("평일합").reset_index()
    we_sum = weekend.groupby(["행정동명", "분기"])["DYNMC_POPLTN_CNT"].sum().rename("주말합").reset_index()

    feat = q_total.merge(wd_sum, on=["행정동명", "분기"], how="left").merge(we_sum, on=["행정동명", "분기"], how="left")
    feat = feat.rename(columns={"분기": "B"})

    dong_total_by_q = feat.groupby("B")["유동인구_분기합"].transform("sum")
    feat["유동인구_행정동share"] = feat["유동인구_분기합"] / dong_total_by_q
    feat["유동인구_주중주말비"] = feat["평일합"] / feat["주말합"].replace(0, np.nan)

    feat = feat.sort_values(["행정동명", "B"], key=lambda s: s if s.name != "B" else s.map(quarter_sort_key))

    def per_dong(g):
        g["유동인구_share_변화"] = g["유동인구_행정동share"].diff()

        def slope(s):
            y = s.dropna().values
            if len(y) < 2:
                return np.nan
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]

        g["유동인구_share_추세4"] = g["유동인구_행정동share"].rolling(4, min_periods=2).apply(slope, raw=False)
        return g

    # pandas 3.0: groupby(열).apply()가 그룹 열을 하위 프레임에서 제외하므로 인덱스로 그룹핑
    feat = feat.set_index("행정동명")
    feat = feat.groupby(level=0, group_keys=False).apply(per_dong)
    feat = feat.reset_index()
    print(f"  생성 행 수: {len(feat):,}")
    return feat[["행정동명", "B", "유동인구_행정동share", "유동인구_주중주말비",
                 "유동인구_share_변화", "유동인구_share_추세4"]]


# ==================== 6. 카드매출 share feature ====================

def build_card_features():
    print("\n[6] 카드매출 share feature (절대값/경계 넘는 증감률 사용 금지 — share만)")
    card = pd.read_csv(CARD_MAPPED_PATH, encoding="utf-8-sig", dtype={"행정동코드": str, "기준년월": str})
    card["분기"] = card["기준년월"].map(month_to_quarter)
    card["행정동명"] = card["행정동코드"].map(dong_code_to_name_map())

    q_agg = card.groupby(["행정동명", "공통업종", "분기"])["매출금액"].sum().reset_index()
    q_agg = q_agg.rename(columns={"분기": "B"})

    dong_q_total = q_agg.groupby(["행정동명", "B"])["매출금액"].transform("sum")
    q_agg["카드매출_행정동내구성비"] = q_agg["매출금액"] / dong_q_total.replace(0, np.nan)

    industry_q_total = q_agg.groupby(["공통업종", "B"])["매출금액"].transform("sum")
    q_agg["카드매출_업종내행정동share"] = q_agg["매출금액"] / industry_q_total.replace(0, np.nan)

    q_agg = q_agg.sort_values(["행정동명", "공통업종", "B"], key=lambda s: s if s.name != "B" else s.map(quarter_sort_key))

    def per_group(g):
        g["카드매출_구성비_변화"] = g["카드매출_행정동내구성비"].diff()

        def slope(s):
            y = s.dropna().values
            if len(y) < 2:
                return np.nan
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]

        g["카드매출_구성비_추세4"] = g["카드매출_행정동내구성비"].rolling(4, min_periods=2).apply(slope, raw=False)
        return g

    q_agg = q_agg.set_index(["행정동명", "공통업종"])
    q_agg = q_agg.groupby(level=[0, 1], group_keys=False).apply(per_group)
    q_agg = q_agg.reset_index()
    print(f"  생성 행 수: {len(q_agg):,}, 공통업종수: {q_agg['공통업종'].nunique()}")
    return q_agg[["행정동명", "공통업종", "B", "카드매출_행정동내구성비", "카드매출_업종내행정동share",
                  "카드매출_구성비_변화", "카드매출_구성비_추세4"]]


SBIZ_TO_CARD = {
    "한식": "음식점", "중식": "음식점", "일식": "음식점", "서양식": "음식점", "동남아시아": "음식점",
    "기타 간이": "음식점", "구내식당·뷔페": "음식점", "주점": "주점",
    "이용·미용": "미용", "일반 교육": "학원·교육", "기타 교육": "학원·교육",
    "의원": "의료", "병원": "의료", "기타 보건": "의료",
    "일반 숙박": "숙박", "기타 숙박": "숙박", "연료 소매": "연료판매",
    "자동차 수리·세차": "자동차", "모터사이클 수리": "자동차",
    "세탁": "수리서비스", "가전제품 수리": "수리서비스", "기타 가정용품 수리": "수리서비스",
    "컴퓨터 수리": "수리서비스", "통신장비 수리": "수리서비스",
    "식료품 소매": "식료품소매", "섬유·의복·신발 소매": "의류·잡화",
    "자동차 부품 소매": "자동차", "모터사이클 소매": "자동차", "종합 소매": "종합소매",
    "유원지·오락": "여가·스포츠", "스포츠 서비스": "여가·스포츠",
}


# ==================== 7. 전환율 ====================


def build_dong_level_conversion(card_raw_path, flow_feat: pd.DataFrame) -> pd.DataFrame:
    card = pd.read_csv(card_raw_path, encoding="utf-8-sig", dtype={"행정동코드": str, "기준년월": str})
    card["분기"] = card["기준년월"].map(month_to_quarter)
    card["행정동명"] = card["행정동코드"].map(dong_code_to_name_map())
    dong_q = card.groupby(["행정동명", "분기"])["매출금액"].sum().reset_index().rename(columns={"분기": "B"})
    total_by_q = dong_q.groupby("B")["매출금액"].transform("sum")
    dong_q["카드매출_행정동share"] = dong_q["매출금액"] / total_by_q.replace(0, np.nan)

    conv = dong_q.merge(flow_feat[["행정동명", "B", "유동인구_행정동share"]], on=["행정동명", "B"], how="inner")
    conv["전환율"] = conv["카드매출_행정동share"] / conv["유동인구_행정동share"].replace(0, np.nan)
    conv = conv.sort_values(["행정동명", "B"], key=lambda s: s if s.name != "B" else s.map(quarter_sort_key))

    def per_dong(g):
        g["전환율_변화"] = g["전환율"].diff()

        def slope(s):
            y = s.dropna().values
            if len(y) < 2:
                return np.nan
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]

        g["전환율_추세4"] = g["전환율"].rolling(4, min_periods=2).apply(slope, raw=False)
        return g

    conv = conv.set_index("행정동명")
    conv = conv.groupby(level=0, group_keys=False).apply(per_dong)
    conv = conv.reset_index()
    return conv[["행정동명", "B", "전환율", "전환율_변화", "전환율_추세4"]]


# ==================== 8. 배후(인구) / 비용(임대) feature ====================

def build_population_features():
    print("\n[8-1] 인구 feature")
    pop = pd.read_csv(POP_PATH, encoding="cp949", dtype=str)
    month_cols = [c for c in pop.columns if "월" in c]

    total = pop[(pop["5세별"] == "계") & (pop["항목"] == "총인구수[명]")].copy()
    for c in month_cols:
        total[c] = pd.to_numeric(total[c].str.replace(",", ""), errors="coerce")

    elderly_ages = ["65 - 69세", "70 - 74세", "75 - 79세", "80 - 84세", "85 - 89세", "90 - 94세"]
    elderly = pop[pop["5세별"].isin(elderly_ages) & (pop["항목"] == "총인구수[명]")].copy()
    for c in month_cols:
        elderly[c] = pd.to_numeric(elderly[c].str.replace(",", ""), errors="coerce")
    elderly_sum = elderly.groupby("행정구역(동읍면)별")[month_cols].sum()

    rows = []
    for _, r in total.iterrows():
        dong = r["행정구역(동읍면)별"]
        for c in month_cols:
            m = re.match(r"(\d{4})\.(\d{2})", c)
            if not m:
                continue
            y, mo = int(m.group(1)), int(m.group(2))
            if mo not in (3, 6, 9, 12):
                continue
            q = f"{y}Q{mo // 3}"
            pop_val = r[c]
            eld_val = elderly_sum.loc[dong, c] if dong in elderly_sum.index else np.nan
            rows.append((dong, q, pop_val, eld_val))

    df = pd.DataFrame(rows, columns=["행정동명", "B", "인구", "고령인구"])
    df["고령비율"] = df["고령인구"] / df["인구"].replace(0, np.nan)
    df = df.dropna(subset=["인구"]).drop_duplicates(subset=["행정동명", "B"])
    df = df.sort_values(["행정동명", "B"], key=lambda s: s if s.name != "B" else s.map(quarter_sort_key))
    df["인구_증감률"] = df.groupby("행정동명")["인구"].pct_change()
    print(f"  생성 행 수: {len(df):,} (주의: 세대수 컬럼이 원본에 없어 세대당인구는 계산 불가 — 결측 처리)")
    df["세대당인구"] = np.nan
    return df[["행정동명", "B", "인구", "고령비율", "인구_증감률", "세대당인구"]]


DONGTAN_GROUP = [f"동탄{n}동" for n in range(1, 10)]
BYEONGJEOM_GROUP = ["병점1동", "병점2동", "화산동", "진안동"]


def build_rent_features():
    print("\n[8-2] 임대료/공실률 feature (R-ONE)")
    print(f"  매핑 규칙: 동탄권({DONGTAN_GROUP}) -> 동탄2신도시/동탄센트럴파크 평균")
    print(f"           병점권({BYEONGJEOM_GROUP}) -> 병점역")
    print(f"           나머지 모든 행정동 -> 경기(광역) 값")

    vac_dir = DATASET_DIR / "임대동향 지역별 공실률"
    rent_dir = DATASET_DIR / "임대동향 지역별 임대가격지수(시계열)데이터"

    def load_wide(path, region_col_candidates=("지역", "분류")):
        df = pd.read_csv(path, encoding="cp949", dtype=str)
        reg1 = region_col_candidates[0] if region_col_candidates[0] in df.columns else region_col_candidates[1]
        reg2 = reg1 + ".1"
        df = df[~df[reg1].isin(["No", None])].copy()
        df = df[df[reg2].notna()]
        q_cols = [c for c in df.columns if "분기" in c]
        long = df.melt(id_vars=[reg2], value_vars=q_cols, var_name="분기raw", value_name="값")
        long = long.rename(columns={reg2: "지역명"})
        long["값"] = pd.to_numeric(long["값"], errors="coerce")

        def parse_q(s):
            m = re.match(r"(\d{4})년\s*(\d)분기", str(s))
            return f"{m.group(1)}Q{m.group(2)}" if m else None

        long["B"] = long["분기raw"].map(parse_q)
        return long.dropna(subset=["B", "값"])[["지역명", "B", "값"]]

    def load_series(name, glob_pattern, folder):
        parts = []
        for f in sorted(folder.glob(glob_pattern)):
            parts.append(load_wide(f))
        if not parts:
            return pd.DataFrame(columns=["지역명", "B", name])
        out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["지역명", "B"], keep="last")
        return out.rename(columns={"값": name})

    vac_small = load_series("공실률_소규모", "*소규모*.csv", vac_dir)
    vac_small_new = load_series("공실률_소규모", "*일반*.csv", vac_dir)
    vac_small = pd.concat([vac_small, vac_small_new], ignore_index=True).drop_duplicates(subset=["지역명", "B"], keep="last")

    rent_small = load_series("임대가격지수_소규모", "*소규모*.csv", rent_dir)
    rent_jip = load_series("임대가격지수_집합", "*집합*.csv", rent_dir)
    vac_jip = load_series("공실률_집합", "*집합*.csv", vac_dir)

    def region_value(region_name, b, series_df):
        row = series_df[(series_df["지역명"] == region_name) & (series_df["B"] == b)]
        if row.empty:
            return np.nan
        return row.iloc[0, -1]

    quarters = sorted(set(vac_small["B"]) | set(rent_small["B"]), key=quarter_sort_key)
    rows = []
    for q in quarters:
        gg_vac = region_value("경기", q, vac_small)
        gg_rent = region_value("경기", q, rent_small)
        bj_vac = region_value("병점역", q, vac_small)
        bj_rent = region_value("병점역", q, rent_small)
        dt_vac_vals = [region_value(r, q, vac_jip) for r in ["동탄2신도시", "동탄센트럴파크"]]
        dt_rent_vals = [region_value(r, q, rent_jip) for r in ["동탄2신도시", "동탄센트럴파크"]]
        dt_vac = np.nanmean(dt_vac_vals) if any(pd.notna(v) for v in dt_vac_vals) else np.nan
        dt_rent = np.nanmean(dt_rent_vals) if any(pd.notna(v) for v in dt_rent_vals) else np.nan
        rows.append((q, gg_vac, gg_rent, bj_vac, bj_rent, dt_vac, dt_rent))

    q_df = pd.DataFrame(rows, columns=["B", "경기_공실률", "경기_임대지수", "병점_공실률", "병점_임대지수",
                                        "동탄_공실률", "동탄_임대지수"])

    dong_names_df = pd.read_csv(DONG_LIST_PATH, encoding="cp949", dtype=str)
    hwaseong_dongs = dong_names_df[dong_names_df["상세주소"].str.contains("화성시", na=False)]["읍면동명"].unique().tolist()

    recs = []
    for dong in hwaseong_dongs:
        if dong in DONGTAN_GROUP:
            group = "동탄"
        elif dong in BYEONGJEOM_GROUP:
            group = "병점"
        else:
            group = "경기"
        for _, r in q_df.iterrows():
            recs.append((dong, r["B"], r[f"{group}_공실률"], r[f"{group}_임대지수"], group))

    out = pd.DataFrame(recs, columns=["행정동명", "B", "공실률", "임대가격지수", "임대료_매핑그룹"])
    print(f"  생성 행 수: {len(out):,}")
    return out


# ==================== 9. 시간 feature ====================

def add_seasonality(train: pd.DataFrame) -> pd.DataFrame:
    train["분기_Q"] = train["B"].str[-2:]  # 'Q1'~'Q4', 연도 정보 없음
    return train


# ==================== 검증 ====================

def run_diagnostics(train: pd.DataFrame):
    print("\n" + "=" * 80)
    print("[검증] 결측률 / 라벨 분포")
    print("=" * 80)

    feature_cols = [c for c in train.columns if c not in
                    ("상가업소번호", "B", "행정동코드", "행정동명", "지번주소", "label_h1", "label_h2")]
    miss = train[feature_cols].isna().mean().sort_values(ascending=False) * 100
    print("\n결측률 상위 15개 feature:")
    print(miss.head(15).round(1).to_string())
    over50 = miss[miss > 50]
    print(f"\n결측률 50% 초과 feature: {list(over50.index)}")

    print("\n분기별 주요 feature 결측률(시기 편중 확인용, 상위 5개 feature):")
    top_missing_cols = miss.head(5).index.tolist()
    by_q = train.groupby("B")[top_missing_cols].apply(lambda g: g.isna().mean() * 100)
    by_q = by_q.reindex(QUARTERS)
    print(by_q.round(1).to_string())

    print("\nlabel_h2 양성비율(전체):", f"{train['label_h2'].mean()*100:.2f}%")
    labeled = train.dropna(subset=["label_h2"]).copy()
    labeled["연도"] = labeled["B"].str[:4]
    print("\n연도별 label_h2 양성비율:")
    print((labeled.groupby("연도")["label_h2"].mean() * 100).round(2).to_string())
    print("\n업종별(중분류) label_h2 양성비율 상위 10개:")
    print((labeled.groupby("상권업종중분류명")["label_h2"].mean() * 100).sort_values(ascending=False).head(10).round(2).to_string())

    print(f"\n행 수: {len(train):,}, 점포수: {train['상가업소번호'].nunique():,}, "
          f"feature 개수: {len(feature_cols)}, 분기범위: {min(QUARTERS)}~{max(QUARTERS)}")


def main():
    all_df, labels_v2 = load_base()
    quarters = sorted(all_df["기준분기"].unique(), key=quarter_sort_key)
    build_quarter_maps(quarters)

    train = build_skeleton(all_df, labels_v2)
    train = add_store_age(train)

    permits = load_permits()
    train = attach_permit_features(train, permits)

    malls = load_malls()
    train = attach_mall_features(train, malls)

    jung_feat = build_market_features(all_df, "상권업종중분류명", "중분류")
    dae_feat = build_market_features(all_df, "상권업종대분류명", "대분류")

    train = train.merge(jung_feat, left_on=["행정동명", "상권업종중분류명", "B"],
                         right_on=["행정동명", "업종", "B"], how="left").drop(columns=["업종"])
    train = train.merge(dae_feat, left_on=["행정동명", "상권업종대분류명", "B"],
                         right_on=["행정동명", "업종", "B"], how="left").drop(columns=["업종"])

    # 주의: sbiz_hwaseong_all.csv의 '행정동코드'는 카드매출/유동인구가 쓰는 표준 10자리
    # 행정동코드와 체계가 달라(확인됨, 8자리 vs 10자리) 코드로 조인 불가 -> 행정동명으로 조인
    flow_feat = build_flow_features()
    train = train.merge(flow_feat, on=["행정동명", "B"], how="left")

    card_feat = build_card_features()
    train["카드매출_공통업종_후보"] = train["상권업종중분류명"].map(SBIZ_TO_CARD)
    train = train.merge(
        card_feat, left_on=["행정동명", "카드매출_공통업종_후보", "B"],
        right_on=["행정동명", "공통업종", "B"], how="left"
    ).drop(columns=["공통업종"])

    conv_feat = build_dong_level_conversion(CARD_MAPPED_PATH, flow_feat)
    train = train.merge(conv_feat, on=["행정동명", "B"], how="left")

    pop_feat = build_population_features()
    train = train.merge(pop_feat, on=["행정동명", "B"], how="left")

    rent_feat = build_rent_features()
    train = train.merge(rent_feat, on=["행정동명", "B"], how="left")

    train = add_seasonality(train)

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    train.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUT_PATH} ({len(train):,}행, {len(train.columns)}컬럼)")

    run_diagnostics(train)


if __name__ == "__main__":
    main()
