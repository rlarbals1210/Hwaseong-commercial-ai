"""카드매출 수요점유율을 예측하고 현재 공급과 비교한 추천 입력값을 만든다.

예측 대상은 매출액이 아니라 ``카드 업종별 화성시 매출 중 행정동 점유율``이다.
경기데이터드림 카드매출은 구·신 업종코드 전환 때 금액 스케일이 끊기지만 지역
점유율은 비교적 안정적이기 때문이다. 신코드가 안정적으로 관측된 연속 월만 쓰며,
2025년 2~6월은 모델 선택에 전혀 쓰지 않는 최종 시험 구간으로 남긴다.

산출물은 모두 읍면동 x 소진공 중분류 집계값이다. 개별 점포를 포함하지 않는다.

    python ai/train_demand_model.py
"""
from __future__ import annotations

import json
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eda.paths import (
    CARD_SALES_CSV,
    FLOATING_POP_CSV,
    GYEONGGI_DONG_LIST_CSV,
    PROCESSED_DATA_DIR,
    RAW_DIR,
)

CARD_CODE_XLSX = RAW_DIR / "공개_수요예측_원본_20260829" / "업종_중분류코드.xlsx"
FINAL_DATASET_CSV = PROCESSED_DATA_DIR / "final_dataset.csv"
INDUSTRY_HIERARCHY_CSV = PROCESSED_DATA_DIR / "industry_hierarchy.csv"

DEMAND_SCORES_CSV = PROCESSED_DATA_DIR / "demand_scores.csv"
DEMAND_RESULTS_JSON = PROCESSED_DATA_DIR / "demand_model_results.json"
DEMAND_MODEL_PKL = PROCESSED_DATA_DIR / "demand_model.pkl"

FEATURES = [
    "area_code",
    "card_code",
    "current_share",
    "previous_share",
    "rolling3_share",
    "share_momentum",
    "area_total_share",
    "floating_share",
    "category_city_share",
    "target_month_sin",
    "target_month_cos",
]

# 소진공 중분류별 가장 가까운 카드 중분류. 공식 코드표의 이름을 사람이 대조한
# 규칙이며, 인과관계나 정확한 KSIC 대응표가 아니다. 정확히 대응되지 않는 업종은
# 아래 대분류 프록시로 폴백하고 산출물의 mapping_level에 표시한다.
INDUSTRY_OVERRIDES: dict[str, tuple[str, ...]] = {
    # 음식
    "한식": ("Q15",), "중식": ("Q12",), "일식": ("Q10",), "서양식": ("Q07",),
    "동남아시아": ("Q04",), "기타 간이": ("Q03", "Q06", "Q14"),
    "비알코올": ("Q11", "Q13"), "구내식당·뷔페": ("Q05", "Q16"),
    "주점": ("Q01", "Q08"),
    # 소매
    "가구 소매": ("D10",), "가전·통신 소매": ("D01", "U03"),
    "기타 상품 소매": ("D18",), "기타 생활용품 소매": ("D10", "D18"),
    "담배 소매": ("D02",), "모터사이클 소매": ("D12", "D13"),
    "섬유·의복·신발 소매": ("D09", "D15"), "시계·귀금속 소매": ("D15",),
    "식료품 소매": ("D08",), "식물 소매": ("D18",),
    "안경·정밀기기 소매": ("D18",), "애완동물·용품 소매": ("D18",),
    "연료 소매": ("F09",), "오락용품 소매": ("D05", "D06", "D14"),
    "음료 소매": ("D08",), "의약·화장품 소매": ("D02", "D16", "S02"),
    "자동차 부품 소매": ("D12",), "장식품 소매": ("D10", "D14"),
    "종합 소매": ("D11",), "중고 상품 소매": ("D18",),
    "철물·건설자재 소매": ("D10", "D19"),
    # 수리·개인
    "가전제품 수리": ("F07",), "기타 가정용품 수리": ("F07",),
    "기타 개인": ("F14",), "모터사이클 수리": ("F10",), "세탁": ("F06",),
    "욕탕·신체관리": ("F05", "O02"), "이용·미용": ("F02",),
    "자동차 수리·세차": ("F10",), "장례식장": ("F08",),
    "컴퓨터 수리": ("F07",), "통신장비 수리": ("F07",),
    # 교육·의료·숙박·부동산
    "교육 지원": ("R03",), "기타 교육": ("R03", "R04", "R05", "R08"),
    "일반 교육": ("R01", "R02", "R06", "R07"),
    "기타 보건": ("S06",), "병원": ("S03", "S04", "S05"),
    "의원": ("S03", "S04"), "부동산 서비스": ("F04",),
    "기타 숙박": ("O01",), "일반 숙박": ("O01",),
    # 과학·기술
    "광고": ("F01",), "기술 서비스": ("F03",), "기타 전문 과학": ("F03",),
    "법무관련": ("F03",), "본사·경영 컨설팅": ("F03",), "사진 촬영": ("F01",),
    "수의": ("S01",), "시장 조사": ("F03",), "인쇄·제품제작": ("F01",),
    "전문 디자인": ("F03",), "회계·세무": ("F03",),
    # 시설관리·임대
    "가정용품 대여": ("F13",), "고용 알선": ("F14",),
    "기타 사업 서비스": ("F11", "F14"), "사무 지원": ("F14",),
    "산업용품 대여": ("F13",), "시설관리": ("F14",), "여행사·보조": ("F12",),
    "운송장비 대여": ("F13",), "조경·유지": ("F14",), "청소·방제": ("F14",),
    # 예술·스포츠
    "도서관·사적지": ("T01", "T04"), "스포츠 서비스": ("O03", "T03"),
    "유원지·오락": ("O04", "T02", "T04"),
}

