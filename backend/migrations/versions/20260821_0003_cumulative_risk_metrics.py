"""4분기 누적 위험 지표 컬럼 추가

단일 분기 폐업률로 등급과 순위를 매기던 것을 4분기 누적으로 바꾸면서 필요한 컬럼을 추가한다.

배경 (2026-08-20 검증)
  분기 간 순위 상관   단일 분기 +0.296  ->  4분기 누적 +0.857
  Top10 유지         단일 분기 1.0개   ->  4분기 누적 5.4개
  등급 기준선        단일 분기 6.00~18.76%로 3배 요동 -> 분위수 기준으로 안정화

기존 closure_rate(단일 분기)는 의미를 바꾸지 않고 그대로 둔다. 화면 표시와 등급 판정만
새 컬럼을 쓴다. 되돌릴 때 데이터 손실이 없도록 추가만 하고 삭제하지 않는다.

Revision ID: 20260821_0003
Revises: 20260818_0002
"""
from alembic import op
import sqlalchemy as sa


revision = "20260821_0003"
down_revision = "20260818_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 4분기 누적 폐업 지표. 전 분기에 대해 채우되 등급은 최신 분기에만 매긴다.
    op.add_column(
        "commercial_quarters",
        sa.Column("closure_rate_cum4", sa.Float(), nullable=True),
    )
    op.add_column(
        "commercial_quarters",
        sa.Column("closure_rate_lower4", sa.Float(), nullable=True),
    )
    op.add_column(
        "commercial_quarters",
        sa.Column("closure_count_cum4", sa.Integer(), nullable=True),
    )

    # 기준선 메타. danger_threshold_pct가 상위 10% 경계, caution이 상위 30% 경계다.
    op.add_column(
        "risk_threshold_sets",
        sa.Column("caution_threshold_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "risk_threshold_sets",
        sa.Column("window_quarters", sa.Integer(), nullable=True, server_default="4"),
    )
    op.add_column(
        "risk_threshold_sets",
        sa.Column("method", sa.String(length=40), nullable=True),
    )

    # 정렬용 인덱스 — 조기경보 목록이 신뢰하한 내림차순으로 최신 분기를 훑는다.
    op.create_index(
        "ix_commercial_quarters_quarter_lower4",
        "commercial_quarters",
        ["quarter_code", "closure_rate_lower4"],
    )


def downgrade() -> None:
    op.drop_index("ix_commercial_quarters_quarter_lower4", table_name="commercial_quarters")
    op.drop_column("risk_threshold_sets", "method")
    op.drop_column("risk_threshold_sets", "window_quarters")
    op.drop_column("risk_threshold_sets", "caution_threshold_pct")
    op.drop_column("commercial_quarters", "closure_count_cum4")
    op.drop_column("commercial_quarters", "closure_rate_lower4")
    op.drop_column("commercial_quarters", "closure_rate_cum4")
