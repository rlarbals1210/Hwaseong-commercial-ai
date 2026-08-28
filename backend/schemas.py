from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import Field


# 비율 필드가 전부 Optional인 이유 —
# 누적 지표는 4분기가 쌓여야 나오므로 그 전 구간은 값이 없다(전체 35,505행 중 21%).
# 없는 값을 0.0으로 채우면 "판단 불가"가 "가장 안전"으로 읽힌다. None으로 내려보내고
# 화면이 "—"로 그리게 한다. 변환은 backend/services/risk.py의 pct() 하나만 쓴다.
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
    cumulative_closure_rate_pct: float | None = None   # 최근 1년 누적 폐업률. 미산출이면 None
    cumulative_closure_count: int        # 같은 창의 폐업 건수 — "23곳 닫힘" 형태로 병기
    store_count: int
    confidence_lower_pct: float | None = None   # Wilson 신뢰하한. 소표본 여부를 가늠하는 근거
    risk_grade: str
    # 유형은 등급과 별개 축이다. 등급은 "얼마나 위험한가", 유형은 "그래서 무엇을 할 것인가".
    cell_type: str | None = None
    cell_type_summary: str | None = None
    cell_type_advice: str | None = None
    cell_type_avoid: str | None = None
    quarter_closure_rate_pct: float | None = None   # 단일 분기(참고용, 정렬·판정에 쓰지 않음)
    open_rate_pct: float | None = None
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
    # 셀 상세로 이동하기 위한 식별자. 없으면 목록이 막다른 길이 된다 —
    # "폐업률 최악 10곳"을 보여주고 클릭할 수 없으면 다음 행동이 끊긴다.
    area_id: int
    industry_id: int
    dong: str
    category: str
    closure_rate_pct: float | None = None   # 최근 1년 누적 폐업률 (정렬 기준과 동일)
    cumulative_closure_count: int
    confidence_lower_pct: float | None = None
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
    cumulative_closure_rate_pct: float | None = None
    # 신뢰구간. 등급 대신 준다 — 등급은 "위험/안정" 한 글자로 확실성을 지우지만
    # 구간은 "8.5% (5.2~13.4%)"로 얼마나 못 믿을 값인지를 같이 전달한다.
    # 폭이 좁은 문턱 근처 구간(중위 6.8%p)에서만 화면이 쓴다.
    closure_lower_pct: float | None = None
    closure_upper_pct: float | None = None
    interval_approximate: bool = False   # 폐업 0건이면 분모를 복원할 수 없어 근사한다


class BlindspotResponse(BaseModel):
    notice: str
    items: list[BlindspotItem]
    total_cells: int
    total_stores: int
    total_closures: int
    store_share_pct: float          # 전체 점포 중 사각지대 비중
    city_stores: int = 0            # 화성시 전체 점포 수 — 화면이 "n곳 중 m곳"으로 말하려면 분모가 필요하다
    sample_min: int
    # 선택된 구간의 셀 수. 전체(all)와 문턱 근처(near)를 한 화면의 탭으로 두므로
    # 탭 라벨에 개수를 박으려면 필터 적용 후 총계가 따로 필요하다.
    band: str = "all"
    band_cells: int = 0
    band_stores: int = 0
    near_min_stores: int = 0        # 문턱 근처 구간의 하한. 화면이 근거를 그대로 적는다