LARGE_CATEGORY_CODES: dict[str, tuple[str, ...]] = {
    "과학·기술": ("F01", "F03", "F11", "F12", "F14"),
    "교육": tuple(f"R{i:02d}" for i in range(1, 9)),
    "보건의료": tuple(f"S{i:02d}" for i in range(1, 7)),
    "부동산": ("F04",),
    "소매": tuple(f"D{i:02d}" for i in range(1, 20)) + ("F09", "S02"),
    "수리·개인": ("F02", "F05", "F06", "F07", "F08", "F10", "O02"),
    "숙박": ("O01",),
    "시설관리·임대": ("F11", "F12", "F13", "F14"),
    "예술·스포츠": ("O02", "O03", "O04", "T01", "T02", "T03", "T04"),
    "음식": tuple(f"Q{i:02d}" for i in range(1, 17)),
}


@dataclass
class ForecastChoice:
    name: str
    blend: float
    validation_mae: float


def _cell_text(cell: ET.Element, shared: list[str], ns: dict[str, str]) -> str:
    value = cell.find("x:v", ns)
    if value is None or value.text is None:
        inline = cell.find("x:is/x:t", ns)
        return inline.text.strip() if inline is not None and inline.text else ""
    if cell.attrib.get("t") == "s":
        return shared[int(value.text)].strip()
    return value.text.strip()


def load_card_code_names(path: Path) -> dict[str, str]:
    """openpyxl 의존성 없이 공식 xlsx의 B:C 열을 읽는다."""
    if not path.exists():
        raise FileNotFoundError(f"공식 카드 업종 코드표가 없습니다: {path}")
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("x:si", ns):
                shared.append("".join(node.text or "" for node in item.findall(".//x:t", ns)))
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: dict[int, dict[str, str]] = {}
    for cell in sheet.findall(".//x:c", ns):
        ref = cell.attrib.get("r", "")
        match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
        if not match:
            continue
        col, row = match.group(1), int(match.group(2))
        rows.setdefault(row, {})[col] = _cell_text(cell, shared, ns)
    result = {
        values.get("B", ""): values.get("C", "")
        for values in rows.values()
        if re.fullmatch(r"[A-Z]\d{2}", values.get("B", ""))
    }
    if len(result) < 80:
        raise ValueError(f"카드 코드표 파싱 결과가 비정상적으로 적습니다: {len(result)}개")
    return result


def month_distance(left: str, right: str) -> int:
    return (int(right[:4]) - int(left[:4])) * 12 + int(right[4:]) - int(left[4:])


def next_month(month: str) -> str:
    period = pd.Period(f"{month[:4]}-{month[4:]}", freq="M") + 1
    return period.strftime("%Y%m")


