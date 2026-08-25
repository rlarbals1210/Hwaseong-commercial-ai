from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import Field


class ClosureRiskItem(BaseModel):
    """조기경보(예측) — 예측 절대값은 절대 노출하지 않는다. 순위만 표시하고,
    판단 근거는 실제 관측 지표(폐업률·개업률·추세)로만 뒷받침한다."""

    model_config = ConfigDict(from_attributes=True)

    prediction_id: int
    predicted_rank: int
    area_id: int          # 셀 상세 페이지 링크용
    industry_id: int
    dong: str
    category: str
    # 화면에 띄우는 근거는 4분기 누적이다. 단일 분기는 점포 60곳짜리 셀에서 폐업 1~2건 차이로
    # 1.5%와 9.0%를 오가서 담당자가 신뢰할 수 없다(분기 간 순위 상관 +0.296).
    cumulative_closure_rate_pct: float   # 최근 4분기 누적 폐업률
    cumulative_closure_count: int        # 같은 창의 폐업 건수 — "23곳 닫힘" 형태로 병기
    store_count: int
    confidence_lower_pct: float          # Wilson 신뢰하한. 소표본 여부를 담당자가 가늠하는 근거
    risk_grade: str
    # 유형은 등급과 별개 축이다. 등급은 "얼마나 위험한가", 유형은 "그래서 무엇을 할 것인가".
    cell_type: str | None = None
    cell_type_summary: str | None = None
    cell_type_advice: str | None = None
    cell_type_avoid: str | None = None
    quarter_closure_rate_pct: float      # 단일 분기(참고용, 정렬·판정에 쓰지 않음)
    open_rate_pct: float
    trend_slope: float
    saturation: float
    anomaly: bool
    action: str


class ClosureRateRankingItem(BaseModel):
    """상권 순위표(현황) — 실제 관측 폐업률로만 정렬, 절대 % 그대로 표시.

    2026-08-20부터 4분기 누적 기준이다. 업종 내 순위를 함께 주는 이유는 목록이 한 업종으로
    덮이기 때문이다 — 실측에서 위험 등급 24개 중 18개가 교육 계열이었다(데이터 결함이 아니라
    학원가가 점포의 14.9%인데 폐업의 28.8%를 차지하는 실제 현상).
    """

    model_config = ConfigDict(from_attributes=True)

    rank: int
    dong: str
    category: str
    closure_rate_pct: float              # 4분기 누적 폐업률 (정렬 기준과 동일)
    cumulative_closure_count: int
    confidence_lower_pct: float
    store_count: int
    risk_grade: str
    industry_rank: int | None = None      # 같은 업종 안에서의 순위
    industry_total: int | None = None     # 같은 업종의 표본충분 셀 수


class BlindspotItem(BaseModel):
    """사각지대 — 표본이 작아 통계 판단을 보류한 셀.

    전체 점포의 38%가 여기 들어간다. 그리고 그게 서부·농촌권에 몰려 있어
    "통계가 약한 곳이 정책적으로는 더 취약한 곳"이 되는 구조다.
    버리지 않고 별도 트랙으로 뺀다.

    정렬은 폐업'률'이 아니라 폐업 '건수'다 — 점포 12곳에서 2곳이 닫히면 률은 노이즈지만
    체감은 크고, 반대로 률이 높아도 1곳이면 행정이 움직일 일이 아니다.
    """

    model_config = ConfigDict(from_attributes=True)

    area_id: int
    industry_id: int
    dong: str
    category: str
    store_count: int
    cumulative_closure_count: int
    cumulative_closure_rate_pct: float


class BlindspotResponse(BaseModel):
    notice: str
    items: list[BlindspotItem]
    total_cells: int
    total_stores: int
    total_closures: int
    store_share_pct: float          # 전체 점포 중 사각지대 비중
    sample_min: int


class VacancyRiskItem(BaseModel):
    """지도(현황) — 읍면동 단위 위험 업종 비율(실제값 기준), 예측값 관여 없음."""

    model_config = ConfigDict(from_attributes=True)

    dong: str
    risk_ratio: float
    risk_level: str
    color: str
    trend: float
    total_cells: int
    sample_sufficient_cells: int
    coverage_pct: float


class PredictionContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    factor_code: str
    factor_label: str
    direction: Literal["risk", "safe"]
    share_pct: float


class PredictionExplanationResponse(BaseModel):
    notice: str
    contributions: list[PredictionContributionResponse]


class PolicyPriorityItem(BaseModel):
    """현장점검 우선순위 4사분면 항목.

    x축 = 실제 관측 폐업률(예측값 아님), y축 = store_count(영향 점포 수).
    구 필드명 growth_prob은 실제로 점포 수를 담고 있어 의미가 혼동되므로 store_count로 정정했다.
    이 응답은 지원 대상 결정이 아니라 '어디부터 현장 확인할지' 순서를 제시한다.
    """

    model_config = ConfigDict(from_attributes=True)

    dong: str
    category: str
    # 2026-08-20부터 4분기 누적 기준이다(이름은 유지 — 프론트·CSV가 참조 중).
    actual_closure_rate_pct: float
    cumulative_closure_count: int = 0
    cell_type: str | None = None
    # 사분면과 등급은 서로 다른 축이다. 사분면은 "어느 순서로 볼까"(중위값 기준 상대 배치),
    # 등급은 "얼마나 심각한가"(상위 10%/30%). 화면에 둘 다 보여줘 혼동을 막는다.
    risk_grade: str = "안정"
    store_count: int
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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    verification_type: str


