from pydantic import BaseModel, ConfigDict
from typing import Optional


class ClosureRiskItem(BaseModel):
    """조기경보(예측) — 예측 절대값은 절대 노출하지 않는다. 순위만 표시하고,
    판단 근거는 실제 관측 지표(폐업률·개업률·추세)로만 뒷받침한다."""

    model_config = ConfigDict(from_attributes=True)

    predicted_rank: int
    dong: str
    category: str
    actual_closure_rate_pct: float
    growth_prob: float
    open_rate_pct: float
    trend_slope: float
    saturation: float
    anomaly: bool
    action: str


class ClosureRateRankingItem(BaseModel):
    """상권 순위표(현황) — 실제 관측 폐업률로만 정렬, 절대 % 그대로 표시."""

    model_config = ConfigDict(from_attributes=True)

    rank: int
    dong: str
    category: str
    closure_rate_pct: float
    store_count: int


class VacancyRiskItem(BaseModel):
    """지도(현황) — 읍면동 단위 위험 업종 비율(실제값 기준), 예측값 관여 없음."""

    model_config = ConfigDict(from_attributes=True)

    dong: str
    risk_ratio: float
    risk_level: str
    color: str
    trend: float


class PolicyPriorityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dong: str
    category: str
    actual_closure_rate_pct: float
    growth_prob: float
    quadrant: int
    sample_insufficient: bool


class AnalysisDongResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dong: str
    category: Optional[str]
    quarter: int
    sales: Optional[int]
    store_count: Optional[int]
    population: Optional[int]
    closure_rate: Optional[float]
    open_rate: Optional[float]
    saturation: Optional[float]
    competition: Optional[float]


class ScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dong: str
    category: str
    growth_prob: float
    grade: str
    rank: Optional[int]
    total_dongs: Optional[int]
    top_pct: Optional[float]
    actual_closure_rate_pct: float
    risk_level: str
    predicted_rank: Optional[int]
    sample_insufficient: bool


class OfficialLoginRequest(BaseModel):
    username: str
    password: str


class CitizenLoginRequest(BaseModel):
    business_number: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    verification_type: str


class ConsultationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dong: str
    category: str
    survival_prob: float
    grade: str
    population_level: str
    competition_level: str
    saturation_level: str
    reasons: list[str]