def current_area_codes() -> tuple[list[str], dict[str, str]]:
    final = pd.read_csv(FINAL_DATASET_CSV, usecols=["행정동명"], dtype=str)
    area_names = set(final["행정동명"].dropna().unique())
    dongs = pd.read_csv(GYEONGGI_DONG_LIST_CSV, encoding="cp949", dtype=str)
    # 2026년 화성시 구 신설로 같은 읍면동명에 신·구 코드가 함께 들어 있다. 카드매출
    # 최신월에 실제 등장한 코드를 골라야 봉담읍 같은 지역이 두 번 잡히지 않는다.
    card_codes = pd.read_csv(CARD_SALES_CSV, usecols=["STD_YM", "ADMDONG_CD"], dtype=str)
    latest_month = card_codes["STD_YM"].max()
    latest_area_codes = set(card_codes.loc[card_codes["STD_YM"] == latest_month, "ADMDONG_CD"])
    dongs = dongs[
        dongs["읍면동명"].isin(area_names) & dongs["읍면동코드"].isin(latest_area_codes)
    ].drop_duplicates("읍면동명")
    mapping = dict(zip(dongs["읍면동코드"], dongs["읍면동명"]))
    if set(mapping.values()) != area_names:
        missing = sorted(area_names - set(mapping.values()))
        raise ValueError(f"행정동 코드 매핑 누락: {missing}")
    return sorted(mapping), mapping


def load_panel(card_code_names: dict[str, str]) -> tuple[pd.DataFrame, dict[str, pd.Series], dict]:
    area_codes, _ = current_area_codes()
    official_codes = set(card_code_names)
    card = pd.read_csv(
        CARD_SALES_CSV,
        dtype={"STD_YM": str, "ADMDONG_CD": str, "MDCLASS_INDUTYPE_CD": str},
    )
    card["SALES_AMT"] = pd.to_numeric(card["SALES_AMT"], errors="coerce").fillna(0.0)
    active = card[card["MDCLASS_INDUTYPE_CD"].isin(official_codes)].copy()
    month_coverage = active.groupby("STD_YM").agg(
        code_count=("MDCLASS_INDUTYPE_CD", "nunique"),
        area_count=("ADMDONG_CD", "nunique"),
    )
    usable_months = sorted(
        month_coverage[(month_coverage.code_count >= 80) & (month_coverage.area_count == len(area_codes))].index
    )
    active = active[active["STD_YM"].isin(usable_months) & active["ADMDONG_CD"].isin(area_codes)]
    card_codes = sorted(active["MDCLASS_INDUTYPE_CD"].unique())

    amounts = active.groupby(["STD_YM", "ADMDONG_CD", "MDCLASS_INDUTYPE_CD"])["SALES_AMT"].sum()
    grid = pd.MultiIndex.from_product(
        [usable_months, area_codes, card_codes],
        names=["month", "area_code", "card_code"],
    )
    panel = amounts.reindex(grid, fill_value=0.0).rename("amount").to_frame()
    city_code_total = panel.groupby(["month", "card_code"])["amount"].transform("sum")
    panel["demand_share"] = np.where(city_code_total > 0, panel["amount"] / city_code_total, 0.0)

    # TO는 전체 카드수요의 지역 점유율 프록시다. 업종별 점유율과 별도로 지역 전체
    # 소비 중심이 이동하는 방향을 모델에 알려준다.
    total = card[
        (card["MDCLASS_INDUTYPE_CD"] == "TO")
        & card["STD_YM"].isin(usable_months)
        & card["ADMDONG_CD"].isin(area_codes)
    ].groupby(["STD_YM", "ADMDONG_CD"])["SALES_AMT"].sum()
    area_total_share: dict[str, pd.Series] = {}
    for month in usable_months:
        values = total.xs(month).reindex(area_codes, fill_value=0.0)
        area_total_share[month] = values / values.sum() if values.sum() else values

    flow = pd.read_csv(FLOATING_POP_CSV, dtype={"STD_YM": str, "ADMDONG_CD": str})
    flow["DYNMC_POPLTN_CNT"] = pd.to_numeric(flow["DYNMC_POPLTN_CNT"], errors="coerce").fillna(0.0)
    flow = flow[(flow["WDAY_CD"] == "TOT") & flow["ADMDONG_CD"].isin(area_codes)]
    flow_series = flow.groupby(["STD_YM", "ADMDONG_CD"])["DYNMC_POPLTN_CNT"].sum()
    floating_share: dict[str, pd.Series] = {}
    for month in usable_months:
        if month not in flow_series.index.get_level_values(0):
            floating_share[month] = area_total_share[month]
            continue
        values = flow_series.xs(month).reindex(area_codes, fill_value=0.0)
        floating_share[month] = values / values.sum() if values.sum() else area_total_share[month]

    city_totals = panel.groupby(["month", "card_code"])["amount"].sum()
    city_code_share: dict[str, pd.Series] = {}
    for month in usable_months:
        values = city_totals.xs(month).reindex(card_codes, fill_value=0.0)
        city_code_share[month] = values / values.sum() if values.sum() else values

    auxiliary = {
        "usable_months": usable_months,
        "area_codes": area_codes,
        "card_codes": card_codes,
        "area_total_share": area_total_share,
        "floating_share": floating_share,
        "city_code_share": city_code_share,
        "city_totals": city_totals,
        "coverage": month_coverage.reset_index().to_dict(orient="records"),
    }
    return panel, auxiliary, {"raw_rows": len(card), "active_rows": len(active)}


