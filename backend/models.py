from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
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
    opening_rate = Column(Float, nullable=True)  # 0~1 비율
    closure_rate = Column(Float, nullable=True)  # 0~1 비율
    saturation_rate = Column(Float, nullable=True)
    competition_index = Column(Float, nullable=True)
    trend_slope = Column(Float, nullable=True)
    anomaly_flag = Column(Boolean, nullable=False, default=False)
    batch_id = Column(Integer, ForeignKey("data_batches.id"), nullable=False, index=True)


class ModelRun(Base):
    __tablename__ = "model_runs"

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


class AlertEvidence(Base):
    __tablename__ = "alert_evidences"

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
