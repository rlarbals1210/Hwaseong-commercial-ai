"""
raw 소진공 상가정보 21개 분기 zip + 화성시 인허가데이터 -> 갭필링 패널 -> label_h2 라벨 -> feature 결합
-> store_train_table.csv / cell_train_table.csv(모델 학습용) + final_dataset.csv(CommercialData 원천)

eda/02_preprocessing.ipynb에서 검증된 로직을 그대로 이식했다. 구버전(ai/archive/build_dataset.py)
대비 두 가지가 바뀌었다:
  1. 라벨 = "다음분기 점포수 증가 여부" -> label_h2(관측분기 기준 +2분기 시점에 폐업 여부, 갭필링 기준)
  2. CommercialData/ScoreData/RiskIndex의 통합카테고리 grain = 상권업종대분류 10개 -> 중분류 74개
     (셀단위 중분류 모델이 검증된 최고 성능이라 grain을 그대로 프로덕션에 반영, DB 컬럼명은 안 바뀜)
final_dataset.csv의 트레일링 통계(점포수/개업_율_평균/폐업_률_평균)도 raw 스냅샷 단순 diff가 아니라
갭필링된 패널 기준으로 계산한다 - 2023Q1 데이터 결함(재등장률 72.1%, 실제 폐업 아님)이 그대로
폐업 급증으로 잡히는 구버전 문제를 없앤다.

사용법:
    python ai/build_dataset.py
"""
import io
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eda"))
import paths as eda_paths  # noqa: E402

GAP_FILL_THRESHOLD = 11

USECOLS = [
    "상가업소번호", "시군구코드", "행정동코드", "행정동명",
    "상권업종대분류명", "상권업종중분류명", "상권업종소분류명", "지번주소", "경도", "위도",
]
# 정규 분기말(0930) 파일이 없는 대신 발간된 비정규 날짜 -> 분기 직접 매핑
QUARTER_OVERRIDE = {"20251031": "2025Q3"}
DONGTAN_GROUP = [f"동탄{n}동" for n in range(1, 10)]
BYEONGJEOM_GROUP = ["병점1동", "병점2동", "화산동", "진안동"]

KEEP_COLS = [
    "상가업소번호", "기준분기", "행정동코드", "행정동명", "상권업종대분류명", "상권업종중분류명",
    "상권업종소분류명", "지번주소", "경도", "위도", "is_filled", "갭길이",
]


def date8_to_quarter(date8: str) -> str:
    if date8 in QUARTER_OVERRIDE:
        return QUARTER_OVERRIDE[date8]
    y, m = int(date8[:4]), int(date8[4:6])
    return f"{y}Q{(m - 1) // 3 + 1}"


def quarter_to_code(q: str) -> int:
    """'2023Q1' -> 20231 (DB 기준_년분기_코드 인코딩, 구버전 파이프라인과 동일)"""
    y, qn = int(q[:4]), int(q[5])
    return int(f"{y}{qn}")


def read_gyeonggi_csv(zf: zipfile.ZipFile, name: str) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(zf.read(name)), encoding="utf-8",
        usecols=lambda c: c in USECOLS,
        dtype={"상가업소번호": str, "시군구코드": str, "행정동코드": str},
    )


def load_snapshot(zip_path: Path) -> pd.DataFrame:
    date8 = re.search(r"(\d{8})", zip_path.stem).group(1)
    quarter = date8_to_quarter(date8)
    with zipfile.ZipFile(zip_path, metadata_encoding="cp949") as z:
        names = z.namelist()
        gg_direct = [n for n in names if "경기" in n and n.endswith(".csv")]
        if gg_direct:
            df = read_gyeonggi_csv(z, gg_direct[0])
        else:
            # 2020Q4~2022Q4: zip 안에 폴더+zip이 한 겹 더 있는 구조
            inner_name = next(n for n in names if n.endswith(".zip"))
            with zipfile.ZipFile(io.BytesIO(z.read(inner_name)), metadata_encoding="cp949") as iz:
                gg_inner = next(n for n in iz.namelist() if "경기" in n and n.endswith(".csv"))
                df = read_gyeonggi_csv(iz, gg_inner)
    df = df[df["시군구코드"] == "41590"].copy()
    df["기준분기"] = quarter
    return df