def contiguous_history(month: str, usable: set[str], limit: int = 3) -> list[str]:
    history = [month]
    cursor = month
    while len(history) < limit:
        previous = (pd.Period(f"{cursor[:4]}-{cursor[4:]}", freq="M") - 1).strftime("%Y%m")
        if previous not in usable:
            break
        history.append(previous)
        cursor = previous
    return history


def source_features(panel: pd.DataFrame, aux: dict, source_month: str) -> pd.DataFrame:
    usable = set(aux["usable_months"])
    current = panel.xs(source_month, level="month")["demand_share"]
    history = contiguous_history(source_month, usable, limit=3)
    previous = panel.xs(history[1], level="month")["demand_share"] if len(history) > 1 else current
    rolling = pd.concat(
        [panel.xs(month, level="month")["demand_share"] for month in history], axis=1
    ).mean(axis=1)
    frame = current.rename("current_share").to_frame().reset_index()
    frame["previous_share"] = previous.to_numpy()
    frame["rolling3_share"] = rolling.to_numpy()
    frame["share_momentum"] = frame["current_share"] - frame["rolling3_share"]
    frame["area_total_share"] = frame["area_code"].map(aux["area_total_share"][source_month])
    frame["floating_share"] = frame["area_code"].map(aux["floating_share"][source_month])
    frame["category_city_share"] = frame["card_code"].map(aux["city_code_share"][source_month])
    target = next_month(source_month)
    target_number = int(target[4:])
    frame["target_month_sin"] = math.sin(2 * math.pi * target_number / 12)
    frame["target_month_cos"] = math.cos(2 * math.pi * target_number / 12)
    frame["source_month"] = source_month
    frame["target_month"] = target
    return frame


def build_supervised(panel: pd.DataFrame, aux: dict) -> pd.DataFrame:
    usable = aux["usable_months"]
    usable_set = set(usable)
    rows: list[pd.DataFrame] = []
    for month in usable:
        target = next_month(month)
        if target not in usable_set:
            continue
        frame = source_features(panel, aux, month)
        frame["target_share"] = panel.xs(target, level="month")["demand_share"].to_numpy()
        rows.append(frame)
    if not rows:
        raise ValueError("연속된 신코드 월이 없어 학습 테이블을 만들 수 없습니다")
    return pd.concat(rows, ignore_index=True)


def feature_matrix(frame: pd.DataFrame, aux: dict) -> pd.DataFrame:
    matrix = frame[FEATURES].copy()
    matrix["area_code"] = pd.Categorical(matrix["area_code"], categories=aux["area_codes"])
    matrix["card_code"] = pd.Categorical(matrix["card_code"], categories=aux["card_codes"])
    return matrix


def normalize_predictions(frame: pd.DataFrame, predictions: np.ndarray) -> np.ndarray:
    work = frame[["target_month", "card_code"]].copy()
    work["prediction"] = np.clip(np.asarray(predictions, dtype=float), 0.0, None)
    totals = work.groupby(["target_month", "card_code"])["prediction"].transform("sum")
    group_sizes = work.groupby(["target_month", "card_code"])["prediction"].transform("size")
    return np.asarray(np.where(totals > 0, work["prediction"] / totals, 1.0 / group_sizes))


