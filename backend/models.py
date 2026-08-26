from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from .database import Base


BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")


class CommercialData(Base):
    __tablename__ = "commercial_data"
    __table_args__ = (
        UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_commercial_dong_cat_quarter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    기준_년분기_코드 = Column(Integer, index=True)
    행정동명 = Column(String(50), index=True)
    통합카테고리 = Column(String(50), index=True)

    당월매출합 = Column(BigInteger, nullable=True)
    점포수 = Column(Integer, nullable=True)
    총_유동인구_수 = Column(Integer, nullable=True)
    폐업_률_평균 = Column(Float, nullable=True)
    개업_율_평균 = Column(Float, nullable=True)
    업종_포화도 = Column(Float, nullable=True)
    경쟁강도 = Column(Float, nullable=True)
    업종_점포당매출 = Column(BigInteger, nullable=True)
    업종_매출점유율 = Column(Float, nullable=True)

    총_직장_인구_수 = Column(Integer, nullable=True)
    주거인구 = Column(Integer, nullable=True)
    월_평균_소득_금액 = Column(Integer, nullable=True)

    매출_20대합 = Column(BigInteger, nullable=True)
    매출_30대합 = Column(BigInteger, nullable=True)
    매출_40대합 = Column(BigInteger, nullable=True)
    매출_50대합 = Column(BigInteger, nullable=True)
    매출_60대이상합 = Column(BigInteger, nullable=True)

    월요일매출합 = Column(BigInteger, nullable=True)
    화요일매출합 = Column(BigInteger, nullable=True)
    수요일매출합 = Column(BigInteger, nullable=True)
    목요일매출합 = Column(BigInteger, nullable=True)
    금요일매출합 = Column(BigInteger, nullable=True)
    토요일매출합 = Column(BigInteger, nullable=True)
    일요일매출합 = Column(BigInteger, nullable=True)

    유동_20대 = Column(Integer, nullable=True)
    유동_30대 = Column(Integer, nullable=True)
    유동_40대 = Column(Integer, nullable=True)
    유동_50대 = Column(Integer, nullable=True)
    유동_60대이상 = Column(Integer, nullable=True)


class ScoreData(Base):
    __tablename__ = "score_data"
    __table_args__ = (
        UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_score_dong_cat_quarter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    행정동명 = Column(String(50), index=True)
    통합카테고리 = Column(String(50), index=True)
    기준_년분기_코드 = Column(Integer, index=True)
    성장확률 = Column(Float)
    등급 = Column(String(2))
    상위_퍼센트 = Column(Float, nullable=True)
    업종내_순위 = Column(Integer, nullable=True)
    업종내_전체동수 = Column(Integer, nullable=True)


class Official(Base):
    __tablename__ = "officials"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String(50), nullable=True)


class RiskIndex(Base):
    __tablename__ = "risk_index"
    __table_args__ = (
        UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_risk_dong_cat_quarter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    행정동명 = Column(String(50), index=True)
    통합카테고리 = Column(String(50), index=True)
    기준_년분기_코드 = Column(Integer, index=True)

    # 지도·순위표(현황) — 실제 관측 폐업률만 사용, 보정 없음
    실제폐업률_pct = Column(Float)
    위험등급 = Column(String(10), nullable=True)  # 실제폐업률_pct 기준 안정/주의/위험/표본부족
    위험업종비율 = Column(Float, nullable=True)  # 동단위: 위험등급 셀 수 / 표본충분 셀 수 (%), choropleth용
    표본부족_플래그 = Column(Boolean, default=False)  # 점포수 < SAMPLE_MIN(build_risk_index.py)
    점포수 = Column(Integer, nullable=True)
    개업률_pct = Column(Float, nullable=True)
    업종_포화도 = Column(Float, nullable=True)

    # 조기경보(예측) — 예측 절대값은 저장하지 않음(내부 랭킹 산정은 CSV에서 완료). 순위만 노출.
    예측순위 = Column(Integer, nullable=True)  # 표본충분 셀 내 예측폐업률 내림차순 순위, 표본부족은 NULL
    성장확률 = Column(Float, nullable=True)  # ScoreData와 동일 값 — 위험도와 분리된 "성장성" 지표, 4사분면 진단용 보존

    트렌드_기울기 = Column(Float, nullable=True)
    이상탐지_플래그 = Column(Boolean, default=False)


# 아래 모델은 원본의 서로 다른 grain을 분리한 정규화 스키마다. 위 4개 테이블은
# 무중단 전환과 롤백을 위해 당분간 보존하고, 신규 API는 아래 테이블만 조회한다.
class AdminArea(Base):
    __tablename__ = "admin_areas"

    id = Column(Integer, primary_key=True)
    area_code = Column(String(10), unique=True, nullable=False, index=True)
    area_name = Column(String(50), nullable=False, index=True)
    area_type = Column(String(20), nullable=False)
    parent_area_id = Column(Integer, ForeignKey("admin_areas.id"), nullable=True)
    valid_from = Column(String(7), nullable=True)  # YYYY-MM; 원천이 월까지만 제공
    valid_to = Column(String(7), nullable=True)
    is_current = Column(Boolean, nullable=False, default=True, index=True)


class IndustryCategory(Base):
    __tablename__ = "industry_categories"
    __table_args__ = (
        UniqueConstraint("source_system", "industry_code", name="uq_industry_source_code"),
    )

    id = Column(Integer, primary_key=True)
    source_system = Column(String(30), nullable=False, default="sbiz")
    industry_code = Column(String(20), nullable=False, index=True)
    industry_name = Column(String(100), nullable=False, index=True)
    level = Column(String(10), nullable=False, default="medium")
    parent_id = Column(Integer, ForeignKey("industry_categories.id"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class DataBatch(Base):
    __tablename__ = "data_batches"

    id = Column(Integer, primary_key=True)
    batch_key = Column(String(100), unique=True, nullable=False, index=True)
    source_name = Column(String(100), nullable=False)
    method_version = Column(String(50), nullable=False)
    source_start_quarter = Column(Integer, nullable=True)
    source_end_quarter = Column(Integer, nullable=True)
    row_count = Column(Integer, nullable=True)
    quality_notes = Column(Text, nullable=True)
    imported_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    retention_until = Column(DateTime(timezone=True), nullable=True)
    purged_at = Column(DateTime(timezone=True), nullable=True)


class RiskThresholdSet(Base):
    """관측 위험등급과 표본 판정에 사용한 기준선 이력."""

    __tablename__ = "risk_threshold_sets"
    __table_args__ = (
        UniqueConstraint("batch_id", "quarter_code", name="uq_threshold_batch_quarter"),
    )

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("data_batches.id"), nullable=False, index=True)
    quarter_code = Column(Integer, nullable=False, index=True)
    avg_closure_rate_pct = Column(Float, nullable=False)
    danger_threshold_pct = Column(Float, nullable=False)
    area_ratio_avg_pct = Column(Float, nullable=False)
    area_ratio_danger_pct = Column(Float, nullable=False)
    sample_min = Column(Integer, nullable=False, default=50)
    # 상위 30% 경계(주의 등급). danger_threshold_pct는 상위 10% 경계다.
    caution_threshold_pct = Column(Float, nullable=True)
    window_quarters = Column(Integer, nullable=True, default=4)
    method = Column(String(40), nullable=True)  # cumulative_quantile
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CommercialQuarter(Base):
    __tablename__ = "commercial_quarters"
    __table_args__ = (
        UniqueConstraint("area_id", "industry_id", "quarter_code", name="uq_commercial_quarter"),
    )

    id = Column(BIGINT_PK, primary_key=True)
    area_id = Column(Integer, ForeignKey("admin_areas.id"), nullable=False, index=True)
    industry_id = Column(Integer, ForeignKey("industry_categories.id"), nullable=False, index=True)
    quarter_code = Column(Integer, nullable=False, index=True)
    store_count = Column(Integer, nullable=False)
    opening_rate = Column(Float, nullable=True)  # 0~1 비율. 원본(개업_율_평균) — 수록 지연 결함이 남아 있다
    # 보정 개업률 4분기 이동평균. 상권유형 판정이 쓰는 값이고 화면 표시도 이쪽이다.
    # 원본은 표본충분 셀의 26.8%가 0.0%로 나오지만 이 값은 5.2%다(2026-08-26 실측).
    # 원본을 지우지 않은 이유: 두 값의 차이가 보정의 근거이고 감사에서 둘 다 필요하다.
    opening_rate_ma4 = Column(Float, nullable=True)
    closure_rate = Column(Float, nullable=True)  # 0~1 비율 (단일 분기, 기존 의미 유지)
    # 4분기 누적 지표 (2026-08-20 추가). 등급·화면 표시는 이 값을 쓴다.
    # 단일 분기는 노이즈가 커서 분기 간 순위 상관이 +0.296에 불과했다(누적은 +0.857).
    closure_rate_cum4 = Column(Float, nullable=True)      # 4분기 누적 폐업률 0~1
    closure_rate_lower4 = Column(Float, nullable=True)    # 위 값의 Wilson 신뢰하한 (정렬용)
    closure_count_cum4 = Column(Integer, nullable=True)   # 4분기 누적 폐업 건수 (화면 병기용)
    # 셀 평균 업력(분기 수). 원천은 cell_train_table.csv의 평균업력_분기수(모델 학습 피처).
    # **점수 축이 아니라 표시 지표다.** 폐업률과의 스피어만이 -0.064로 사실상 무상관이고,
    # 실제로는 신도시 여부의 대리변수라(면·읍이 높고 동탄이 낮다) 가중치를 줄 근거가 없다.
    # 자세한 계측은 migrations/versions/20260826_0007_avg_tenure_quarters.py 참조.
    avg_tenure_quarters = Column(Float, nullable=True)
    saturation_rate = Column(Float, nullable=True)
    competition_index = Column(Float, nullable=True)
    trend_slope = Column(Float, nullable=True)
    anomaly_flag = Column(Boolean, nullable=False, default=False)
    risk_grade = Column(String(10), nullable=True)
    # 상권 유형 — 고회전/쇠퇴/성장/정체/유형판정보류. 등급과 별개 축이며 섞지 않는다.
    # 등급은 "얼마나 위험한가", 유형은 "그래서 무엇을 할 것인가"를 가른다.
    cell_type = Column(String(20), nullable=True)
    sample_insufficient = Column(Boolean, nullable=False, default=False, index=True)
    threshold_set_id = Column(
        Integer, ForeignKey("risk_threshold_sets.id"), nullable=True, index=True
    )
    batch_id = Column(Integer, ForeignKey("data_batches.id"), nullable=False, index=True)


class StoreCluster(Base):
    """공개 지도용 점포 격자 집계.

    개별 점포 좌표는 저장하지 않는다. 적재 단계에서 0.002도 격자로 합친 뒤 중심점과
    개수만 남기며, 공개 API는 3개 미만 격자를 추가로 숨긴다.
    """

    __tablename__ = "store_clusters"
    __table_args__ = (
        UniqueConstraint(
            "industry_id", "quarter_code", "grid_x", "grid_y",
            name="uq_store_cluster_industry_quarter_grid",
        ),
        CheckConstraint("store_count > 0", name="ck_store_clusters_positive_count"),
    )

    id = Column(BIGINT_PK, primary_key=True)
    industry_id = Column(Integer, ForeignKey("industry_categories.id"), nullable=False, index=True)
    quarter_code = Column(Integer, nullable=False, index=True)
    grid_x = Column(Integer, nullable=False)
    grid_y = Column(Integer, nullable=False)
    center_lng = Column(Float, nullable=False)
    center_lat = Column(Float, nullable=False)
    store_count = Column(Integer, nullable=False)
    batch_id = Column(Integer, ForeignKey("data_batches.id"), nullable=False, index=True)


class AreaQuarterSummary(Base):
    """동×분기 집계 — 지도와 표본 사각지대 조회의 단일 원천."""

    __tablename__ = "area_quarter_summaries"
    __table_args__ = (
        UniqueConstraint("area_id", "quarter_code", name="uq_area_quarter"),
    )

    id = Column(Integer, primary_key=True)
    area_id = Column(Integer, ForeignKey("admin_areas.id"), nullable=False, index=True)
    quarter_code = Column(Integer, nullable=False, index=True)
    total_cells = Column(Integer, nullable=False)
    sample_sufficient_cells = Column(Integer, nullable=False)
    risk_cells = Column(Integer, nullable=False)
    risk_industry_ratio_pct = Column(Float, nullable=False)
    area_risk_grade = Column(String(10), nullable=True)
    avg_trend_slope = Column(Float, nullable=True)
    threshold_set_id = Column(Integer, ForeignKey("risk_threshold_sets.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("data_batches.id"), nullable=False, index=True)


class ModelRun(Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        Index(
            "uq_model_runs_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id = Column(Integer, primary_key=True)
    run_key = Column(String(120), unique=True, nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=False)
    observation_quarter = Column(Integer, nullable=False, index=True)
    prediction_horizon_quarters = Column(Integer, nullable=False, default=2)
    train_end_quarter = Column(Integer, nullable=True)
    validation_end_quarter = Column(Integer, nullable=True)
    metrics = Column(JSON, nullable=True)
    artifact_path = Column(String(255), nullable=True)
    artifact_checksum = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False, default="ready")
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    __table_args__ = (
        UniqueConstraint("model_run_id", "commercial_quarter_id", name="uq_prediction_run_cell"),
    )

    id = Column(BIGINT_PK, primary_key=True)
    model_run_id = Column(Integer, ForeignKey("model_runs.id"), nullable=False, index=True)
    commercial_quarter_id = Column(
        BIGINT_PK, ForeignKey("commercial_quarters.id"), nullable=False, index=True
    )
    target_quarter_code = Column(Integer, nullable=False)
    predicted_closure_rate_internal = Column(Float, nullable=False)  # API 외부 노출 금지
    predicted_rank = Column(Integer, nullable=True, index=True)
    grade = Column(String(2), nullable=False)
    industry_rank = Column(Integer, nullable=True)
    industry_total_areas = Column(Integer, nullable=True)
    top_percent = Column(Float, nullable=True)
    sample_insufficient = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PredictionContribution(Base):
    """모델 기여 요인. 화면은 share_pct만 사용하고 내부 원 기여도는 노출하지 않는다."""

    __tablename__ = "prediction_contributions"
    __table_args__ = (
        UniqueConstraint("prediction_id", "rank", name="uq_contribution_prediction_rank"),
        CheckConstraint("direction IN ('risk','safe')", name="ck_contribution_direction"),
        CheckConstraint("rank BETWEEN 1 AND 5", name="ck_contribution_rank"),
        CheckConstraint("share_pct >= 0 AND share_pct <= 100", name="ck_contribution_share"),
    )

    id = Column(BIGINT_PK, primary_key=True)
    prediction_id = Column(
        BIGINT_PK, ForeignKey("risk_predictions.id"), nullable=False, index=True
    )
    rank = Column(Integer, nullable=False)
    factor_code = Column(String(40), nullable=False)
    factor_label = Column(String(60), nullable=False)
    direction = Column(String(10), nullable=False)
    share_pct = Column(Float, nullable=False)
    contribution_value_internal = Column(Float, nullable=True)
    source_features = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AlertCase(Base):
    __tablename__ = "alert_cases"

    id = Column(BIGINT_PK, primary_key=True)
    prediction_id = Column(BIGINT_PK, ForeignKey("risk_predictions.id"), unique=True, nullable=False)
    assigned_official_id = Column(Integer, ForeignKey("officials.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="new", index=True)
    confirmed_cause_code = Column(String(50), nullable=True)
    decision_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)


class AlertContact(Base):
    __tablename__ = "alert_contacts"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('visit','phone','sms','email','meeting','other')",
            name="ck_alert_contacts_channel",
        ),
        CheckConstraint(
            "outcome IN ('connected','no_answer','declined','applied','pending')",
            name="ck_alert_contacts_outcome",
        ),
        CheckConstraint(
            "target_scope IN ('cell','store_subset')", name="ck_alert_contacts_scope"
        ),
        Index("ix_alert_contacts_alert_date", "alert_id", "contacted_on"),
    )

    id = Column(BIGINT_PK, primary_key=True)
    alert_id = Column(BIGINT_PK, ForeignKey("alert_cases.id"), nullable=False, index=True)
    official_id = Column(Integer, ForeignKey("officials.id"), nullable=False, index=True)
    contacted_on = Column(Date, nullable=False, index=True)
    channel = Column(String(20), nullable=False)
    outcome = Column(String(20), nullable=False)
    target_scope = Column(String(20), nullable=False, default="cell")
    contacted_store_count = Column(Integer, nullable=True)
    # 개별 점포 참조는 원칙 문구가 승인되기 전까지 API에서 입력받지 않고 NULL로 유지한다.
    store_refs = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())


class AlertEvidence(Base):
    __tablename__ = "alert_evidences"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('confirmed_signal','model_contribution','field_check')",
            name="ck_alert_evidences_type",
        ),
    )

    id = Column(BIGINT_PK, primary_key=True)
    alert_id = Column(BIGINT_PK, ForeignKey("alert_cases.id"), nullable=False, index=True)
    evidence_type = Column(String(30), nullable=False)
    metric_code = Column(String(50), nullable=False)
    observed_value = Column(Float, nullable=True)
    baseline_value = Column(Float, nullable=True)
    direction = Column(String(20), nullable=True)
    quality_flag = Column(String(20), nullable=False, default="verified")
    source_quarter_code = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    verified_by_official_id = Column(Integer, ForeignKey("officials.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PolicyProgram(Base):
    __tablename__ = "policy_programs"

    id = Column(Integer, primary_key=True)
    program_code = Column(String(50), unique=True, nullable=False)
    program_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # (가) 매칭 조건 — 상권 유형·등급 기반. 우리 처방 로직이라 근거가 있다.
    target_cell_types = Column(JSON, nullable=True)        # ["쇠퇴", "정체"]
    target_risk_grades = Column(JSON, nullable=True)       # ["위험", "주의"]
    discouraged_cell_types = Column(JSON, nullable=True)   # 상충하는 유형 — 이유와 함께 표시
    match_reason = Column(Text, nullable=True)

    # (나) 자격 요건 — 실제 공고문에서 확인해야 한다. 추정해서 채우지 않는다.
    owner_department = Column(String(80), nullable=True)
    legal_basis = Column(String(200), nullable=True)
    apply_period = Column(String(120), nullable=True)
    support_limit_text = Column(String(120), nullable=True)
    exclusion_note = Column(Text, nullable=True)
    tenure_min_quarters = Column(Integer, nullable=True)
    tenure_max_quarters = Column(Integer, nullable=True)
    # (나)가 비어 있으면 True. 화면에 "요건 확인 필요"로 표시된다.
    requires_verification = Column(Boolean, nullable=False, default=True)


class PolicyAction(Base):
    __tablename__ = "policy_actions"

    id = Column(BIGINT_PK, primary_key=True)
    alert_id = Column(BIGINT_PK, ForeignKey("alert_cases.id"), nullable=False, index=True)
    program_id = Column(Integer, ForeignKey("policy_programs.id"), nullable=False)
    official_id = Column(Integer, ForeignKey("officials.id"), nullable=False)
    status = Column(String(20), nullable=False, default="reviewing", index=True)
    decision_reason = Column(Text, nullable=True)
    budget_amount = Column(Numeric(15, 2), nullable=True)
    target_store_count = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PolicyOutcome(Base):
    __tablename__ = "policy_outcomes"
    __table_args__ = (
        UniqueConstraint("action_id", "evaluation_quarter_code", name="uq_action_evaluation_quarter"),
    )

    id = Column(BIGINT_PK, primary_key=True)
    action_id = Column(BIGINT_PK, ForeignKey("policy_actions.id"), nullable=False, index=True)
    evaluation_quarter_code = Column(Integer, nullable=False)
    baseline_closure_rate = Column(Float, nullable=True)
    observed_closure_rate = Column(Float, nullable=True)
    baseline_store_count = Column(Integer, nullable=True)
    observed_store_count = Column(Integer, nullable=True)
    evaluation_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AreaPopulationQuarter(Base):
    """읍면동 배후인구(등록인구) 분기 시계열 — KOSIS 주민등록인구.

    등급·상권유형 판정에 관여하지 않는다. 인구증감과 폐업률의 순위상관이 +0.238로 약하고
    부호도 직관과 반대라(정남면 인구 -9.8% / 폐업률 0.04, 봉담읍 +25.9% / 0.05) 판정 축으로
    쓸 근거가 없다. 셀 상세에서 "같은 위험 등급이라도 원인 방향이 다르다"를 보이는 설명 근거다.

    total_population이 NULL인 분기는 인구가 0명이었던 게 아니라 동이 아직 없었다는 뜻이다
    (동탄9동은 2023Q3부터). 0으로 채우면 화면에 인구 폭증으로 그려진다.
    """

    __tablename__ = "area_population_quarters"
    __table_args__ = (
        UniqueConstraint("area_id", "quarter_code", name="uq_area_population_quarter"),
    )

    id = Column(Integer, primary_key=True)
    area_id = Column(Integer, ForeignKey("admin_areas.id"), nullable=False, index=True)
    quarter_code = Column(Integer, nullable=False, index=True)
    total_population = Column(Integer, nullable=True)
    source = Column(String(50), nullable=False, default="kosis_registered")