class BlindspotCoverageItem(BaseModel):
    """읍면동별 커버율 — 사각지대가 어디에 뚫려 있는지.

    "전체의 38%가 안 보인다"는 한 숫자로는 구멍의 모양이 안 보인다. 실제로는 고르게
    퍼져 있지 않고 농촌·구도심에 몰려 있다(기배동·매송면 커버율 0%, 동탄1동 35.1%).
    분석 도구가 도시 지역에 편향돼 있다는 뜻이고, 정책 우선순위를 고르는 데 쓰이면
    형평성 문제로 직결된다. 지적당하기 전에 화면이 먼저 드러내는 편이 낫다.
    """

    model_config = ConfigDict(from_attributes=True)

    dong: str
    total_cells: int
    sufficient_cells: int
    coverage_pct: float
    total_stores: int
    blindspot_stores: int
    blindspot_store_pct: float
    # 업종 구분을 지우고 동 전체를 한 덩어리로 본 폐업률.
    # 커버율 0%인 동도 이 단위에서는 표본이 충분하다(기배동 누적 분모 1,847).
    # "이 동은 아무것도 모른다"가 아니라 "업종별로는 못 갈라도 동 단위로는 안다"가 사실이다.
    pooled_closure_rate_pct: float | None = None
    pooled_closure_count: int = 0
    pooled_denominator: int = 0
    # 화성시 전체와의 차이가 우연으로 설명되는지. 두 비율 차이의 z검정(양측 p<0.05).
    # 값만 주면 "5.17%가 높은 건가 낮은 건가"를 담당자가 알 수 없다. 분모가 동마다
    # 1,300~18,000으로 크게 달라서 눈대중 비교도 안 된다.
    vs_city: str = "차이없음"          # 높음 / 낮음 / 차이없음
    vs_city_z: float | None = None


class BlindspotCoverageResponse(BaseModel):
    notice: str
    sample_min: int
    items: list[BlindspotCoverageItem]     # 커버율 오름차순 — 안 보이는 곳이 위로
    zero_coverage_dongs: list[str]         # 커버율 0%. 별도로 세어 화면이 문장으로 말할 수 있게
    # 화성시 전체를 같은 방식으로 묶은 값. 동 값 하나만 주면 높은지 낮은지 알 수 없다.
    city_pooled_closure_rate_pct: float | None = None


class BlindspotIndustryItem(BaseModel):
    """업종별 커버율 — 사각지대의 두 번째 축.

    지역 축(위)만 보면 "시골 문제"로 읽히지만, 업종 축을 같이 보면 구조 문제가 드러난다.
    읍면동마다 10곳씩 흩어진 업종은 어느 셀도 기준을 못 넘어 화성시 전역에서 통째로
    사라진다(74개 업종 중 41개가 판단 가능 셀 0개).

    closure_count는 건수만 준다. 누적 분모는 4개 분기 직전점포수의 합이라 store_count의
    약 4배이고, 화면이 closure_count / store_count 를 폐업률처럼 계산하면 4배 부풀려진다.
    """

    model_config = ConfigDict(from_attributes=True)

    category: str
    total_cells: int
    sufficient_cells: int
    coverage_pct: float
    total_stores: int
    closure_count: int


class BlindspotIndustryResponse(BaseModel):
    notice: str
    sample_min: int
    items: list[BlindspotIndustryItem]
    invisible_count: int      # 판단 가능 셀이 0개인 업종 수
    industry_total: int       # 전체 업종 수 — 분모를 화면에 같이 띄운다


class VacancyRiskItem(BaseModel):
    """지도(현황) — 읍면동 단위 위험 업종 비율(실제값 기준), 예측값 관여 없음."""

    model_config = ConfigDict(from_attributes=True)

    dong: str
    area_id: int = 0            # 클릭한 읍면동의 상세를 부르려면 id가 필요하다
    # 표본충분 셀이 적은 동은 비율을 내리지 않는다(None). 0.0으로 채우면 "판단 불가"가
    # "위험 업종 0%"로 읽히고 지도가 초록으로 칠해진다(2026-08-25 감사).
    risk_ratio: float | None = None
    risk_level: str
    color: str
    trend: float
    total_cells: int
    sample_sufficient_cells: int
    coverage_pct: float
    # 판정은 했지만 표본충분 업종이 적은 동. 화면이 흐리게 칠하고 배지를 단다.
    evidence_thin: bool = False
    # 보류 사유 또는 근거 얕음 안내. 충분히 판정된 동은 None
    hold_notice: str | None = None


class AreaIndustryItem(BaseModel):
    """읍면동 안의 업종 한 줄. 지도 패널이 "그래서 어느 업종인가"에 답하게 한다."""

    model_config = ConfigDict(from_attributes=True)

    area_id: int
    industry_id: int
    category: str
    store_count: int
    cumulative_closure_rate_pct: float | None = None
    cumulative_closure_count: int | None = None
    risk_grade: str | None = None
    cell_type: str | None = None


