"""add contact log, prediction contributions, threshold sets, and area summaries"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0002"
down_revision = "20260818_0001"
branch_labels = None
depends_on = None
BIGINT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "risk_threshold_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("data_batches.id"), nullable=False),
        sa.Column("quarter_code", sa.Integer(), nullable=False),
        sa.Column("avg_closure_rate_pct", sa.Float(), nullable=False),
        sa.Column("danger_threshold_pct", sa.Float(), nullable=False),
        sa.Column("area_ratio_avg_pct", sa.Float(), nullable=False),
        sa.Column("area_ratio_danger_pct", sa.Float(), nullable=False),
        sa.Column("sample_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("batch_id", "quarter_code", name="uq_threshold_batch_quarter"),
    )
    op.create_index(
        "ix_risk_threshold_sets_batch_id", "risk_threshold_sets", ["batch_id"]
    )
    op.create_index(
        "ix_risk_threshold_sets_quarter_code", "risk_threshold_sets", ["quarter_code"]
    )

    op.add_column(
        "commercial_quarters", sa.Column("risk_grade", sa.String(10), nullable=True)
    )
    op.add_column(
        "commercial_quarters",
        sa.Column(
            "sample_insufficient",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "commercial_quarters", sa.Column("threshold_set_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_commercial_quarters_threshold_set",
        "commercial_quarters",
        "risk_threshold_sets",
        ["threshold_set_id"],
        ["id"],
    )
    op.create_index(
        "ix_commercial_quarters_sample_insufficient",
        "commercial_quarters",
        ["sample_insufficient"],
    )
    op.create_index(
        "ix_commercial_quarters_threshold_set_id",
        "commercial_quarters",
        ["threshold_set_id"],
    )

    op.create_table(
        "area_quarter_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("admin_areas.id"), nullable=False),
        sa.Column("quarter_code", sa.Integer(), nullable=False),
        sa.Column("total_cells", sa.Integer(), nullable=False),
        sa.Column("sample_sufficient_cells", sa.Integer(), nullable=False),
        sa.Column("risk_cells", sa.Integer(), nullable=False),
        sa.Column("risk_industry_ratio_pct", sa.Float(), nullable=False),
        sa.Column("area_risk_grade", sa.String(10), nullable=True),
        sa.Column("avg_trend_slope", sa.Float(), nullable=True),
        sa.Column("threshold_set_id", sa.Integer(), sa.ForeignKey("risk_threshold_sets.id")),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("data_batches.id"), nullable=False),
        sa.UniqueConstraint("area_id", "quarter_code", name="uq_area_quarter"),
    )
    op.create_index(
        "ix_area_quarter_summaries_area_id", "area_quarter_summaries", ["area_id"]
    )
    op.create_index(
        "ix_area_quarter_summaries_quarter_code",
        "area_quarter_summaries",
        ["quarter_code"],
    )
    op.create_index(
        "ix_area_quarter_summaries_batch_id", "area_quarter_summaries", ["batch_id"]
    )

    op.create_table(
        "prediction_contributions",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column(
            "prediction_id", BIGINT_PK, sa.ForeignKey("risk_predictions.id"), nullable=False
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("factor_code", sa.String(40), nullable=False),
        sa.Column("factor_label", sa.String(60), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("share_pct", sa.Float(), nullable=False),
        sa.Column("contribution_value_internal", sa.Float()),
        sa.Column("source_features", sa.JSON()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "prediction_id", "rank", name="uq_contribution_prediction_rank"
        ),
        sa.CheckConstraint(
            "direction IN ('risk','safe')", name="ck_contribution_direction"
        ),
        sa.CheckConstraint("rank BETWEEN 1 AND 5", name="ck_contribution_rank"),
        sa.CheckConstraint(
            "share_pct >= 0 AND share_pct <= 100", name="ck_contribution_share"
        ),
    )
    op.create_index(
        "ix_prediction_contributions_prediction_id",
        "prediction_contributions",
        ["prediction_id"],
    )

    op.create_table(
        "alert_contacts",
        sa.Column("id", BIGINT_PK, primary_key=True, autoincrement=True),
        sa.Column("alert_id", BIGINT_PK, sa.ForeignKey("alert_cases.id"), nullable=False),
        sa.Column("official_id", sa.Integer(), sa.ForeignKey("officials.id"), nullable=False),
        sa.Column("contacted_on", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("target_scope", sa.String(20), nullable=False, server_default="cell"),
        sa.Column("contacted_store_count", sa.Integer()),
        sa.Column("store_refs", sa.JSON()),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "channel IN ('visit','phone','sms','email','meeting','other')",
            name="ck_alert_contacts_channel",
        ),
        sa.CheckConstraint(
            "outcome IN ('connected','no_answer','declined','applied','pending')",
            name="ck_alert_contacts_outcome",
        ),
        sa.CheckConstraint(
            "target_scope IN ('cell','store_subset')", name="ck_alert_contacts_scope"
        ),
    )
    op.create_index("ix_alert_contacts_alert_id", "alert_contacts", ["alert_id"])
    op.create_index("ix_alert_contacts_official_id", "alert_contacts", ["official_id"])
    op.create_index("ix_alert_contacts_contacted_on", "alert_contacts", ["contacted_on"])
    op.create_index(
        "ix_alert_contacts_alert_date", "alert_contacts", ["alert_id", "contacted_on"]
    )

    # 기존 자유 문자열을 A/B/C 세 영역의 확정 코드로 먼저 정규화한 뒤 제약을 건다.
    op.execute(
        """
        UPDATE alert_evidences
        SET evidence_type = CASE evidence_type
            WHEN 'OBSERVED_SIGNAL' THEN 'confirmed_signal'
            WHEN 'MODEL_CONTRIBUTION' THEN 'model_contribution'
            WHEN 'CONTEXT_INDICATOR' THEN 'model_contribution'
            WHEN 'OFFICIAL_CONFIRMATION' THEN 'field_check'
            ELSE evidence_type
        END
        """
    )
    op.create_check_constraint(
        "ck_alert_evidences_type",
        "alert_evidences",
        "evidence_type IN ('confirmed_signal','model_contribution','field_check')",
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_model_runs_single_active "
            "ON model_runs (is_active) WHERE is_active"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_model_runs_single_active")

    op.drop_constraint("ck_alert_evidences_type", "alert_evidences", type_="check")

    op.drop_index("ix_alert_contacts_alert_date", table_name="alert_contacts")
    op.drop_index("ix_alert_contacts_contacted_on", table_name="alert_contacts")
    op.drop_index("ix_alert_contacts_official_id", table_name="alert_contacts")
    op.drop_index("ix_alert_contacts_alert_id", table_name="alert_contacts")
    op.drop_table("alert_contacts")

    op.drop_index(
        "ix_prediction_contributions_prediction_id",
        table_name="prediction_contributions",
    )
    op.drop_table("prediction_contributions")

    op.drop_index("ix_area_quarter_summaries_batch_id", table_name="area_quarter_summaries")
    op.drop_index(
        "ix_area_quarter_summaries_quarter_code", table_name="area_quarter_summaries"
    )
    op.drop_index("ix_area_quarter_summaries_area_id", table_name="area_quarter_summaries")
    op.drop_table("area_quarter_summaries")

    op.drop_index("ix_commercial_quarters_threshold_set_id", table_name="commercial_quarters")
    op.drop_index(
        "ix_commercial_quarters_sample_insufficient", table_name="commercial_quarters"
    )
    op.drop_constraint(
        "fk_commercial_quarters_threshold_set",
        "commercial_quarters",
        type_="foreignkey",
    )
    op.drop_column("commercial_quarters", "threshold_set_id")
    op.drop_column("commercial_quarters", "sample_insufficient")
    op.drop_column("commercial_quarters", "risk_grade")

    op.drop_index("ix_risk_threshold_sets_quarter_code", table_name="risk_threshold_sets")
    op.drop_index("ix_risk_threshold_sets_batch_id", table_name="risk_threshold_sets")
    op.drop_table("risk_threshold_sets")
