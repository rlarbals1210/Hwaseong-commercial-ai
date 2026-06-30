from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import CommercialData, ScoreData
from ..schemas import ConsultationResponse

router = APIRouter(prefix="/api/consultation", tags=["consultation"])


def _level(value: float, low: float, high: float) -> str:
    if value >= high:
        return "높음"
    if value >= low:
        return "보통"
    return "낮음"


@router.get("/startup", response_model=ConsultationResponse)
def get_startup_consultation(
    dong: str = Query(...),
    category: str = Query(...),
    db: Session = Depends(get_db),
):
    latest = db.query(func.max(CommercialData.기준_년분기_코드)).scalar()
    comm = (
        db.query(CommercialData)
        .filter(
            CommercialData.행정동명 == dong,
            CommercialData.통합카테고리 == category,
            CommercialData.기준_년분기_코드 == latest,
        )
        .first()
    )
    if not comm:
        raise HTTPException(status_code=404, detail="해당 지역·업종 데이터 없음")

    score_row = (
        db.query(ScoreData)
        .filter(ScoreData.행정동명 == dong, ScoreData.통합카테고리 == category)
        .order_by(ScoreData.기준_년분기_코드.desc())
        .first()
    )

    growth = score_row.성장확률 if score_row else 50.0
    grade = score_row.등급 if score_row else "C"
    survival = round(growth * 0.7 + (100 - (comm.폐업_률_평균 or 0) * 5) * 0.3, 1)
    survival = max(0.0, min(100.0, survival))

    pop = comm.총_유동인구_수 or 0
    pop_level = _level(pop, 5000, 15000)
    comp_level = _level(comm.경쟁강도 or 0, 2, 5)
    sat_level = _level(comm.업종_포화도 or 0, 0.001, 0.005)

    reasons = []
    if growth >= 60:
        reasons.append(f"AI 성장확률 {growth:.0f}% — 이 업종의 성장 가능성이 높습니다.")
    elif growth < 40:
        reasons.append(f"AI 성장확률 {growth:.0f}% — 성장 여력이 제한적입니다.")

    if pop >= 15000:
        reasons.append(f"월 유동인구 {pop:,}명 — 충분한 고객 수요가 기대됩니다.")
    elif pop < 5000:
        reasons.append(f"월 유동인구 {pop:,}명 — 유동인구가 적어 초기 마케팅이 필요합니다.")

    if (comm.경쟁강도 or 0) >= 5:
        reasons.append(f"경쟁강도 {comm.경쟁강도:.1f} — 경쟁이 치열한 상권입니다.")
    else:
        reasons.append(f"경쟁강도 {comm.경쟁강도:.1f} — 비교적 경쟁이 낮은 환경입니다.")

    if not reasons:
        reasons.append("기본 상권 데이터 기반 분석입니다.")

    return ConsultationResponse(
        dong=dong,
        category=category,
        survival_prob=survival,
        grade=grade,
        population_level=pop_level,
        competition_level=comp_level,
        saturation_level=sat_level,
        reasons=reasons[:3],
    )