class AreaDetailResponse(BaseModel):
    """지도에서 읍면동을 눌렀을 때 뜨는 상세.

    예전 패널은 "위험 업종 비율 0.0%"와 표본 충족률만 말하고 끝났다. 담당자의 다음 질문은
    반드시 "그래서 어느 업종인가"인데 화면에서 동선이 끊겼다. 업종 목록과 동 단위 실적,
    배후 여건까지 한 패널에서 답한다.
    """

    area_id: int
    dong: str
    quarter_code: int
    quarter_label: str

    total_cells: int = 0
    sample_sufficient_cells: int = 0
    coverage_pct: float = 0.0
    risk_cells: int = 0                  # 위험 등급 업종 수
    caution_cells: int = 0               # 주의 등급 업종 수

    # 업종 구분 없이 읍면동 전체를 묶은 폐업률. 표본이 부족한 동도 이 단위에서는 판정된다.
    pooled_closure_rate_pct: float | None = None
    pooled_closure_count: int = 0
    city_pooled_closure_rate_pct: float | None = None
    vs_city: str = "차이없음"            # 높음 / 낮음 / 차이없음
    vs_city_z: float | None = None

    # 배후 여건 — 판정 축이 아니라 원인의 방향을 좁히는 참고 자료
    population: int | None = None
    population_change_pct: float | None = None
    population_from_label: str | None = None
    population_to_label: str | None = None

    # 사각지대 규모
    blindspot_cells: int = 0
    blindspot_stores: int = 0
    total_stores: int = 0

    industries: list[AreaIndustryItem] = []


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

    # 셀 상세로 이동하기 위한 식별자. "가장 먼저 확인하세요"라고 써 둔 목록을 눌렀는데
    # 아무 일도 일어나지 않으면 도구의 논리가 그 자리에서 끊긴다.
    area_id: int
    industry_id: int
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


# 예비 창업자용 공개 응답. 예측 절대값은 아예 필드로 정의하지 않아
# 라우터가 실수로 넣어도 FastAPI 응답 직렬화 단계에서 공개되지 않게 한다.
class RecommendationObserved(BaseModel):
    closure_rate_cum4_pct: float | None = None
    closure_count_cum4: int | None = None
    store_count: int
    opening_rate_pct: float | None = None
    tenure_quarters: float | None = None
    cell_type: str | None = None


class RecommendationBreakdown(BaseModel):
    key: str
    label: str
    score: float
    max: int
    weight_pct: int
    desc: str


class RecommendationAreaResult(BaseModel):
    rank: int | None = None
    area_id: int
    area_name: str
    score: float | None = None
    grade: str | None = None
    percentile: float | None = None
    breakdown: list[RecommendationBreakdown]
    tags: list[str]
    reason: str
    observed: RecommendationObserved
    evidence_key: Literal["sufficient", "medium", "low", "unobserved"]
    evidence_label: str
    # 원점수를 얼마나 반영했는지이며, 성공확률이나 신뢰구간이 아니다.
    data_weight_pct: int
    score_adjusted: bool
    adjustment_note: str | None = None


class RecommendationAreaListResponse(BaseModel):
    quarter_code: int
    quarter_label: str
    window_quarters: int
    industry_id: int
    industry_name: str
    measured_count: int
    excluded_count: int
    total_count: int
    ranked_count: int
    sufficient_count: int
    limited_count: int
    unobserved_count: int
    sample_min: int
    comparison_notice: str
    preset: str
    weights: dict[str, float]
    growth_spread: float
    growth_spread_narrow: bool
    results: list[RecommendationAreaResult]
    relative_notice: str
    disclaimer: str


class RecommendationIndustryResult(BaseModel):
    rank: int
    industry_id: int
    industry_name: str
    score: float
    breakdown: list[RecommendationBreakdown]
    tags: list[str]
    reason: str
    observed: RecommendationObserved
    growth_spread: float
    growth_spread_narrow: bool


class RecommendationIndustryListResponse(BaseModel):
    quarter_code: int
    quarter_label: str
    area_id: int
    area_name: str
    measured_count: int
    excluded_count: int
    preset: str
    weights: dict[str, float]
    results: list[RecommendationIndustryResult]
    grade_notice: str
    relative_notice: str
    disclaimer: str