def evaluate(frame: pd.DataFrame, predictions: np.ndarray) -> dict[str, float]:
    truth = frame["target_share"].to_numpy(dtype=float)
    pred = normalize_predictions(frame, predictions)
    maes = float(np.mean(np.abs(truth - pred)))
    correlations: list[float] = []
    top5: list[float] = []
    for _, indexes in frame.groupby(["target_month", "card_code"], observed=True).groups.items():
        idx = np.asarray(list(indexes), dtype=int)
        actual_group, pred_group = truth[idx], pred[idx]
        if np.unique(actual_group).size > 1 and np.unique(pred_group).size > 1:
            correlations.append(float(spearmanr(actual_group, pred_group).statistic))
        n = min(5, len(idx))
        actual_top = set(np.argsort(actual_group)[-n:])
        pred_top = set(np.argsort(pred_group)[-n:])
        top5.append(len(actual_top & pred_top) / n)
    return {
        "mae": maes,
        "mean_spearman": float(np.nanmean(correlations)),
        "mean_top5_overlap": float(np.mean(top5)),
    }


def fit_lgbm(train: pd.DataFrame, valid: pd.DataFrame, aux: dict) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(
        objective="regression_l1",
        n_estimators=800,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=120,
        subsample=0.9,
        colsample_bytree=0.85,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbosity=-1,
    )
    model.fit(
        feature_matrix(train, aux),
        train["target_share"],
        eval_set=[(feature_matrix(valid, aux), valid["target_share"])],
        categorical_feature=["area_code", "card_code"],
        callbacks=[lgb.early_stopping(80, verbose=False), lgb.log_evaluation(0)],
    )
    return model


def best_blend(
    valid: pd.DataFrame,
    candidate: np.ndarray,
    *,
    candidate_name: str,
) -> ForecastChoice:
    persistence = valid["current_share"].to_numpy(dtype=float)
    choices: list[ForecastChoice] = []
    for blend in np.linspace(0.0, 1.0, 21):
        pred = (1.0 - blend) * persistence + blend * candidate
        choices.append(ForecastChoice(candidate_name, float(blend), evaluate(valid, pred)["mae"]))
    return min(choices, key=lambda item: item.validation_mae)


def mapping_for(industry_name: str, large_name: str, official_codes: set[str]) -> tuple[list[str], str]:
    direct = [code for code in INDUSTRY_OVERRIDES.get(industry_name, ()) if code in official_codes]
    if direct:
        return direct, "중분류 직접 대응"
    fallback = [code for code in LARGE_CATEGORY_CODES.get(large_name, ()) if code in official_codes]
    if not fallback:
        raise ValueError(f"카드 업종 매핑이 없습니다: {large_name} > {industry_name}")
    return fallback, "대분류 프록시"


def build_demand_scores(
    forecast_frame: pd.DataFrame,
    forecast_share: np.ndarray,
    aux: dict,
    area_names: dict[str, str],
    *,
    model_name: str,
    gate_passed: bool,
) -> pd.DataFrame:
    forecast = forecast_frame[["area_code", "card_code"]].copy()
    forecast["forecast_share"] = forecast_share
    recent_months = contiguous_history(forecast_frame["source_month"].iloc[0], set(aux["usable_months"]), 3)
    recent_city_total = (
        aux["city_totals"].loc[recent_months]
        .groupby("card_code")
        .mean()
        .reindex(aux["card_codes"], fill_value=0.0)
    )
    forecast["city_weight"] = forecast["card_code"].map(recent_city_total).fillna(0.0)
    forecast["demand_proxy"] = forecast["forecast_share"] * forecast["city_weight"]

    hierarchy = pd.read_csv(INDUSTRY_HIERARCHY_CSV, dtype=str)
    final = pd.read_csv(
        FINAL_DATASET_CSV,
        usecols=["행정동명", "통합카테고리", "기준_년분기_코드", "점포수"],
    )
    latest_quarter = int(final["기준_년분기_코드"].max())
    supply = final[final["기준_년분기_코드"] == latest_quarter].copy()
    supply["점포수"] = pd.to_numeric(supply["점포수"], errors="coerce").fillna(0.0)
    large_by_industry = dict(zip(hierarchy["중분류명"], hierarchy["대분류명"]))
    official_codes = set(aux["card_codes"])
    rows: list[dict] = []
    for industry_name, group in supply.groupby("통합카테고리"):
        large_name = large_by_industry[industry_name]
        codes, mapping_level = mapping_for(
            str(industry_name).strip(), str(large_name).strip(), official_codes
        )
        demand = (
            forecast[forecast["card_code"].isin(codes)]
            .groupby("area_code")["demand_proxy"]
            .sum()
        )
        demand = demand / demand.sum() if demand.sum() else demand
        industry_supply_total = group["점포수"].sum()
        for record in group.itertuples(index=False):
            area_code = next((code for code, name in area_names.items() if name == record.행정동명), None)
            if area_code is None:
                continue
            demand_share = float(demand.get(area_code, 0.0))
            supply_share = float(record.점포수 / industry_supply_total) if industry_supply_total else 0.0
            gap_log = math.log((demand_share + 1e-6) / (supply_share + 1e-6))
            rows.append({
                "행정동명": record.행정동명,
                "통합카테고리": industry_name,
                "수요공급격차_log": gap_log,
                "예측수요점유율": demand_share,
                "현재공급점유율": supply_share,
                "점포수": int(record.점포수),
                "카드업종코드": "|".join(codes),
                "매핑수준": mapping_level,
                "예측기준년월": forecast_frame["source_month"].iloc[0],
                "예측대상년월": forecast_frame["target_month"].iloc[0],
                "공급기준분기": latest_quarter,
                "선택모델": model_name,
                "검증통과": gate_passed,
            })
    result = pd.DataFrame(rows)
    result["수요공급점수"] = result.groupby("통합카테고리")["수요공급격차_log"].rank(
        method="average", pct=True
    ) * 100
    return result.sort_values(["통합카테고리", "수요공급점수"], ascending=[True, False])