def load_all_snapshots() -> tuple[pd.DataFrame, list, dict]:
    zip_files = sorted(p for p in eda_paths.SBIZ_DIR.glob("*.zip") if not p.name.startswith("._"))
    if not zip_files:
        raise FileNotFoundError(f"상가정보 zip 없음: {eda_paths.SBIZ_DIR}")
    sbiz = pd.concat([load_snapshot(p) for p in zip_files], ignore_index=True)
    quarters = sorted(sbiz["기준분기"].unique(), key=lambda q: (int(q[:4]), int(q[5])))
    q_idx = {q: i for i, q in enumerate(quarters)}
    sbiz["idx"] = sbiz["기준분기"].map(q_idx)
    return sbiz, quarters, q_idx


def build_filled_panel(sbiz: pd.DataFrame, quarters: list, threshold: int = GAP_FILL_THRESHOLD) -> pd.DataFrame:
    """점포별 등장 분기 사이 짧은 공백(<=threshold)을 '존속 중'으로 채운다.
    threshold=11은 eda/02_preprocessing.ipynb에서 2024Q4~2025Q3 잔여 개업수 스파이크가
    가장 작아지는 값으로 검증됐다(4106->2491->1443, threshold 4/8/11 비교).
    """
    sbiz = sbiz.copy()
    sbiz["is_filled"] = 0
    sbiz["갭길이"] = np.nan
    fill_rows = []
    for store, grp in sbiz.groupby("상가업소번호"):
        grp_sorted = grp.sort_values("idx")
        idxs = grp_sorted["idx"].tolist()
        base_by_idx = {row["idx"]: row for _, row in grp_sorted.iterrows()}
        for a, b in zip(idxs, idxs[1:]):
            gap = b - a - 1
            if 0 < gap <= threshold:
                base = base_by_idx[a]
                for missing_idx in range(a + 1, b):
                    fill_rows.append({
                        "상가업소번호": store, "기준분기": quarters[missing_idx],
                        "행정동코드": base["행정동코드"], "행정동명": base["행정동명"],
                        "상권업종대분류명": base["상권업종대분류명"], "상권업종중분류명": base["상권업종중분류명"],
                        "상권업종소분류명": base["상권업종소분류명"], "지번주소": base["지번주소"],
                        "경도": base["경도"], "위도": base["위도"], "is_filled": 1, "갭길이": gap,
                    })
    fill_df = pd.DataFrame(fill_rows, columns=KEEP_COLS)
    return pd.concat([sbiz[KEEP_COLS], fill_df], ignore_index=True)


def build_trailing_stats(panel: pd.DataFrame, quarters: list) -> pd.DataFrame:
    """행정동x상권업종중분류x분기 트레일링 통계 (CommercialData 원천).
    갭필링된 패널 기준 diff라 2023Q1 데이터 결함이 인위적 폐업 급증으로 안 잡힌다.
    """
    rows = []
    prev_sets: dict[tuple, set] = {}
    for q in quarters:
        snap = panel[panel["기준분기"] == q]
        store_sets = snap.groupby(["행정동명", "상권업종중분류명"])["상가업소번호"].apply(set)
        for key, store_set in store_sets.items():
            prev_set = prev_sets.get(key)
            row = {
                "행정동명": key[0], "통합카테고리": key[1],
                "기준_년분기_코드": quarter_to_code(q), "점포수": len(store_set),
            }
            if prev_set:
                row["개업_율_평균"] = len(store_set - prev_set) / len(prev_set)
                row["폐업_률_평균"] = len(prev_set - store_set) / len(prev_set)
            rows.append(row)
        prev_sets = dict(store_sets.items())
    df = pd.DataFrame(rows)
    df = df.dropna(subset=["개업_율_평균", "폐업_률_평균"])  # 직전 분기 없는 첫 분기는 제외
    dong_total = df.groupby(["행정동명", "기준_년분기_코드"])["점포수"].transform("sum")
    df["업종_포화도"] = (df["점포수"] / dong_total.replace(0, np.nan)).round(4)
    df["경쟁강도"] = ((dong_total - df["점포수"]) / df["점포수"].replace(0, np.nan)).round(4)
    return df.sort_values(["행정동명", "통합카테고리", "기준_년분기_코드"]).reset_index(drop=True)


