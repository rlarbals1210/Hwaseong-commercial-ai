"""검증된 CSV 산출물을 정규화 PostgreSQL 스키마에 이력 보존 방식으로 적재한다.

실행 전:
    # 기존 DB는 최초 1회 baseline stamp 후 신규 테이블 생성
    alembic stamp 20260818_0000
    alembic upgrade head

    # 신규 DB는 바로 전체 migration 실행
    alembic upgrade head

사용법:
    python ai/import_normalized_db.py

기존 import_to_db.py의 TRUNCATE 방식과 달리 관측 팩트는 복합키 upsert, 모델 결과는
model_run별 append/upsert한다. 예측 절대값은 내부 감사용으로만 저장하며 API에서 노출하지 않는다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cumulative as cum  # noqa: E402
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import engine  # noqa: E402
from backend.models import (  # noqa: E402
    AdminArea,
    AreaQuarterSummary,
    CommercialQuarter,
    DataBatch,
    IndustryCategory,
    ModelRun,
    PolicyProgram,
    RiskPrediction,
    RiskThresholdSet,
)
from eda import paths as eda_paths  # noqa: E402


COMMERCIAL_REQUIRED = {
    "행정동명", "통합카테고리", "기준_년분기_코드", "점포수",
    "개업_율_평균", "폐업_률_평균", "업종_포화도", "경쟁강도",
}
SCORES_REQUIRED = {
    "행정동명", "통합카테고리", "기준_년분기_코드", "성장확률", "등급",
    "업종내_순위", "업종내_전체동수", "상위_퍼센트",
}
SAMPLE_MIN = 50  # 기본값. 실제로는 risk_thresholds.json의 sample_min을 우선 사용한다.

# 동 단위 등급의 최소 분모. backend/services/risk.py의 AREA_MIN_SUFFICIENT_CELLS와
# 같은 값이어야 한다(적재값과 화면 판정이 어긋나지 않도록).
AREA_MIN_SUFFICIENT_CELLS = 5

# 등급·누적 지표 로직은 ai/cumulative.py 한 곳에만 둔다. build_risk_index.py도 같은 모듈을 쓴다.
# risk_index.csv는 .gitignore 대상이라 그 파일을 읽는 방식으로는 공유할 수 없어(팀원이 pull만
# 받으면 파일이 없다) 모듈을 공유한다. 2026-08-20에 build_risk_index만 고쳤더니 CSV는 4분기
# 누적 등급인데 화면은 단일 분기 등급이던 문제가 있었다.
THRESHOLD_REQUIRED = {
    "avg_closure_rate_pct",
    "danger_threshold_pct",
    "dong_ratio_avg_pct",
    "dong_ratio_danger_pct",
    "sample_min",
    "quarter",
    "caution_threshold_pct",
    "window_quarters",
}
POLICY_PROGRAMS = [
    # 매칭 조건(target_*)은 상권 유형별 처방 로직에서 나온 것이라 근거가 있다.
    # 자격 요건(업력·한도·신청 기간)은 실제 공고문에서 확인해야 하므로 비워 둔다.
    # requires_verification=True인 동안 화면은 "요건 확인 필요"로 표시한다.
    {
        "program_code": "SPECIAL_GUARANTEE",
        "program_name": "특례보증",
        "description": "경영안정자금 접근성 개선을 위한 보증 지원",
        "is_active": True,
        "target_cell_types": ["쇠퇴"],
        "target_risk_grades": ["위험", "주의"],
        "discouraged_cell_types": ["고회전"],
        "match_reason": "나간 자리가 채워지지 않는 상권에서 개별 점포의 자금 접근성을 높입니다.",
        "requires_verification": True,
    },
    {
        "program_code": "BUSINESS_ENVIRONMENT",
        "program_name": "경영환경개선",
        "description": "점포 시설·홍보·경영환경 개선 지원",
        "is_active": True,
        "target_cell_types": ["쇠퇴", "정체"],
        "target_risk_grades": ["위험", "주의", "안정"],
        "discouraged_cell_types": [],
        "match_reason": "시설·환경 노후가 이탈 요인일 수 있는 상권에 해당합니다.",
        "requires_verification": True,
    },
    {
        "program_code": "DISTRICT_REVITALIZATION",
        "program_name": "상권 활성화",
        "description": "공동 마케팅·행사·공간 개선 등 상권 단위 지원",
        "is_active": True,
        "target_cell_types": ["쇠퇴", "정체"],
        "target_risk_grades": ["위험", "주의"],
        "discouraged_cell_types": ["고회전"],
        "match_reason": "개별 점포가 아니라 상권 단위로 유입을 늘려야 하는 경우입니다.",
        "requires_verification": True,
    },
    {
        "program_code": "NEW_POLICY_REVIEW",
        "program_name": "신규 정책 검토",
        "description": "기존 사업으로 대응하기 어려운 확인 원인에 대한 신규 정책 검토",
        "is_active": True,
        "target_cell_types": ["고회전", "정체"],
        "target_risk_grades": ["위험", "주의"],
        "discouraged_cell_types": [],
        "match_reason": "기존 사업의 틀로는 대응이 어려운 구조라 별도 검토가 필요합니다.",
        "requires_verification": True,
    },
]


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} 필수 컬럼 누락: {missing}")


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"인코딩 판별 실패: {path}")


def _stable_fallback_code(prefix: str, value: str, length: int) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest().upper()
    return f"{prefix}{digest}"[:length]


def _quarter_add(code: int, count: int) -> int:
    year, quarter = divmod(int(code), 10)
    offset = year * 4 + quarter - 1 + count
    return (offset // 4) * 10 + (offset % 4) + 1


def _slope(values: pd.Series) -> float:
    clean = values.dropna().astype(float).to_numpy()
    if len(clean) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(clean)), clean, 1)[0])


def _build_latest_signals(
    commercial: pd.DataFrame, scores: pd.DataFrame, sample_min: int = SAMPLE_MIN
) -> pd.DataFrame:
    latest = int(commercial["기준_년분기_코드"].max())
    quarters = sorted(commercial["기준_년분기_코드"].unique())[-4:]
    slopes = (
        commercial[commercial["기준_년분기_코드"].isin(quarters)]
        .sort_values("기준_년분기_코드")
        .groupby(["행정동명", "통합카테고리"])["누적폐업률_pct"]
        .apply(_slope)
        .reset_index(name="trend_slope")
    )
    slope_std = float(slopes["trend_slope"].std())
    slopes["anomaly_flag"] = slopes["trend_slope"] > slope_std

    latest_fact = commercial[commercial["기준_년분기_코드"] == latest][
        ["행정동명", "통합카테고리", "점포수"]
    ]
    result = scores.merge(latest_fact, on=["행정동명", "통합카테고리"], how="left")
    result = result.merge(slopes, on=["행정동명", "통합카테고리"], how="left")
    result["sample_insufficient"] = result["점포수"].fillna(0) < sample_min
    result["predicted_closure_rate_internal"] = ((100 - result["성장확률"]) / 100).clip(0, 1)
    result["predicted_rank"] = pd.NA
    ok = ~result["sample_insufficient"]
    result.loc[ok, "predicted_rank"] = (
        result.loc[ok, "predicted_closure_rate_internal"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    return result


def _supplement_score_only_cells(
    commercial: pd.DataFrame, scores: pd.DataFrame, cell_table_path: Path
) -> pd.DataFrame:
    """직전 분기 셀이 없어 트레일링 비율이 미산출된 최신 예측 셀을 점포수 팩트로 보존한다."""
    key = ["행정동명", "통합카테고리"]
    latest = int(commercial["기준_년분기_코드"].max())
    current = commercial[commercial["기준_년분기_코드"] == latest][key]
    missing = scores[key].merge(current, on=key, how="left", indicator=True)
    missing = missing[missing["_merge"] == "left_only"][key]
    if missing.empty:
        return commercial

    cell = _read_csv(cell_table_path)
    quarter_label = f"{latest // 10}Q{latest % 10}"
    cell = cell[cell["기준분기"] == quarter_label].rename(
        columns={"상권업종중분류명": "통합카테고리"}
    )
    missing = missing.merge(cell[[*key, "점포수"]], on=key, how="left", validate="one_to_one")
    if missing["점포수"].isna().any():
        unresolved = missing.loc[missing["점포수"].isna(), key].to_dict("records")
        raise ValueError(f"cell_train_table에서 최신 예측 셀 점포수를 찾지 못했습니다: {unresolved}")

    # final_dataset.csv에 컬럼이 추가돼도 여기서 다시 KeyError가 나지 않도록,
    # 채울 컬럼을 하드코딩하지 않고 commercial의 스키마에서 자동으로 맞춘다.
    # (2026-08-20: fix_opening_rate.py가 개업_율_보정 계열 4개를 추가하면서 실제로 터졌던 지점)
    # 점포수와 키 컬럼은 이미 채워져 있고, 나머지 지표는 직전 분기가 없어 산출 불가하므로 NaN.
    additions = missing.assign(기준_년분기_코드=latest)
    for column in commercial.columns:
        if column not in additions.columns:
            additions[column] = np.nan
    combined = pd.concat([commercial, additions[commercial.columns]], ignore_index=True)
    current_mask = combined["기준_년분기_코드"] == latest
    current_total = combined.loc[current_mask].groupby("행정동명")["점포수"].transform("sum")
    combined.loc[current_mask, "업종_포화도"] = combined.loc[current_mask, "업종_포화도"].fillna(
        combined.loc[current_mask, "점포수"] / current_total
    )
    combined.loc[current_mask, "경쟁강도"] = combined.loc[current_mask, "경쟁강도"].fillna(
        (current_total - combined.loc[current_mask, "점포수"]) / combined.loc[current_mask, "점포수"]
    )
    return combined


def _nullable_float(value) -> float | None:
    return None if pd.isna(value) else float(value)


def _load_thresholds(path: Path, latest_quarter: int) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"위험 기준선 파일이 없습니다: {path}. ai/build_risk_index.py를 먼저 실행하세요."
        )
    thresholds = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(THRESHOLD_REQUIRED - set(thresholds))
    if missing:
        raise ValueError(f"risk_thresholds.json 필수 키 누락: {missing}")
    if int(thresholds["quarter"]) != latest_quarter:
        raise ValueError(
            "위험 기준선 분기가 최신 상권 분기와 다릅니다: "
            f"{thresholds['quarter']} != {latest_quarter}"
        )
    return thresholds


def _cell_risk_grade(
    cumulative_pct: float | None,
    sample_insufficient: bool,
    caution_pct: float,
    danger_pct: float,
) -> str | None:
    """등급은 4분기 누적 폐업률로 판정한다(단일 분기가 아니다).

    기준선은 그 분기 표본충분 셀의 분위수라 절대 임계가 아니라 화성시 내 상대 순위다.
    신뢰하한은 정렬에만 쓰고 등급에는 쓰지 않는다 — 등급은 관측 사실이어야 감사에 방어된다.
    """
    if sample_insufficient:
        return "표본부족"
    if cumulative_pct is None or pd.isna(cumulative_pct):
        return None
    return cum.grade(cumulative_pct, True, danger_pct, caution_pct)


def _area_risk_grade(ratio_pct: float, avg_pct: float, danger_pct: float) -> str:
    if ratio_pct >= danger_pct:
        return "위험"
    if ratio_pct >= avg_pct:
        return "주의"
    return "안정"


def _upsert(
    session: Session,
    model,
    rows: list[dict],
    key_columns: list[str],
    update_columns: list[str],
    chunk_size: int = 1000,
) -> None:
    if not rows:
        return
    table = model.__table__
    dialect = session.get_bind().dialect.name
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        if dialect == "postgresql":
            stmt = postgres_insert(table).values(chunk)
        elif dialect == "sqlite":
            stmt = sqlite_insert(table).values(chunk)
        else:
            for row in chunk:
                existing = session.query(model).filter_by(**{k: row[k] for k in key_columns}).one_or_none()
                if existing is None:
                    session.add(model(**row))
                else:
                    for column in update_columns:
                        setattr(existing, column, row[column])
            session.flush()
            continue
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c[column] for column in key_columns],
            set_={column: getattr(stmt.excluded, column) for column in update_columns},
        )
        session.execute(stmt)


def _area_rows(area_names: list[str]) -> list[dict]:
    code_df = _read_csv(eda_paths.GYEONGGI_DONG_LIST_CSV, dtype=str)
    code_df = code_df.drop_duplicates("읍면동명")
    lookup = code_df.set_index("읍면동명").to_dict("index")
    rows = []
    for name in sorted(area_names):
        raw = lookup.get(name, {})
        registered = str(raw.get("등록일자", ""))
        valid_from = f"{registered[:4]}-{registered[4:6]}" if len(registered) >= 6 else None
        area_type = "읍" if name.endswith("읍") else "면" if name.endswith("면") else "동"
        rows.append({
            "area_code": str(raw.get("읍면동코드") or _stable_fallback_code("A", name, 10)),
            "area_name": name,
            "area_type": area_type,
            "valid_from": valid_from,
            "valid_to": None,
            "is_current": True,
        })
    return rows


def _industry_rows(industry_names: list[str]) -> list[dict]:
    codes = _read_csv(eda_paths.SBIZ_CATEGORY_CODE_CSV, dtype=str)
    codes = codes[["중분류코드", "중분류명"]].drop_duplicates("중분류명")
    lookup = codes.set_index("중분류명")["중분류코드"].to_dict()
    return [
        {
            "source_system": "sbiz",
            "industry_code": lookup.get(name, _stable_fallback_code("M", name, 20)),
            "industry_name": name,
            "level": "medium",
            "is_active": True,
        }
        for name in sorted(industry_names)
    ]


def _file_checksum(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_normalized(
    session: Session,
    commercial_path: Path,
    scores_path: Path,
    cell_table_path: Path,
    metrics_path: Path,
    model_artifact_path: Path,
    thresholds_path: Path,
    model_version: str = "phase6-cell-lgbm",
) -> dict:
    required_tables = {
        "admin_areas",
        "industry_categories",
        "commercial_quarters",
        "model_runs",
        "risk_threshold_sets",
        "area_quarter_summaries",
    }
    missing_tables = required_tables - set(inspect(session.get_bind()).get_table_names())
    if missing_tables:
        raise RuntimeError(f"Alembic migration이 필요합니다. 누락 테이블: {sorted(missing_tables)}")

    commercial = _read_csv(commercial_path)
    scores = _read_csv(scores_path)
    _require_columns(commercial, COMMERCIAL_REQUIRED, commercial_path.name)
    _require_columns(scores, SCORES_REQUIRED, scores_path.name)

    commercial_key = ["행정동명", "통합카테고리", "기준_년분기_코드"]
    if commercial.duplicated(commercial_key).any():
        raise ValueError("final_dataset.csv에 행정동×업종×분기 중복키가 있습니다")
    if scores.duplicated(commercial_key).any():
        raise ValueError("scores.csv에 행정동×업종×분기 중복키가 있습니다")

    latest = int(commercial["기준_년분기_코드"].max())
    thresholds = _load_thresholds(thresholds_path, latest)
    sample_min = int(thresholds["sample_min"])
    if set(scores["기준_년분기_코드"].astype(int).unique()) != {latest}:
        raise ValueError("scores.csv는 final_dataset.csv의 최신 분기 한 개만 포함해야 합니다")
    commercial = _supplement_score_only_cells(commercial, scores, cell_table_path)
    commercial = cum.add_cumulative(commercial, int(thresholds.get("window_quarters", cum.WINDOW)))
    # 유형은 최신 분기에만 매긴다. 과거 분기는 기준 중위값이 달라 비교 의미가 없다.
    latest_quarter = int(commercial["기준_년분기_코드"].max())
    typed = cum.add_cell_type(
        commercial[commercial["기준_년분기_코드"] == latest_quarter], sample_min
    )
    cell_type_lookup = {
        (r.행정동명, r.통합카테고리): r.상권유형 for r in typed.itertuples(index=False)
    }
    signals = _build_latest_signals(commercial, scores, sample_min)
    signal_lookup = signals.set_index(["행정동명", "통합카테고리"]).to_dict("index")

    _upsert(
        session, AdminArea, _area_rows(commercial["행정동명"].unique().tolist()),
        ["area_code"], ["area_name", "area_type", "valid_from", "valid_to", "is_current"],
    )
    _upsert(
        session, IndustryCategory, _industry_rows(commercial["통합카테고리"].unique().tolist()),
        ["source_system", "industry_code"], ["industry_name", "level", "is_active"],
    )
    session.flush()
    areas = {row.area_name: row.id for row in session.query(AdminArea).filter(AdminArea.is_current.is_(True))}
    industries = {
        row.industry_name: row.id
        for row in session.query(IndustryCategory).filter(IndustryCategory.source_system == "sbiz")
    }

    batch_key = f"sbiz-gapfill-t11-{latest}"
    batch_rows = [{
        "batch_key": batch_key,
        "source_name": "소상공인시장진흥공단 분기 스냅샷",
        "method_version": "gapfill-t11-trailing-stats-v1",
        "source_start_quarter": int(commercial["기준_년분기_코드"].min()),
        "source_end_quarter": latest,
        "row_count": int(len(commercial)),
        "quality_notes": "2023Q1 원천 결함을 threshold=11 갭필링 패널로 보정",
    }]
    _upsert(
        session, DataBatch, batch_rows, ["batch_key"],
        ["source_name", "method_version", "source_start_quarter", "source_end_quarter", "row_count", "quality_notes"],
    )
    session.flush()
    batch_id = session.query(DataBatch.id).filter(DataBatch.batch_key == batch_key).scalar()

    threshold_rows = [{
        "batch_id": batch_id,
        "quarter_code": latest,
        "avg_closure_rate_pct": float(thresholds["avg_closure_rate_pct"]),
        "danger_threshold_pct": float(thresholds["danger_threshold_pct"]),
        "area_ratio_avg_pct": float(thresholds["dong_ratio_avg_pct"]),
        "area_ratio_danger_pct": float(thresholds["dong_ratio_danger_pct"]),
        "caution_threshold_pct": float(thresholds["caution_threshold_pct"]),
        "window_quarters": int(thresholds.get("window_quarters", cum.WINDOW)),
        "method": str(thresholds.get("method", "cumulative_quantile")),
        "sample_min": sample_min,
        "computed_at": datetime.now(timezone.utc),
    }]
    _upsert(
        session,
        RiskThresholdSet,
        threshold_rows,
        ["batch_id", "quarter_code"],
        [
            "avg_closure_rate_pct",
            "danger_threshold_pct",
            "area_ratio_avg_pct",
            "area_ratio_danger_pct",
            "caution_threshold_pct",
            "window_quarters",
            "method",
            "sample_min",
            "computed_at",
        ],
    )
    session.flush()
    threshold_set_id = (
        session.query(RiskThresholdSet.id)
        .filter(
            RiskThresholdSet.batch_id == batch_id,
            RiskThresholdSet.quarter_code == latest,
        )
        .scalar()
    )

    commercial_rows = []
    for row in commercial.itertuples(index=False):
        signal = signal_lookup.get((row.행정동명, row.통합카테고리), {}) if row.기준_년분기_코드 == latest else {}
        closure_rate = _nullable_float(row.폐업_률_평균)
        is_latest = int(row.기준_년분기_코드) == latest
        sample_insufficient = int(row.점포수) < sample_min
        commercial_rows.append({
            "area_id": areas[row.행정동명],
            "industry_id": industries[row.통합카테고리],
            "quarter_code": int(row.기준_년분기_코드),
            "store_count": int(row.점포수),
            "opening_rate": _nullable_float(row.개업_율_평균),
            "closure_rate": closure_rate,
            "closure_rate_cum4": _nullable_float(
                row.누적폐업률_pct / 100 if pd.notna(row.누적폐업률_pct) else None
            ),
            "closure_rate_lower4": _nullable_float(
                row.위험도_하한_pct / 100 if pd.notna(row.위험도_하한_pct) else None
            ),
            "closure_count_cum4": (
                int(row.누적폐업건수) if pd.notna(row.누적폐업건수) else None
            ),
            "saturation_rate": _nullable_float(row.업종_포화도),
            "competition_index": _nullable_float(row.경쟁강도),
            "trend_slope": float(signal.get("trend_slope", 0.0)) if signal else None,
            "anomaly_flag": bool(signal.get("anomaly_flag", False)),
            "risk_grade": _cell_risk_grade(
                row.누적폐업률_pct,
                sample_insufficient,
                float(thresholds["caution_threshold_pct"]),
                float(thresholds["danger_threshold_pct"]),
            ) if is_latest else None,
            "cell_type": cell_type_lookup.get((row.행정동명, row.통합카테고리)) if is_latest else None,
            "sample_insufficient": sample_insufficient,
            "threshold_set_id": threshold_set_id if is_latest else None,
            "batch_id": batch_id,
        })
    _upsert(
        session, CommercialQuarter, commercial_rows,
        ["area_id", "industry_id", "quarter_code"],
        [
            "store_count",
            "opening_rate",
            "closure_rate",
            "closure_rate_cum4",
            "closure_rate_lower4",
            "closure_count_cum4",
            "saturation_rate",
            "competition_index",
            "trend_slope",
            "anomaly_flag",
            "risk_grade",
            "cell_type",
            "sample_insufficient",
            "threshold_set_id",
            "batch_id",
        ],
    )
    session.flush()

    latest_rows = [row for row in commercial_rows if row["quarter_code"] == latest]
    summary_rows = []
    for area_id in sorted({row["area_id"] for row in latest_rows}):
        cells = [row for row in latest_rows if row["area_id"] == area_id]
        sufficient = [row for row in cells if not row["sample_insufficient"]]
        risk_cells = sum(row["risk_grade"] == "위험" for row in sufficient)
        # 분모가 0이면 비율은 "0%"가 아니라 "산출 불가"다. risk_industry_ratio_pct 컬럼이
        # NOT NULL이라 값 자체는 0.0으로 두되, 등급은 아래에서 None으로 보류한다.
        ratio = round(risk_cells / len(sufficient) * 100, 1) if sufficient else 0.0
        # 표본충분 셀이 적으면 비율이 노이즈다. 3개 중 2개가 위험이면 66.7%가 되어 기준선
        # 34.64%를 훌쩍 넘는다 — 지도에서 가장 빨간 두 동이 그렇게 만들어지고 있었다
        # (동탄8동 2/3, 새솔동 4/6. 2026-08-25 감사). 5개 미만은 판정을 보류하고, 5~9개는
        # 판정하되 화면이 흐리게 칠한다(backend/services/risk.py의 AREA_THIN_EVIDENCE_CELLS).
        judged = len(sufficient) >= AREA_MIN_SUFFICIENT_CELLS
        slopes = [
            row["trend_slope"]
            for row in sufficient
            if row["trend_slope"] is not None
        ]
        summary_rows.append({
            "area_id": area_id,
            "quarter_code": latest,
            "total_cells": len(cells),
            "sample_sufficient_cells": len(sufficient),
            "risk_cells": risk_cells,
            "risk_industry_ratio_pct": ratio,
            "area_risk_grade": _area_risk_grade(
                ratio,
                float(thresholds["dong_ratio_avg_pct"]),
                float(thresholds["dong_ratio_danger_pct"]),
            ) if judged else None,
            "avg_trend_slope": float(np.mean(slopes)) if slopes else None,
            "threshold_set_id": threshold_set_id,
            "batch_id": batch_id,
        })
    _upsert(
        session,
        AreaQuarterSummary,
        summary_rows,
        ["area_id", "quarter_code"],
        [
            "total_cells",
            "sample_sufficient_cells",
            "risk_cells",
            "risk_industry_ratio_pct",
            "area_risk_grade",
            "avg_trend_slope",
            "threshold_set_id",
            "batch_id",
        ],
    )
    session.flush()

    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    run_key = f"cell-lightgbm-{model_version}-{latest}"
    session.query(ModelRun).filter(ModelRun.is_active.is_(True), ModelRun.run_key != run_key).update(
        {ModelRun.is_active: False}, synchronize_session=False
    )
    run_rows = [{
        "run_key": run_key,
        "model_name": "LightGBM cell closure-rate regressor",
        "model_version": model_version,
        "observation_quarter": latest,
        "prediction_horizon_quarters": 2,
        "train_end_quarter": 20232,
        "validation_end_quarter": 20242,
        "metrics": metrics,
        "artifact_path": str(model_artifact_path),
        "artifact_checksum": _file_checksum(model_artifact_path),
        "status": "ready",
        "is_active": True,
    }]
    _upsert(
        session, ModelRun, run_rows, ["run_key"],
        ["model_name", "model_version", "observation_quarter", "prediction_horizon_quarters", "train_end_quarter", "validation_end_quarter", "metrics", "artifact_path", "artifact_checksum", "status", "is_active"],
    )
    session.flush()
    model_run_id = session.query(ModelRun.id).filter(ModelRun.run_key == run_key).scalar()

    latest_cells = {
        (area_id, industry_id): cell_id
        for cell_id, area_id, industry_id in session.query(
            CommercialQuarter.id, CommercialQuarter.area_id, CommercialQuarter.industry_id
        ).filter(CommercialQuarter.quarter_code == latest)
    }
    prediction_rows = []
    for row in signals.itertuples(index=False):
        cell_id = latest_cells[(areas[row.행정동명], industries[row.통합카테고리])]
        predicted_rank = None if pd.isna(row.predicted_rank) else int(row.predicted_rank)
        prediction_rows.append({
            "model_run_id": model_run_id,
            "commercial_quarter_id": cell_id,
            "target_quarter_code": _quarter_add(latest, 2),
            "predicted_closure_rate_internal": float(row.predicted_closure_rate_internal),
            "predicted_rank": predicted_rank,
            "grade": str(row.등급),
            "industry_rank": int(row.업종내_순위),
            "industry_total_areas": int(row.업종내_전체동수),
            "top_percent": float(row.상위_퍼센트),
            "sample_insufficient": bool(row.sample_insufficient),
        })
    _upsert(
        session, RiskPrediction, prediction_rows,
        ["model_run_id", "commercial_quarter_id"],
        ["target_quarter_code", "predicted_closure_rate_internal", "predicted_rank", "grade", "industry_rank", "industry_total_areas", "top_percent", "sample_insufficient"],
    )
    _upsert(
        session, PolicyProgram, POLICY_PROGRAMS, ["program_code"],
        [
            "program_name", "description", "is_active",
            "target_cell_types", "target_risk_grades", "discouraged_cell_types",
            "match_reason", "requires_verification",
        ],
    )
    session.commit()

    return {
        "areas": len(areas),
        "industries": len(industries),
        "commercial_quarters": len(commercial_rows),
        "threshold_sets": len(threshold_rows),
        "area_quarter_summaries": len(summary_rows),
        "predictions": len(prediction_rows),
        "ranked_predictions": sum(row["predicted_rank"] is not None for row in prediction_rows),
        "latest_quarter": latest,
        "model_run": run_key,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commercial", type=Path, default=PROJECT_ROOT / "data/processed/final_dataset.csv")
    parser.add_argument("--scores", type=Path, default=PROJECT_ROOT / "data/processed/scores.csv")
    parser.add_argument("--cell-table", type=Path, default=PROJECT_ROOT / "data/processed/cell_train_table.csv")
    parser.add_argument("--metrics", type=Path, default=PROJECT_ROOT / "data/processed/model_cell_results.json")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "data/processed/lgbm_model_cell.pkl")
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=PROJECT_ROOT / "data/processed/risk_thresholds.json",
    )
    parser.add_argument("--model-version", default="phase6-cell-lgbm")
    args = parser.parse_args()

    with Session(engine) as session:
        result = import_normalized(
            session,
            args.commercial,
            args.scores,
            args.cell_table,
            args.metrics,
            args.model,
            args.thresholds,
            args.model_version,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
