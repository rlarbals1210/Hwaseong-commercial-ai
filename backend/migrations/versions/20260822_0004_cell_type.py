"""상권 유형(고회전·쇠퇴·성장·정체) 컬럼 추가

위험도 한 축만으로는 어느 셀이든 결론이 "현장 확인" 하나였다. 개업률 축을 얹어
같은 "위험"이라도 처방이 갈리게 한다. 판정 기준은 각 분기 표본충분 셀의 중위값이며
산출 근거는 ai/cumulative.py 주석 참조.

Revision ID: 20260822_0004
Revises: 20260821_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260822_0004"
down_revision = "20260821_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commercial_quarters", sa.Column("cell_type", sa.String(length=20), nullable=True))
    op.create_index(
        "ix_commercial_quarters_quarter_cell_type",
        "commercial_quarters",
        ["quarter_code", "cell_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_commercial_quarters_quarter_cell_type", table_name="commercial_quarters")
    op.drop_column("commercial_quarters", "cell_type")
