"""공개 지도용 점포 격자 집계를 추가한다.

개별 점포 위치를 적재하지 않고 0.002도 격자 중심과 점포 수만 저장한다. 공개 API는
이 중 3개 미만 격자도 숨겨 단일 점포 위치가 드러나지 않게 한다.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260826_0008"
down_revision = "20260826_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_clusters",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("industry_id", sa.Integer(), nullable=False),
        sa.Column("quarter_code", sa.Integer(), nullable=False),
        sa.Column("grid_x", sa.Integer(), nullable=False),
        sa.Column("grid_y", sa.Integer(), nullable=False),
        sa.Column("center_lng", sa.Float(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("store_count", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("store_count > 0", name="ck_store_clusters_positive_count"),
        sa.ForeignKeyConstraint(["batch_id"], ["data_batches.id"]),
        sa.ForeignKeyConstraint(["industry_id"], ["industry_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "industry_id", "quarter_code", "grid_x", "grid_y",
            name="uq_store_cluster_industry_quarter_grid",
        ),
    )
    op.create_index("ix_store_clusters_batch_id", "store_clusters", ["batch_id"])
    op.create_index("ix_store_clusters_industry_id", "store_clusters", ["industry_id"])
    op.create_index("ix_store_clusters_quarter_code", "store_clusters", ["quarter_code"])


def downgrade() -> None:
    op.drop_index("ix_store_clusters_quarter_code", table_name="store_clusters")
    op.drop_index("ix_store_clusters_industry_id", table_name="store_clusters")
    op.drop_index("ix_store_clusters_batch_id", table_name="store_clusters")
    op.drop_table("store_clusters")
