"""add normalized analytics, prediction, and official workflow tables"""
from alembic import op
import sqlalchemy as sa


revision = "20260818_0001"
down_revision = "20260818_0000"
branch_labels = None
depends_on = None
BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "admin_areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_code", sa.String(10), nullable=False),
        sa.Column("area_name", sa.String(50), nullable=False),
        sa.Column("area_type", sa.String(20), nullable=False),
        sa.Column("parent_area_id", sa.Integer(), sa.ForeignKey("admin_areas.id")),
        sa.Column("valid_from", sa.String(7)),
        sa.Column("valid_to", sa.String(7)),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_admin_areas_area_code", "admin_areas", ["area_code"], unique=True)
    op.create_index("ix_admin_areas_area_name", "admin_areas", ["area_name"])
    op.create_index("ix_admin_areas_is_current", "admin_areas", ["is_current"])

    op.create_table(
        "industry_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(30), nullable=False),
        sa.Column("industry_code", sa.String(20), nullable=False),
        sa.Column("industry_name", sa.String(100), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("industry_categories.id")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("source_system", "industry_code", name="uq_industry_source_code"),
    )
    op.create_index("ix_industry_categories_industry_code", "industry_categories", ["industry_code"])
    op.create_index("ix_industry_categories_industry_name", "industry_categories", ["industry_name"])

    op.create_table(
        "data_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_key", sa.String(100), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("method_version", sa.String(50), nullable=False),
        sa.Column("source_start_quarter", sa.Integer()),
        sa.Column("source_end_quarter", sa.Integer()),
        sa.Column("row_count", sa.Integer()),
        sa.Column("quality_notes", sa.Text()),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_data_batches_batch_key", "data_batches", ["batch_key"], unique=True)

    op.create_table(
        "commercial_quarters",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("admin_areas.id"), nullable=False),
        sa.Column("industry_id", sa.Integer(), sa.ForeignKey("industry_categories.id"), nullable=False),
        sa.Column("quarter_code", sa.Integer(), nullable=False),
        sa.Column("store_count", sa.Integer(), nullable=False),
        sa.Column("opening_rate", sa.Float()),
        sa.Column("closure_rate", sa.Float()),
        sa.Column("saturation_rate", sa.Float()),
        sa.Column("competition_index", sa.Float()),
        sa.Column("trend_slope", sa.Float()),
        sa.Column("anomaly_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("data_batches.id"), nullable=False),
        sa.UniqueConstraint("area_id", "industry_id", "quarter_code", name="uq_commercial_quarter"),
    )
    op.create_index("ix_commercial_quarters_area_id", "commercial_quarters", ["area_id"])
    op.create_index("ix_commercial_quarters_industry_id", "commercial_quarters", ["industry_id"])
    op.create_index("ix_commercial_quarters_quarter_code", "commercial_quarters", ["quarter_code"])
    op.create_index("ix_commercial_quarters_batch_id", "commercial_quarters", ["batch_id"])

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_key", sa.String(120), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("observation_quarter", sa.Integer(), nullable=False),
        sa.Column("prediction_horizon_quarters", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("train_end_quarter", sa.Integer()),
        sa.Column("validation_end_quarter", sa.Integer()),
        sa.Column("metrics", sa.JSON()),
        sa.Column("artifact_path", sa.String(255)),
        sa.Column("artifact_checksum", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_model_runs_run_key", "model_runs", ["run_key"], unique=True)
    op.create_index("ix_model_runs_observation_quarter", "model_runs", ["observation_quarter"])
    op.create_index("ix_model_runs_is_active", "model_runs", ["is_active"])

    op.create_table(
        "risk_predictions",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("model_run_id", sa.Integer(), sa.ForeignKey("model_runs.id"), nullable=False),
        sa.Column("commercial_quarter_id", BIGINT_PK, sa.ForeignKey("commercial_quarters.id"), nullable=False),
        sa.Column("target_quarter_code", sa.Integer(), nullable=False),
        sa.Column("predicted_closure_rate_internal", sa.Float(), nullable=False),
        sa.Column("predicted_rank", sa.Integer()),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("industry_rank", sa.Integer()),
        sa.Column("industry_total_areas", sa.Integer()),
        sa.Column("top_percent", sa.Float()),
        sa.Column("sample_insufficient", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("model_run_id", "commercial_quarter_id", name="uq_prediction_run_cell"),
    )
    op.create_index("ix_risk_predictions_model_run_id", "risk_predictions", ["model_run_id"])
    op.create_index("ix_risk_predictions_commercial_quarter_id", "risk_predictions", ["commercial_quarter_id"])
    op.create_index("ix_risk_predictions_predicted_rank", "risk_predictions", ["predicted_rank"])
    op.create_index("ix_risk_predictions_sample_insufficient", "risk_predictions", ["sample_insufficient"])

    op.create_table(
        "alert_cases",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("prediction_id", BIGINT_PK, sa.ForeignKey("risk_predictions.id"), nullable=False, unique=True),
        sa.Column("assigned_official_id", sa.Integer(), sa.ForeignKey("officials.id")),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("confirmed_cause_code", sa.String(50)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alert_cases_assigned_official_id", "alert_cases", ["assigned_official_id"])
    op.create_index("ix_alert_cases_status", "alert_cases", ["status"])

    op.create_table(
        "alert_evidences",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("alert_id", BIGINT_PK, sa.ForeignKey("alert_cases.id"), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("metric_code", sa.String(50), nullable=False),
        sa.Column("observed_value", sa.Float()),
        sa.Column("baseline_value", sa.Float()),
        sa.Column("direction", sa.String(20)),
        sa.Column("quality_flag", sa.String(20), nullable=False, server_default="verified"),
        sa.Column("source_quarter_code", sa.Integer()),
        sa.Column("description", sa.Text()),
        sa.Column("verified_by_official_id", sa.Integer(), sa.ForeignKey("officials.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_alert_evidences_alert_id", "alert_evidences", ["alert_id"])

    op.create_table(
        "policy_programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_code", sa.String(50), nullable=False, unique=True),
        sa.Column("program_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "policy_actions",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("alert_id", BIGINT_PK, sa.ForeignKey("alert_cases.id"), nullable=False),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("policy_programs.id"), nullable=False),
        sa.Column("official_id", sa.Integer(), sa.ForeignKey("officials.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="reviewing"),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("budget_amount", sa.Numeric(15, 2)),
        sa.Column("target_store_count", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_policy_actions_alert_id", "policy_actions", ["alert_id"])
    op.create_index("ix_policy_actions_status", "policy_actions", ["status"])

    op.create_table(
        "policy_outcomes",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("action_id", BIGINT_PK, sa.ForeignKey("policy_actions.id"), nullable=False),
        sa.Column("evaluation_quarter_code", sa.Integer(), nullable=False),
        sa.Column("baseline_closure_rate", sa.Float()),
        sa.Column("observed_closure_rate", sa.Float()),
        sa.Column("baseline_store_count", sa.Integer()),
        sa.Column("observed_store_count", sa.Integer()),
        sa.Column("evaluation_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("action_id", "evaluation_quarter_code", name="uq_action_evaluation_quarter"),
    )
    op.create_index("ix_policy_outcomes_action_id", "policy_outcomes", ["action_id"])


def downgrade() -> None:
    op.drop_table("policy_outcomes")
    op.drop_table("policy_actions")
    op.drop_table("policy_programs")
    op.drop_table("alert_evidences")
    op.drop_table("alert_cases")
    op.drop_table("risk_predictions")
    op.drop_table("model_runs")
    op.drop_table("commercial_quarters")
    op.drop_table("data_batches")
    op.drop_table("industry_categories")
    op.drop_table("admin_areas")