class RecommendationScoreResponse(BaseModel):
    quarter_code: int
    quarter_label: str
    window_quarters: int | None = None
    area_id: int
    area_name: str
    industry_id: int
    industry_name: str
    is_fallback: bool
    score: float | None = None
    grade: str | None = None
    percentile: float | None = None
    rank: int | None = None
    total: int
    excluded_count: int | None = None
    summary: str
    breakdown: list[RecommendationBreakdown]
    pros: list[str]
    cons: list[str]
    observed: RecommendationObserved
    evidence_key: Literal["sufficient", "medium", "low", "unobserved"]
    evidence_label: str
    data_weight_pct: int
    score_adjusted: bool
    adjustment_note: str | None = None
    preset: str
    weights: dict[str, float]
    growth_spread: float
    growth_spread_narrow: bool
    relative_notice: str
    disclaimer: str


class RecommendationPreset(BaseModel):
    key: str
    label: str
    description: str
    weights: dict[str, float]


class RecommendationAxis(BaseModel):
    key: str
    label: str
    desc: str


class RecommendationPresetsResponse(BaseModel):
    default: str
    presets: list[RecommendationPreset]
    axes: list[RecommendationAxis]
    notice: str


class StoreClusterItem(BaseModel):
    lat: float
    lng: float
    store_count: int


class StoreClusterResponse(BaseModel):
    quarter_code: int
    industry_id: int
    grid_degrees: float
    min_cluster_size: int
    clusters: list[StoreClusterItem]
    visible_store_count: int
    suppressed_store_count: int
    omitted_cluster_count: int
    privacy_notice: str


class TrendPoint(BaseModel):
    quarter_code: int
    quarter_label: str
    closure_rate_pct: float | None = None
    opening_rate_pct: float | None = None
    store_count: int
    cell_count: int


class TrendGroup(BaseModel):
    key: str
    label: str
    series: list[TrendPoint]
    closure_change_pct: float | None = None


class TrendOverviewResponse(BaseModel):
    latest_quarter: int
    series: list[TrendPoint]
    method_notice: str


class TrendAreaRankResponse(BaseModel):
    industry_id: int
    industry_name: str
    results: list[TrendGroup]


class TrendIndustryRankResponse(BaseModel):
    area_id: int
    area_name: str
    results: list[TrendGroup]


class TrendCellResponse(BaseModel):
    area_id: int
    area_name: str
    industry_id: int
    industry_name: str
    series: list[TrendPoint]


class TrendComparisonResponse(BaseModel):
    title: str
    description: str
    groups: list[TrendGroup]


class RuleReportSection(BaseModel):
    key: str
    title: str
    body: list[str]


class RuleReportResponse(BaseModel):
    title: str
    quarter_code: int
    quarter_label: str
    preset: str
    cache_key: str
    generated_by: str
    sections: list[RuleReportSection]
    relative_notice: str
    disclaimer: str
    ai_disclosure: str


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
    cumulative_closure_rate_pct: float | None = None
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
    # 배후 여건 — 상권의 성적이 아니라 그 상권이 놓인 조건이다. 같은 폐업률이라도
    # 점포가 젊은 곳과 오래된 곳, 사람이 느는 곳과 주는 곳은 손댈 지점이 다르다.
    avg_tenure_quarters: float | None = None      # 평균 업력(분기)
    population: int | None = None                 # 배후 읍면동 등록인구(최신)
    population_change_pct: float | None = None    # 3년 증감
    population_from_label: str | None = None
    population_to_label: str | None = None


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
    # 차이를 같은 업종 분포의 표준편차로 나눈 값. 단위가 제각각인 지표들을 한 자로 재서
    # "가장 크게 다른 점"을 정렬할 수 있게 한다. 업종이 서로 다르면 기준이 없어 None이다.
    sigma: float | None = None
    # 이 업종 안에서 그 지표와 폐업률이 함께 움직인 정도(스피어만 순위상관).
    # 차이가 크다는 것과 그 차이가 이 업종에서 의미 있다는 것은 다르다. 상관이 0에
    # 가까우면 아무리 크게 벌어져도 폐업률을 설명할 후보가 아니다.
    # 인과가 아니다. 표본이 업종당 9~27곳이라 값 자체도 흔들린다.
    industry_correlation: float | None = None
    explains: bool = False              # 상관·차이가 모두 충분해 설명 후보로 볼 만한가


