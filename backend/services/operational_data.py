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

from ..models import CommercialQuarter


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
