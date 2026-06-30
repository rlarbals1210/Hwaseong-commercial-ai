from pydantic import BaseModel, ConfigDict
from typing import Optional


class ClosureRiskItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    dong: str
    category: str
    risk_score: float
    growth_prob: float
    closure_rate: float
    anomaly: bool
    action: str


class VacancyRiskItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dong: str
    score: float
    risk_level: str
    color: str
    trend: float


class PolicyPriorityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dong: str
    category: str
    risk_score: float
    growth_prob: float
    quadrant: int


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
    risk_score: float


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
