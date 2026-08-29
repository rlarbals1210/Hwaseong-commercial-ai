"""폐업 조기경보 실험용 과거 수요 피처를 시점 누수 없이 생성한다.

카드매출 원본이 연속된 분기 말에 한해, 해당 월까지 알 수 있었던 정보만으로
다음 달의 카드 업종별 행정동 수요점유율을 예측한다. 예측값은 같은 분기의
소진공 점포점유율과 비교해 읍면동 x 중분류 집계 피처로 저장한다.

현재 공개 원본은 2024-02~2024-12가 비어 있어 운영 폐업모델 학습에는 쓰지
않는다. 이 스크립트의 산출물은 데이터 연결과 피처 방향성을 검증하기 위한
연구용이며, ``운영적용가능`` 값은 감사 JSON의 데이터 게이트로 결정한다.

    python ai/build_historical_demand_features.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.train_demand_model import (
    CARD_CODE_XLSX,
    FINAL_DATASET_CSV,
    INDUSTRY_HIERARCHY_CSV,
    best_blend,
    build_supervised,
    contiguous_history,
    current_area_codes,
    load_card_code_names,
    load_panel,
    mapping_for,
    next_month,
    normalize_predictions,
    source_features,
)
from eda.paths import CARD_SALES_CSV, PROCESSED_DATA_DIR, RAW_DIR

HISTORICAL_FEATURES_CSV = PROCESSED_DATA_DIR / "demand_features_historical.csv"
HISTORICAL_AUDIT_JSON = PROCESSED_DATA_DIR / "demand_features_historical_audit.json"

# 과거 성능을 두 달만 보고 혼합비를 고르면 우연에 과적합되기 쉽다. 최소 세 개
# target month 전까지는 단순 현재 점유율(persistence)을 사용한다.
MIN_SELECTION_TARGET_MONTHS = 3

# 운영 폐업모델의 시간 분할. 이 구간 중 validation에 수요 피처가 존재해야만
# 기존 모델과 공정하게 비교할 수 있다.
CLOSURE_TRAIN_END = 20232
CLOSURE_VALID_END = 20242
MIN_ELIGIBLE_QUARTERS = 12
MIN_VALIDATION_QUARTERS = 2
MAPPING_REVIEWED = False


@dataclass(frozen=True)
class AsOfChoice:
    method: str
    rolling_blend: float
    validation_mae: float | None
    history_target_months: tuple[str, ...]


def month_to_quarter_code(month: str) -> int:
    """YYYYMM을 기존 파이프라인의 YYYYQ 정수(예: 20221)로 바꾼다."""
    year, month_number = int(month[:4]), int(month[4:])
    return year * 10 + ((month_number - 1) // 3 + 1)


def previous_quarter_code(quarter_code: int) -> int:
    year, quarter = divmod(int(quarter_code), 10)
    return (year - 1) * 10 + 4 if quarter == 1 else year * 10 + quarter - 1


def eligible_source_months(usable_months: list[str], available_quarters: set[int]) -> list[str]:
    """3개월 연속 관측이 있고 같은 분기 공급이 있는 분기 말만 반환한다."""
    usable = set(usable_months)
    return [
        month
        for month in usable_months
        if month[4:] in {"03", "06", "09", "12"}
        and len(contiguous_history(month, usable, limit=3)) == 3
        and month_to_quarter_code(month) in available_quarters
    ]


def select_asof_blend(supervised: pd.DataFrame, source_month: str) -> AsOfChoice:
    """source_month까지 정답이 드러난 월만으로 rolling 혼합비를 고른다."""
    history = supervised[supervised["target_month"] <= source_month].copy().reset_index(drop=True)
    target_months = tuple(sorted(history["target_month"].unique()))
    if len(target_months) < MIN_SELECTION_TARGET_MONTHS:
        return AsOfChoice("persistence_fallback", 0.0, None, target_months)

    choice = best_blend(
        history,
        history["rolling3_share"].to_numpy(dtype=float),
        candidate_name="expanding_rolling_mean_blend",
    )
    return AsOfChoice(choice.name, choice.blend, choice.validation_mae, target_months)


def _normalise_area_distribution(values: pd.Series, area_codes: list[str]) -> pd.Series:
    result = values.reindex(area_codes, fill_value=0.0).astype(float)
    total = float(result.sum())
    return result / total if total > 0 else result


def _mapped_distribution(
    signal: pd.DataFrame,
    codes: list[str],
    signal_column: str,
    area_codes: list[str],
) -> pd.Series:
    values = (
        signal[signal["card_code"].isin(codes)]
        .groupby("area_code")[signal_column]
        .sum()
    )
    return _normalise_area_distribution(values, area_codes)


def _prepare_supply(final: pd.DataFrame) -> pd.DataFrame:
    supply = final[["행정동명", "통합카테고리", "기준_년분기_코드", "점포수"]].copy()
    supply["기준_년분기_코드"] = pd.to_numeric(
        supply["기준_년분기_코드"], errors="raise"
    ).astype(int)
    supply["점포수"] = pd.to_numeric(supply["점포수"], errors="coerce").fillna(0.0)
    totals = supply.groupby(["기준_년분기_코드", "통합카테고리"])["점포수"].transform("sum")
    supply["공급점유율"] = np.where(totals > 0, supply["점포수"] / totals, 0.0)
    supply["전분기코드"] = supply["기준_년분기_코드"].map(previous_quarter_code)
    previous = supply[
        ["행정동명", "통합카테고리", "기준_년분기_코드", "공급점유율"]
    ].rename(columns={
        "기준_년분기_코드": "전분기코드",
        "공급점유율": "전분기공급점유율",
    })
    supply = supply.merge(
        previous,
        on=["행정동명", "통합카테고리", "전분기코드"],
        how="left",
        validate="one_to_one",
    )
    supply = supply.drop(columns="전분기코드")
    supply["공급점유율_전분기변화"] = supply["공급점유율"] - supply["전분기공급점유율"]
    return supply


def _build_quarter_features(
    source_month: str,
    forecast_frame: pd.DataFrame,
    forecast_share: np.ndarray,
    choice: AsOfChoice,
    aux: dict,
    area_names: dict[str, str],
    supply: pd.DataFrame,
    large_by_industry: dict[str, str],
) -> pd.DataFrame:
    quarter = month_to_quarter_code(source_month)
    quarter_supply = supply[supply["기준_년분기_코드"] == quarter].copy()
    name_to_code = {name: code for code, name in area_names.items()}

    recent_months = contiguous_history(source_month, set(aux["usable_months"]), limit=3)
    recent_city_total = (
        aux["city_totals"].loc[recent_months]
        .groupby("card_code")
        .mean()
        .reindex(aux["card_codes"], fill_value=0.0)
    )
    signal = forecast_frame[["area_code", "card_code", "current_share", "rolling3_share"]].copy()
    signal["forecast_share"] = forecast_share
    signal["city_weight"] = signal["card_code"].map(recent_city_total).fillna(0.0)
    for column in ("forecast_share", "current_share", "rolling3_share"):
        signal[f"{column}_weighted"] = signal[column] * signal["city_weight"]

    official_codes = set(aux["card_codes"])
    rows: list[dict] = []
    for industry_name, group in quarter_supply.groupby("통합카테고리", sort=True):
        large_name = large_by_industry[str(industry_name)]
        codes, mapping_level = mapping_for(
            str(industry_name).strip(), str(large_name).strip(), official_codes
        )
        distributions = {
            "예측수요점유율": _mapped_distribution(
                signal, codes, "forecast_share_weighted", aux["area_codes"]
            ),
            "현재수요점유율": _mapped_distribution(
                signal, codes, "current_share_weighted", aux["area_codes"]
            ),
            "최근3개월평균수요점유율": _mapped_distribution(
                signal, codes, "rolling3_share_weighted", aux["area_codes"]
            ),
        }
        for record in group.itertuples(index=False):
            area_code = name_to_code.get(record.행정동명)
            if area_code is None:
                continue
            forecast_demand = float(distributions["예측수요점유율"].get(area_code, 0.0))
            current_demand = float(distributions["현재수요점유율"].get(area_code, 0.0))
            rolling_demand = float(
                distributions["최근3개월평균수요점유율"].get(area_code, 0.0)
            )
            demand_momentum = current_demand - rolling_demand
            supply_change = (
                float(record.공급점유율_전분기변화)
                if pd.notna(record.공급점유율_전분기변화)
                else np.nan
            )
            rows.append({
                "행정동명": record.행정동명,
                "통합카테고리": industry_name,
                "기준_년분기_코드": quarter,
                "예측기준년월": source_month,
                "예측대상년월": next_month(source_month),
                "예측수요점유율": forecast_demand,
                "현재수요점유율": current_demand,
                "최근3개월평균수요점유율": rolling_demand,
                "수요모멘텀_3개월": demand_momentum,
                "공급점유율": float(record.공급점유율),
                "전분기공급점유율": (
                    float(record.전분기공급점유율)
                    if pd.notna(record.전분기공급점유율)
                    else np.nan
                ),
                "공급점유율_전분기변화": supply_change,
                "수요공급격차_log": math.log(
                    (forecast_demand + 1e-6) / (float(record.공급점유율) + 1e-6)
                ),
                "수요감소_공급증가_플래그": bool(
                    demand_momentum < 0 and pd.notna(supply_change) and supply_change > 0
                ),
                "점포수": int(record.점포수),
                "카드업종코드": "|".join(codes),
                "매핑수준": mapping_level,
                "예측방법": choice.method,
                "rolling_혼합비": choice.rolling_blend,
                "혼합비선택_과거월수": len(choice.history_target_months),
                "연구용": True,
            })
    return pd.DataFrame(rows)


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _fresh_download_audit() -> dict:
    download_dir = RAW_DIR / "공개_수요예측_원본_20260829" / "카드매출_행정동_집계_20250918"
    zip_path = download_dir / "카드매출_행정동_집계.zip"
    csv_path = download_dir / "extracted" / "카드매출_행정동_집계.csv"
    result = {
        "source_page": (
            "https://data.gg.go.kr/portal/data/service/"
            "selectServicePage.do?infId=H92OOSWZXICJM0UO4IHH38259217&infSeq=1"
        ),
        "downloaded_zip": _portable_path(zip_path, RAW_DIR),
        "downloaded_zip_sha256": _sha256(zip_path),
        "downloaded_csv": _portable_path(csv_path, RAW_DIR),
        "fresh_file_available": csv_path.exists(),
        "page_data_basis_date": "2025-09-18",
        "page_update_date": "2025-10-14",
    }
    if not csv_path.exists():
        return result
    fresh = pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        usecols=["std_ym", "admdong_cd", "mdclass_indutype_cd", "sales_amt"],
        dtype={"std_ym": str, "admdong_cd": str, "mdclass_indutype_cd": str},
    )
    hwaseong = fresh[fresh["admdong_cd"].str.startswith("41590", na=False)].copy()
    observed_months = set(hwaseong["std_ym"].unique())
    full_months = pd.period_range("2018-01", "2025-06", freq="M").strftime("%Y%m")
    result.update({
        "statewide_rows": len(fresh),
        "hwaseong_rows": len(hwaseong),
        "hwaseong_first_month": str(hwaseong["std_ym"].min()),
        "hwaseong_last_month": str(hwaseong["std_ym"].max()),
        "hwaseong_area_codes": int(hwaseong["admdong_cd"].nunique()),
        "hwaseong_card_codes": int(hwaseong["mdclass_indutype_cd"].nunique()),
        "hwaseong_missing_months": [month for month in full_months if month not in observed_months],
    })

    working = pd.read_csv(
        CARD_SALES_CSV,
        dtype={"STD_YM": str, "ADMDONG_CD": str, "MDCLASS_INDUTYPE_CD": str},
    )
    working["SALES_AMT"] = pd.to_numeric(working["SALES_AMT"], errors="coerce")
    fresh_hwaseong = hwaseong.rename(columns={
        "std_ym": "STD_YM",
        "admdong_cd": "ADMDONG_CD",
        "mdclass_indutype_cd": "MDCLASS_INDUTYPE_CD",
        "sales_amt": "SALES_AMT_fresh",
    })
    fresh_hwaseong["SALES_AMT_fresh"] = pd.to_numeric(
        fresh_hwaseong["SALES_AMT_fresh"], errors="coerce"
    )
    keys = ["STD_YM", "ADMDONG_CD", "MDCLASS_INDUTYPE_CD"]
    comparison = working.merge(
        fresh_hwaseong[keys + ["SALES_AMT_fresh"]],
        on=keys,
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    matched = comparison[comparison["_merge"] == "both"]
    sales_delta = (matched["SALES_AMT"] - matched["SALES_AMT_fresh"]).abs()
    result["working_file_comparison"] = {
        "working_rows": len(working),
        "fresh_hwaseong_rows": len(fresh_hwaseong),
        "keys_identical": bool((comparison["_merge"] == "both").all()),
        "working_only_keys": int((comparison["_merge"] == "left_only").sum()),
        "fresh_only_keys": int((comparison["_merge"] == "right_only").sum()),
        "max_absolute_sales_delta": float(sales_delta.max()) if len(sales_delta) else None,
        "relative_total_absolute_sales_delta": (
            float(sales_delta.sum() / matched["SALES_AMT_fresh"].abs().sum())
            if len(matched) and matched["SALES_AMT_fresh"].abs().sum()
            else None
        ),
    }
    return result


def _missing_months(path: Path) -> list[str]:
    observed = set(pd.read_csv(path, usecols=["STD_YM"], dtype=str)["STD_YM"].unique())
    if not observed:
        return []
    full = pd.period_range(
        f"{min(observed)[:4]}-{min(observed)[4:]}",
        f"{max(observed)[:4]}-{max(observed)[4:]}",
        freq="M",
    ).strftime("%Y%m")
    return [month for month in full if month not in observed]


def main() -> None:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    code_names = load_card_code_names(CARD_CODE_XLSX)
    panel, aux, panel_audit = load_panel(code_names)
    supervised = build_supervised(panel, aux)
    _, area_names = current_area_codes()

    final = pd.read_csv(
        FINAL_DATASET_CSV,
        usecols=["행정동명", "통합카테고리", "기준_년분기_코드", "점포수"],
    )
    supply = _prepare_supply(final)
    hierarchy = pd.read_csv(INDUSTRY_HIERARCHY_CSV, dtype=str)
    large_by_industry = dict(zip(hierarchy["중분류명"], hierarchy["대분류명"]))
    available_quarters = set(supply["기준_년분기_코드"].unique())
    source_months = eligible_source_months(aux["usable_months"], available_quarters)

    feature_frames: list[pd.DataFrame] = []
    choices: list[dict] = []
    for source_month in source_months:
        forecast_frame = source_features(panel, aux, source_month)
        choice = select_asof_blend(supervised, source_month)
        raw_forecast = (
            (1.0 - choice.rolling_blend) * forecast_frame["current_share"].to_numpy(dtype=float)
            + choice.rolling_blend * forecast_frame["rolling3_share"].to_numpy(dtype=float)
        )
        forecast_share = normalize_predictions(forecast_frame, raw_forecast)
        quarter_features = _build_quarter_features(
            source_month,
            forecast_frame,
            forecast_share,
            choice,
            aux,
            area_names,
            supply,
            large_by_industry,
        )
        feature_frames.append(quarter_features)
        choices.append({
            "source_month": source_month,
            "quarter": month_to_quarter_code(source_month),
            **asdict(choice),
            "history_target_months": list(choice.history_target_months),
            "output_rows": len(quarter_features),
        })

    if not feature_frames:
        raise ValueError("3개월 연속 카드매출과 공급 데이터가 겹치는 분기가 없습니다")
    features = pd.concat(feature_frames, ignore_index=True)
    key_columns = ["행정동명", "통합카테고리", "기준_년분기_코드"]
    if features.duplicated(key_columns).any():
        raise ValueError("과거 수요 피처 복합키가 중복됐습니다")
    if not np.isfinite(features["수요공급격차_log"]).all():
        raise ValueError("수요공급격차에 비유한 값이 포함됐습니다")

    features = features.sort_values(key_columns).reset_index(drop=True)
    features.to_csv(HISTORICAL_FEATURES_CSV, index=False, encoding="utf-8-sig")

    quarters = sorted(int(value) for value in features["기준_년분기_코드"].unique())
    split_quarters = {
        "train": [quarter for quarter in quarters if quarter <= CLOSURE_TRAIN_END],
        "validation": [
            quarter
            for quarter in quarters
            if CLOSURE_TRAIN_END < quarter <= CLOSURE_VALID_END
        ],
        "test_or_later": [quarter for quarter in quarters if quarter > CLOSURE_VALID_END],
    }
    quarter_summary = []
    for quarter, group in features.groupby("기준_년분기_코드", sort=True):
        source_supply = supply[supply["기준_년분기_코드"] == quarter]
        quarter_summary.append({
            "quarter": int(quarter),
            "rows": len(group),
            "supply_rows": len(source_supply),
            "join_coverage_pct": len(group) / len(source_supply) * 100 if len(source_supply) else 0.0,
            "sample_ge_30_rows": int((group["점포수"] >= 30).sum()),
            "sample_ge_50_rows": int((group["점포수"] >= 50).sum()),
            "previous_supply_missing_rows": int(group["전분기공급점유율"].isna().sum()),
            "direct_mapping_industries": int(
                (group.groupby("통합카테고리")["매핑수준"].first() == "중분류 직접 대응").sum()
            ),
        })

    missing_months = _missing_months(CARD_SALES_CSV)
    production_ready = bool(
        len(quarters) >= MIN_ELIGIBLE_QUARTERS
        and len(split_quarters["validation"]) >= MIN_VALIDATION_QUARTERS
        and not missing_months
        and MAPPING_REVIEWED
    )
    blockers: list[str] = []
    if len(quarters) < MIN_ELIGIBLE_QUARTERS:
        blockers.append(
            f"연속 3개월로 생성 가능한 분기가 {len(quarters)}개뿐임(최소 {MIN_ELIGIBLE_QUARTERS}개 필요)"
        )
    if len(split_quarters["validation"]) < MIN_VALIDATION_QUARTERS:
        blockers.append(
            "기존 폐업모델 validation(2023Q3~2024Q2)에 수요 피처 분기가 없음"
        )
    if missing_months:
        blockers.append(f"카드매출 원본 결측 월 {len(missing_months)}개 존재")
    if not MAPPING_REVIEWED:
        blockers.append("카드 업종과 소진공 업종의 공식 일대일 매핑표가 없어 수기 프록시 매핑 사용")

    audit = {
        "method_version": "historical-demand-features-v1",
        "research_only": True,
        "production_ready": production_ready,
        "target_definition": "분기 말 다음 달 카드 업종별 화성시 매출 중 행정동 점유율",
        "leakage_controls": [
            "각 분기 말까지 공개된 카드매출만 사용",
            "혼합비 선택은 예측기준월까지 정답이 확인된 과거 target month만 사용",
            "공급은 예측기준월과 같은 분기의 점포수만 사용",
            "결측 2024-02~2024-12는 보간하지 않음",
        ],
        "source_files": {
            "working_card_sales": _portable_path(CARD_SALES_CSV, RAW_DIR),
            "working_card_sales_sha256": _sha256(CARD_SALES_CSV),
            "official_card_code_table": _portable_path(CARD_CODE_XLSX, RAW_DIR),
            "official_card_code_table_sha256": _sha256(CARD_CODE_XLSX),
            "fresh_official_download": _fresh_download_audit(),
        },
        "panel_audit": panel_audit,
        "usable_months": aux["usable_months"],
        "missing_months": missing_months,
        "eligible_source_months": source_months,
        "eligible_quarters": quarters,
        "closure_model_split_quarters": split_quarters,
        "asof_choices": choices,
        "quarter_summary": quarter_summary,
        "output": {
            "path": _portable_path(HISTORICAL_FEATURES_CSV, PROJECT_ROOT),
            "rows": len(features),
            "unique_areas": int(features["행정동명"].nunique()),
            "unique_industries": int(features["통합카테고리"].nunique()),
            "duplicate_keys": int(features.duplicated(key_columns).sum()),
            "research_only_all_true": bool(features["연구용"].all()),
        },
        "deployment_gate": {
            "minimum_eligible_quarters": MIN_ELIGIBLE_QUARTERS,
            "minimum_validation_quarters": MIN_VALIDATION_QUARTERS,
            "require_no_missing_months": True,
            "require_industry_mapping_review": True,
            "industry_mapping_reviewed": MAPPING_REVIEWED,
        },
        "blockers": blockers,
    }
    HISTORICAL_AUDIT_JSON.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"과거 수요 피처: {HISTORICAL_FEATURES_CSV} ({len(features):,}행)")
    print(f"가용 분기: {quarters}")
    print(f"폐업모델 분할: {split_quarters}")
    print(f"운영 적용 가능: {production_ready}")
    print(f"감사 결과: {HISTORICAL_AUDIT_JSON}")


if __name__ == "__main__":
    main()