def build_labels(panel: pd.DataFrame, quarters: list, horizon: int = 2) -> pd.DataFrame:
    """관측분기 B에서 (갭필링 기준) B+horizon 시점에 존재하지 않으면 1. panel엔 'idx' 컬럼이 있어야 함.

    B+horizon이 데이터 범위를 벗어나는 가장 최근 horizon개 분기는 라벨을 NaN으로 두고 행은 유지한다
    (eda 노트북은 이 분기를 통째로 drop했지만, 그러면 조기경보 대시보드가 항상 실제 최신 데이터보다
    horizon분기(6개월) 뒤처진 값을 보여주게 된다 - 학습/평가에서는 dropna로 제외하고, 추론에서는 이
    최신 분기 행을 그대로 스코어링에 써서 "지금" 기준 위험도를 낸다).
    """
    max_idx = len(quarters) - 1
    present_by_idx = {i: set(g["상가업소번호"]) for i, g in panel.groupby("idx")}
    parts = []
    for idx, grp in panel.groupby("idx"):
        target_idx = idx + horizon
        grp = grp.copy()
        if target_idx > max_idx:
            grp[f"label_h{horizon}"] = np.nan
        else:
            target_set = present_by_idx[target_idx]
            grp[f"label_h{horizon}"] = (~grp["상가업소번호"].isin(target_set)).astype(float)
        parts.append(grp)
    return pd.concat(parts, ignore_index=True)


def norm_addr(s) -> str:
    if pd.isna(s):
        return ""
    s = re.sub(r"경기도|화성시|효행구|만세구|동탄구|병점구", "", str(s))
    m = re.search(r"\d+(-\d+)?", s)
    if m:
        s = s[:m.end()]
    return "".join(s.split())


