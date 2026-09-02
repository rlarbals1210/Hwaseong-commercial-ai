"""검증된 월의 읍면동별 요일 유동인구 상대 패턴."""
from alembic import op
import sqlalchemy as sa

revision = "20260902_0010"
down_revision = "20260827_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "area_weekday_flows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("admin_areas.id"), nullable=False, index=True),
        sa.Column("month", sa.String(7), nullable=False, index=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("relative_index", sa.Float(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("area_id", "month", "weekday", name="uq_area_month_weekday"),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_flow_weekday"),
        sa.CheckConstraint("relative_index >= 0", name="ck_flow_index"),
    )


def downgrade():
    op.drop_table("area_weekday_flows")