class CompareTrendPoint(BaseModel):
    """두 상권의 분기별 누적 폐업률. 스냅샷만으로는 「원래 나쁜 곳」과 「최근 나빠진 곳」이
    구분되지 않는다. 후자면 개입 시점이 지금이라 판단이 갈린다.
    누적 4분기가 채워지기 전 분기는 None이다 — 0.0으로 채우면 폐업이 없었다고 읽힌다."""

    quarter_code: int
    label: str
    left_pct: float | None = None
    right_pct: float | None = None


class CompareResponse(BaseModel):
    left: CompareCellItem
    right: CompareCellItem
    diffs: list[CompareDiff]
    trend: list[CompareTrendPoint] = []
    industry_cells: int = 0              # 상관 계산에 쓴 표본 수. 화면이 신뢰도를 함께 말한다
    verdict: str
    notice: str
    basis: dict


class ComparePeerItem(BaseModel):
    """비교 후보 한 곳. 같은 업종·비슷한 규모의 다른 읍면동."""

    model_config = ConfigDict(from_attributes=True)

    area_id: int
    industry_id: int
    area_name: str
    store_count: int
    cumulative_closure_rate_pct: float | None = None
    cumulative_closure_count: int | None = None
    delta_pp: float | None = None        # 선택 상권 대비 (후보 - 선택)
    z: float | None = None               # 두 비율 차이 z. 음수면 후보가 더 낮다
    significant: bool = False            # |z| >= 1.96


class CompareDistributionItem(BaseModel):
    """업종 지형도의 점 하나.

    폐업률 한 축만 그리면 "누가 더 나쁜가"밖에 못 말한다. 개업률을 두 번째 축으로 두면
    같은 폐업률이라도 드나듦이 잦은 곳과 멈춘 곳이 갈리고, 그 네 칸이 곧 상권 유형이다
    (고회전/쇠퇴/성장/정체). 처방이 갈리는 지점을 그림 하나로 보인다.
    """

    area_id: int
    area_name: str
    store_count: int
    cumulative_closure_rate_pct: float
    opening_rate_pct: float | None = None
    cell_type: str | None = None
    rank: int | None = None        # 업종 내 폐업률 순위
    is_self: bool = False
    is_target: bool = False        # 현재 비교 중인 상대편


class CompareContextResponse(BaseModel):
    """비교 대상을 담당자가 이미 알고 있어야 쓸 수 있는 도구는 도구가 아니다.
    상권 하나를 받아 ① 같은 업종 안에서의 위치와 ② 비교할 만한 후보를 돌려준다."""

    quarter_code: int
    quarter_label: str
    area_id: int
    industry_id: int
    area_name: str
    industry_name: str
    store_count: int
    cumulative_closure_rate_pct: float | None = None
    sample_insufficient: bool = False

    # 업종 내 위치
    industry_eligible_cells: int = 0     # 표본 기준을 넘은 같은 업종 상권 수
    industry_rank: int | None = None     # 폐업률 높은 순
    industry_median_pct: float | None = None
    distribution: list[CompareDistributionItem] = []
    # 상권 유형 4분류의 가로·세로 절단선(표본충분 셀의 중위값). 지형도의 십자선이고,
    # 하드코딩하면 파이프라인 재실행 때 사분면과 배지가 어긋난다.
    type_open_cut_pct: float | None = None
    type_close_cut_pct: float | None = None
    cell_type: str | None = None

    # 비교 후보
    peer_store_min: int = 0
    peer_store_max: int = 0
    peer_ratio_pct: int = 50
    peers: list[ComparePeerItem] = []
    contrast: ComparePeerItem | None = None   # 가장 대조적인 곳(z 최소)
    similar: ComparePeerItem | None = None    # 가장 비슷한 곳(|z| 최소)
    notice: str = ""