def build_age_lookup(store_ids_addr: pd.DataFrame) -> pd.DataFrame:
    """상가업소번호 -> 인허가일자 기준 qoffset(년*4+분기). 화성시 인허가데이터 12종
    (학원교습소정보.csv는 스키마가 달라 자동 제외) 매칭.
    """
    permit_files = sorted(p for p in eda_paths.PERMIT_DIR.glob("*.csv") if not p.name.startswith("._"))
    permit_frames = []
    for p in permit_files:
        df = None
        for enc in ["cp949", "utf-8"]:
            try:
                df = pd.read_csv(p, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
        if df is None or "지번주소" not in df.columns or "인허가일자" not in df.columns:
            continue
        permit_frames.append(df[["지번주소", "인허가일자"]])

    permit_all = pd.concat(permit_frames, ignore_index=True)
    permit_all["지번주소_norm"] = permit_all["지번주소"].map(norm_addr)
    permit_all["인허가일자_dt"] = pd.to_datetime(permit_all["인허가일자"], format="%Y-%m-%d", errors="coerce")
    permit_all = permit_all.dropna(subset=["인허가일자_dt"])
    permit_lookup = (
        permit_all.sort_values("인허가일자_dt")
        .drop_duplicates(subset=["지번주소_norm"], keep="first")
        .set_index("지번주소_norm")["인허가일자_dt"]
    )

    store_addr = store_ids_addr.drop_duplicates("상가업소번호").copy()
    store_addr["지번주소_norm"] = store_addr["지번주소"].map(norm_addr)
    store_addr["permit_qoffset"] = store_addr["지번주소_norm"].map(permit_lookup).apply(
        lambda d: (d.year * 4 + (d.month - 1) // 3 + 1) if pd.notna(d) else np.nan
    )
    return store_addr.set_index("상가업소번호")[["permit_qoffset"]]


def rent_group(dong: str) -> str:
    if dong in DONGTAN_GROUP:
        return "동탄권"
    if dong in BYEONGJEOM_GROUP:
        return "병점권"
    return "기타"


def build_momentum(panel: pd.DataFrame, quarters: list, q_idx: dict) -> pd.DataFrame:
    """행정동x상권업종대분류 셀의 직전1분기 실제 이탈률(모멘텀, 점포단위 분류기 feature).
    B-1->B 구간만 사용하므로 label_h2(B+2 시점)와 시점이 겹치지 않는다(시간 누수 없음).
    """
    prev_sets = {
        (dong, cat, idx): set(g["상가업소번호"])
        for (dong, cat, idx), g in panel.groupby(["행정동명", "상권업종대분류명", "idx"])
    }

    def departure_rate(dong, cat, idx):
        if idx == 0:
            return np.nan
        prev = prev_sets.get((dong, cat, idx - 1), set())
        if len(prev) == 0:
            return np.nan
        cur = prev_sets.get((dong, cat, idx), set())
        return len(prev - cur) / len(prev)

    cell_keys = panel[["행정동명", "상권업종대분류명"]].drop_duplicates()
    grid = cell_keys.merge(pd.DataFrame({"idx": range(len(quarters))}), how="cross")
    grid["최근1분기이탈률"] = grid.apply(
        lambda r: departure_rate(r["행정동명"], r["상권업종대분류명"], r["idx"]), axis=1
    )
    idx_to_q = {i: q for q, i in q_idx.items()}
    grid["기준분기"] = grid["idx"].map(idx_to_q)
    return grid[["행정동명", "상권업종대분류명", "기준분기", "최근1분기이탈률"]]


def build_store_train_table(labels: pd.DataFrame, panel: pd.DataFrame, quarters: list, q_idx: dict) -> pd.DataFrame:
    age_lookup = build_age_lookup(labels[["상가업소번호", "지번주소"]])
    momentum = build_momentum(panel, quarters, q_idx)

    store_train = labels.merge(age_lookup, on="상가업소번호", how="left")
    store_train["관측분기_qoffset"] = store_train["기준분기"].map(lambda q: int(q[:4]) * 4 + int(q[5]))
    store_train["업력_분기수"] = store_train["관측분기_qoffset"] - store_train["permit_qoffset"]
    store_train["임대료_매핑그룹"] = store_train["행정동명"].map(rent_group)
    store_train = store_train.merge(momentum, on=["행정동명", "상권업종대분류명", "기준분기"], how="left")
    return store_train


def build_cell_table(store_train: pd.DataFrame) -> pd.DataFrame:
    """행정동x상권업종중분류(74종)x분기 집계. n>=30 필터는 학습 시점(train_model.py)에 적용."""
    return (
        store_train.groupby(["행정동명", "상권업종중분류명", "기준분기"])
        .agg(
            점포수=("상가업소번호", "nunique"),
            폐업률=("label_h2", "mean"),
            평균업력_분기수=("업력_분기수", "mean"),
            임대료_매핑그룹=("임대료_매핑그룹", "first"),
        )
        .reset_index()
    )


def main():
    print(f"원본 데이터 위치: {eda_paths.SBIZ_DIR}")
    print("분기별 스냅샷 로드 중...")
    sbiz, quarters, q_idx = load_all_snapshots()
    print(f"  {len(quarters)}개 분기, {len(sbiz):,}행")

    print(f"갭필링 패널 구축 중 (threshold={GAP_FILL_THRESHOLD})...")
    panel = build_filled_panel(sbiz, quarters)
    panel["idx"] = panel["기준분기"].map(q_idx)
    eda_paths.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_csv(eda_paths.STORE_PANEL_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {eda_paths.STORE_PANEL_CSV} {panel.shape}")

    print("트레일링 통계(CommercialData 원천) 집계 중...")
    final_dataset = build_trailing_stats(panel, quarters)
    final_path = eda_paths.PROCESSED_DATA_DIR / "final_dataset.csv"
    final_dataset.to_csv(final_path, index=False, encoding="utf-8-sig")
    print(f"저장: {final_path} {final_dataset.shape}")

    print("라벨(label_h2) 계산 중...")
    labels = build_labels(panel, quarters)

    print("feature 결합 중 (인허가 매칭 업력, 임대료그룹, 모멘텀)...")
    store_train = build_store_train_table(labels, panel, quarters, q_idx)
    store_train.to_csv(eda_paths.STORE_TRAIN_TABLE_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {eda_paths.STORE_TRAIN_TABLE_CSV} {store_train.shape}")

    print("셀단위(중분류) 집계 중...")
    cell_train = build_cell_table(store_train)
    cell_train.to_csv(eda_paths.CELL_TRAIN_TABLE_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {eda_paths.CELL_TRAIN_TABLE_CSV} {cell_train.shape}")

    print("완료.")


if __name__ == "__main__":
    main()