class AlertCaseUpdate(BaseModel):
    status: Optional[str] = None
    confirmed_cause_code: Optional[str] = None
    decision_note: Optional[str] = None


class AlertCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prediction_id: int
    assigned_official_id: Optional[int]
    status: str
    confirmed_cause_code: Optional[str]
    decision_note: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]
    closed_at: Optional[datetime]


class AlertEvidenceCreate(BaseModel):
    evidence_type: str
    metric_code: str
    observed_value: Optional[float] = None
    baseline_value: Optional[float] = None
    direction: Optional[str] = None
    quality_flag: str = "verified"
    source_quarter_code: Optional[int] = None
    description: Optional[str] = None


class AlertEvidenceResponse(AlertEvidenceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int
    verified_by_official_id: Optional[int]
    created_at: datetime


class AlertContactCreate(BaseModel):
    contacted_on: date
    channel: Literal["visit", "phone", "sms", "email", "meeting", "other"]
    outcome: Literal["connected", "no_answer", "declined", "applied", "pending"]
    target_scope: Literal["cell", "store_subset"] = "cell"
    contacted_store_count: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = None


class AlertContactUpdate(BaseModel):
    contacted_on: Optional[date] = None
    channel: Optional[Literal["visit", "phone", "sms", "email", "meeting", "other"]] = None
    outcome: Optional[Literal["connected", "no_answer", "declined", "applied", "pending"]] = None
    target_scope: Optional[Literal["cell", "store_subset"]] = None
    contacted_store_count: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = None


class AlertContactResponse(AlertContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int
    official_id: int
    created_at: datetime
    updated_at: Optional[datetime]


class PolicyProgramResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    program_code: str
    program_name: str
    description: Optional[str]


class PolicyActionCreate(BaseModel):
    alert_id: int
    program_code: str
    status: str = "reviewing"
    decision_reason: Optional[str] = None
    budget_amount: Optional[Decimal] = None
    target_store_count: Optional[int] = None


class PolicyActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int
    program_id: int
    official_id: int
    status: str
    decision_reason: Optional[str]
    budget_amount: Optional[Decimal]
    target_store_count: Optional[int]
    created_at: datetime


class PolicyOutcomeCreate(BaseModel):
    evaluation_quarter_code: int
    baseline_closure_rate: Optional[float] = None
    observed_closure_rate: Optional[float] = None
    baseline_store_count: Optional[int] = None
    observed_store_count: Optional[int] = None
    evaluation_note: Optional[str] = None


class PolicyOutcomeResponse(PolicyOutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_id: int
    created_at: datetime


# ── 상권 비교 (2026-08-25) ──────────────────────────────────────────────────
# 노다지(서울 프로젝트)의 지역 비교/업종 비교 두 기능을 하나로 합쳤다. 화성시의 분석 단위가
# (행정동 x 업종) 셀이라 셀 두 개를 받으면 "같은 업종 다른 동" "같은 동 다른 업종" "자유 조합"이
# 모두 커버된다. 3개 이상 비교는 넣지 않는다 — 그건 랭킹이고 closure-rate-ranking이 담당한다.


class CompareInterval(BaseModel):
    lower_pct: float
    upper_pct: float
    denominator: int
    approximate: bool  # 폐업 0건 셀은 분모를 비율로 복원할 수 없어 근사한다


class CompareCellItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    area_id: int
    industry_id: int
    area_name: str
    industry_name: str
    quarter_code: int
    store_count: int
    cumulative_closure_rate_pct: float
    cumulative_closure_count: int | None = None
    confidence_lower_pct: float | None = None      # 저장된 Wilson 하한(정렬용)
    interval: CompareInterval | None = None        # 비교 판정에 쓰는 구간
    opening_rate_pct: float | None = None
    saturation_rate: float | None = None
    competition_index: float | None = None
    trend_slope: float | None = None
    anomaly: bool = False
    risk_grade: str | None = None
    cell_type: str | None = None
    cell_type_summary: str | None = None
    industry_rank: int | None = None
    industry_total_areas: int | None = None
    sample_insufficient: bool = False


class CompareDiff(BaseModel):
    metric: str
    label: str
    unit: str
    decimals: int = 2                   # 화면 표시 소수 자릿수. 건수·점포수는 0
    kind: str = "rate"                  # "count"(관측 건수) | "rate"(비율·지수). 표본부족 처리가 갈린다
    left: float | None = None
    right: float | None = None
    delta: float | None = None          # left - right
    comparable: bool = True             # False면 화면에서 차이를 숫자로 말하지 않는다
    reason: str | None = None           # comparable=False인 이유: "noise" | "sample" (화면 문구가 갈린다)
    note: str | None = None


class CompareResponse(BaseModel):
    left: CompareCellItem
    right: CompareCellItem
    diffs: list[CompareDiff]
    verdict: str
    notice: str
    basis: dict