def main() -> None:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    code_names = load_card_code_names(CARD_CODE_XLSX)
    panel, aux, audit = load_panel(code_names)
    supervised = build_supervised(panel, aux)

    train = supervised[supervised["target_month"] <= "202212"].copy().reset_index(drop=True)
    valid = supervised[
        (supervised["target_month"] >= "202301") & (supervised["target_month"] <= "202307")
    ].copy().reset_index(drop=True)
    test = supervised[
        (supervised["target_month"] >= "202502") & (supervised["target_month"] <= "202506")
    ].copy().reset_index(drop=True)
    if min(len(train), len(valid), len(test)) == 0:
        raise ValueError(
            f"시간 분할 중 빈 구간이 있습니다: train={len(train)}, valid={len(valid)}, test={len(test)}"
        )

    baseline_valid = evaluate(valid, valid["current_share"].to_numpy())
    rolling_choice = best_blend(
        valid,
        valid["rolling3_share"].to_numpy(),
        candidate_name="rolling_mean_blend",
    )
    model = fit_lgbm(train, valid, aux)
    valid_model_pred = model.predict(feature_matrix(valid, aux), num_iteration=model.best_iteration_)
    lgbm_choice = best_blend(valid, valid_model_pred, candidate_name="lightgbm_blend")
    selected = min([rolling_choice, lgbm_choice], key=lambda item: item.validation_mae)

    if selected.name == "lightgbm_blend":
        test_candidate = model.predict(feature_matrix(test, aux), num_iteration=model.best_iteration_)
    else:
        test_candidate = test["rolling3_share"].to_numpy()
    test_prediction = (
        (1.0 - selected.blend) * test["current_share"].to_numpy()
        + selected.blend * test_candidate
    )
    baseline_test = evaluate(test, test["current_share"].to_numpy())
    selected_test = evaluate(test, test_prediction)
    mae_improvement = (baseline_test["mae"] - selected_test["mae"]) / baseline_test["mae"]
    gate_passed = bool(
        selected.blend >= 0.10
        and mae_improvement >= 0.005
        and selected_test["mean_spearman"] >= baseline_test["mean_spearman"] - 0.005
        and selected_test["mean_top5_overlap"] >= baseline_test["mean_top5_overlap"] - 0.02
    )

    # 최종 예측은 검증 완료 후 모든 연속 신코드 월을 다시 학습한다. 모델 선택과
    # 혼합비는 시험 구간을 보기 전에 validation에서 확정한 값을 그대로 쓴다.
    source_month = max(aux["usable_months"])
    forecast_frame = source_features(panel, aux, source_month)
    fitted_model = None
    if selected.name == "lightgbm_blend":
        best_iterations = max(50, int(model.best_iteration_ or 300))
        fitted_model = lgb.LGBMRegressor(
            objective="regression_l1",
            n_estimators=best_iterations,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=120,
            subsample=0.9,
            colsample_bytree=0.85,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            verbosity=-1,
        )
        fitted_model.fit(
            feature_matrix(supervised, aux),
            supervised["target_share"],
            categorical_feature=["area_code", "card_code"],
        )
        forecast_candidate = fitted_model.predict(feature_matrix(forecast_frame, aux))
    else:
        forecast_candidate = forecast_frame["rolling3_share"].to_numpy()
    raw_forecast = (
        (1.0 - selected.blend) * forecast_frame["current_share"].to_numpy()
        + selected.blend * forecast_candidate
    )
    forecast_share = normalize_predictions(forecast_frame, raw_forecast)

    _, area_names = current_area_codes()
    scores = build_demand_scores(
        forecast_frame,
        forecast_share,
        aux,
        area_names,
        model_name=selected.name,
        gate_passed=gate_passed,
    )
    scores.to_csv(DEMAND_SCORES_CSV, index=False, encoding="utf-8-sig")

    results = {
        "method_version": "demand-share-v1",
        "target_definition": "다음 달 카드 업종별 화성시 매출 중 행정동 점유율",
        "source_month": source_month,
        "forecast_target_month": next_month(source_month),
        "usable_months": aux["usable_months"],
        "missing_card_months": [
            month
            for month in pd.period_range("2018-01", "2025-06", freq="M").strftime("%Y%m")
            if month not in pd.read_csv(CARD_SALES_CSV, usecols=["STD_YM"], dtype=str)["STD_YM"].unique()
        ],
        "splits": {
            "train_target_months": sorted(train["target_month"].unique()),
            "validation_target_months": sorted(valid["target_month"].unique()),
            "test_target_months": sorted(test["target_month"].unique()),
            "train_rows": len(train), "validation_rows": len(valid), "test_rows": len(test),
        },
        "validation": {
            "persistence": baseline_valid,
            "rolling_mean_blend": rolling_choice.__dict__,
            "lightgbm_blend": lgbm_choice.__dict__,
        },
        "test": {
            "persistence": baseline_test,
            "selected": selected_test,
            "mae_improvement_pct": mae_improvement * 100,
        },
        "selected_model": selected.__dict__,
        "deployment_gate_passed": gate_passed,
        "deployment_gate": {
            "minimum_test_mae_improvement_pct": 0.5,
            "maximum_spearman_drop": 0.005,
            "maximum_top5_overlap_drop": 0.02,
            "minimum_non_baseline_blend": 0.10,
        },
        "data_audit": {
            **audit,
            "official_card_codes": len(code_names),
            "modeled_card_codes": len(aux["card_codes"]),
            "current_admin_areas": len(aux["area_codes"]),
            "demand_score_rows": len(scores),
            "direct_mapping_industries": int((scores.groupby("통합카테고리")["매핑수준"].first() == "중분류 직접 대응").sum()),
        },
        "limitations": [
            "카드매출은 2024-02~2024-12 원본이 없어 해당 구간을 학습·보간하지 않았다.",
            "카드 업종과 소진공 업종은 공식 일대일 대응표가 없어 명칭 기반 프록시 매핑을 사용한다.",
            "점수는 매출액 예측이 아니라 지역 수요점유율과 점포점유율의 상대 격차다.",
            "2025-06 이후 공개 카드매출이 없어 예측 시점은 2025-07이며 최신 공급과 시차가 있다.",
        ],
    }
    DEMAND_RESULTS_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    joblib.dump(
        {
            "model": fitted_model,
            "features": FEATURES,
            "area_categories": aux["area_codes"],
            "card_categories": aux["card_codes"],
            "selected_model": selected.__dict__,
            "source_month": source_month,
            "forecast_target_month": next_month(source_month),
            "deployment_gate_passed": gate_passed,
        },
        DEMAND_MODEL_PKL,
    )

    print(json.dumps({
        "selected_model": selected.__dict__,
        "test_persistence": baseline_test,
        "test_selected": selected_test,
        "test_mae_improvement_pct": round(mae_improvement * 100, 3),
        "deployment_gate_passed": gate_passed,
        "scores": str(DEMAND_SCORES_CSV),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
