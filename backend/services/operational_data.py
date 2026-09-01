"""운영 DB에 실제로 반영된 데이터 현황 집계.

업로드 스테이징(``services.manual_uploads``)과 의도적으로 분리한다. 업로드는
``data/raw/manual_uploads`` 파일 시스템에만 쌓이고 이 모듈은 DB만 읽으므로,
파일을 올려도 여기 숫자는 움직이지 않는다. 공무원 화면이 "지금 서비스가 쓰는
데이터"와 "올렸지만 아직 반영 안 된 파일"을 구분해서 볼 수 있게 하는 것이 목적이다.

예측값(``risk_predictions.predicted_closure_rate_internal`` 등)은 어떤 형태로도
집계에 넣지 않는다 — 이 요약은 적재 현황이지 모델 산출물이 아니다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from ..models import (
    AreaQuarterSummary,
    CommercialQuarter,
    DataBatch,
    RiskThresholdSet,
    StoreCluster,
)


EMPTY_SUMMARY: dict[str, Any] = {
    "latest_quarter_code": None,
    "latest_quarter_label": None,
    "quarter_count": 0,
    "area_count": 0,
    "industry_count": 0,
    "analysis_cell_count": 0,
    "sample_sufficient_cell_count": 0,
}


def quarter_label_ko(code: int | None) -> str | None:
    """20254 -> '2025년 4분기'. 화면 상단 요약 카드 전용 표기다.

    ``services.risk.quarter_label``('2025Q4')과 다른 이유는 이 카드가 데이터 담당
    공무원이 처음 보는 문장형 요약이기 때문이다. 분석 화면의 축·표 라벨은 기존
    'YYYYQn'을 그대로 쓴다.
    """
    try:
        code = int(code)
    except (TypeError, ValueError):
        return None
    year, quarter = divmod(code, 10)
    if not 1 <= quarter <= 4:
        return None
    return f"{year}년 {quarter}분기"


def current_data_summary(db: Session) -> dict[str, Any]:
    """운영 DB 기준 반영 현황. 데이터가 없으면 최신 분기는 None, 나머지는 0."""
    latest = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if latest is None:
        return dict(EMPTY_SUMMARY)

    latest = int(latest)
    quarter_count = (
        db.query(func.count(distinct(CommercialQuarter.quarter_code))).scalar() or 0
    )
    area_count, industry_count, analysis_cell_count, sufficient_count = (
        db.query(
            func.count(distinct(CommercialQuarter.area_id)),
            func.count(distinct(CommercialQuarter.industry_id)),
            func.count(CommercialQuarter.id),
            # 표본충분 셀(점포수 >= sample_min)은 조기경보·등급 기준선의 모수다.
            # 총 레코드 수만 내면 이 화면의 "분석 셀"과 조기경보 화면의 "N개 셀 중
            # 상위 10%"가 다른 수를 가리켜 읽는 사람이 둘을 대조할 수 없다.
            func.sum(case((CommercialQuarter.sample_insufficient.is_(False), 1), else_=0)),
        )
        .filter(CommercialQuarter.quarter_code == latest)
        .one()
    )

    return {
        "latest_quarter_code": latest,
        "latest_quarter_label": quarter_label_ko(latest),
        "quarter_count": int(quarter_count),
        "area_count": int(area_count or 0),
        "industry_count": int(industry_count or 0),
        "analysis_cell_count": int(analysis_cell_count or 0),
        "sample_sufficient_cell_count": int(sufficient_count or 0),
    }


def operational_batches(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """운영 DB에 실제로 적재된 배치 이력.

    시각은 ``data_batches.imported_at``을 그대로 쓴다. 이 컬럼은 재적재 시
    갱신 대상에서 빠져 있어(``import_normalized_db._upsert``의 update_columns 참조)
    해당 배치가 처음 들어온 시각을 유지한다. 화면을 여는 시각으로 대체하면
    이력표가 사실과 다른 시각을 기록하게 되므로 하지 않는다.
    """
    rows = (
        db.query(DataBatch)
        .order_by(DataBatch.imported_at.desc(), DataBatch.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "batch_key": row.batch_key,
            "source_name": row.source_name,
            "method_version": row.method_version,
            "quarter_start_label": quarter_label_ko(row.source_start_quarter),
            "quarter_end_label": quarter_label_ko(row.source_end_quarter),
            "row_count": row.row_count,
            "quality_notes": row.quality_notes,
            "imported_at": row.imported_at.isoformat() if row.imported_at else None,
        }
        for row in rows
    ]


def batch_detail(db: Session, batch_key: str) -> dict[str, Any] | None:
    """이력표에서 배치 한 건을 펼쳤을 때 보여줄 상세.

    목록에 없는 것만 추가로 캔다 — 그 배치가 실제로 사용한 기준선, 분기별 셀 수,
    최신 분기의 행정동·업종 수, 점포 격자 수. **예측 산출물은 넣지 않는다**:
    ``risk_predictions``의 값은 절대값 비노출 원칙 대상이고, 이 화면은 적재
    현황을 보여주는 자리지 모델 결과를 보여주는 자리가 아니다.
    """
    batch = db.query(DataBatch).filter(DataBatch.batch_key == batch_key).one_or_none()
    if batch is None:
        return None

    quarter_rows = (
        db.query(
            CommercialQuarter.quarter_code,
            func.count(CommercialQuarter.id),
            func.sum(case((CommercialQuarter.sample_insufficient.is_(False), 1), else_=0)),
        )
        .filter(CommercialQuarter.batch_id == batch.id)
        .group_by(CommercialQuarter.quarter_code)
        .order_by(CommercialQuarter.quarter_code.desc())
        .all()
    )
    quarters = [
        {
            "quarter_code": int(code),
            "quarter_label": quarter_label_ko(code),
            "cell_count": int(total or 0),
            "sample_sufficient_cell_count": int(sufficient or 0),
        }
        for code, total, sufficient in quarter_rows
    ]

    latest = quarters[0]["quarter_code"] if quarters else None
    area_count = industry_count = 0
    if latest is not None:
        area_count, industry_count = (
            db.query(
                func.count(distinct(CommercialQuarter.area_id)),
                func.count(distinct(CommercialQuarter.industry_id)),
            )
            .filter(
                CommercialQuarter.batch_id == batch.id,
                CommercialQuarter.quarter_code == latest,
            )
            .one()
        )

    threshold = (
        db.query(RiskThresholdSet)
        .filter(RiskThresholdSet.batch_id == batch.id)
        .order_by(RiskThresholdSet.quarter_code.desc())
        .first()
    )
    thresholds = None
    if threshold is not None:
        thresholds = {
            "quarter_code": threshold.quarter_code,
            "quarter_label": quarter_label_ko(threshold.quarter_code),
            "avg_closure_rate_pct": threshold.avg_closure_rate_pct,
            "caution_threshold_pct": threshold.caution_threshold_pct,
            "danger_threshold_pct": threshold.danger_threshold_pct,
            "area_ratio_avg_pct": threshold.area_ratio_avg_pct,
            "area_ratio_danger_pct": threshold.area_ratio_danger_pct,
            "sample_min": threshold.sample_min,
            "window_quarters": threshold.window_quarters,
            "method": threshold.method,
        }

    store_cluster_count = (
        db.query(func.count(StoreCluster.id))
        .filter(StoreCluster.batch_id == batch.id)
        .scalar()
        or 0
    )
    area_summary_count = (
        db.query(func.count(AreaQuarterSummary.id))
        .filter(AreaQuarterSummary.batch_id == batch.id)
        .scalar()
        or 0
    )

    return {
        "batch_key": batch.batch_key,
        "source_name": batch.source_name,
        "method_version": batch.method_version,
        "quarter_start_label": quarter_label_ko(batch.source_start_quarter),
        "quarter_end_label": quarter_label_ko(batch.source_end_quarter),
        "row_count": batch.row_count,
        "quality_notes": batch.quality_notes,
        "imported_at": batch.imported_at.isoformat() if batch.imported_at else None,
        "retention_until": batch.retention_until.isoformat() if batch.retention_until else None,
        "quarter_count": len(quarters),
        "latest_quarter_label": quarter_label_ko(latest),
        "area_count": int(area_count or 0),
        "industry_count": int(industry_count or 0),
        "store_cluster_count": int(store_cluster_count),
        "area_summary_count": int(area_summary_count),
        "thresholds": thresholds,
        "quarters": quarters,
    }
