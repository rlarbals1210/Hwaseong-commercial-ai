"""지원사업 매칭 요건 컬럼 추가

policy_programs에 이름과 설명만 있어 "이 상권에 연결 가능한 지원사업"을 계산할 수 없었다.

두 종류를 구분해서 담는다.
  (가) 매칭 조건   상권 유형·등급 기반. 우리 처방 로직이므로 근거가 있다
  (나) 자격 요건   업력·한도·신청 기간 등. 실제 공고문에서 확인해야 하며 추정하지 않는다

(나)가 비어 있으면 requires_verification = true로 두고 화면에 "요건 확인 필요"로 표시한다.
공고문을 확인하지 않은 값을 채워 넣으면 담당자가 그대로 안내하게 되므로 위험하다.

Revision ID: 20260823_0005
Revises: 20260822_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20260823_0005"
down_revision = "20260822_0004"
branch_labels = None
depends_on = None

COLUMNS = [
    ("target_cell_types", sa.JSON()),
    ("target_risk_grades", sa.JSON()),
    ("discouraged_cell_types", sa.JSON()),
    ("match_reason", sa.Text()),
    ("owner_department", sa.String(length=80)),
    ("legal_basis", sa.String(length=200)),
    ("apply_period", sa.String(length=120)),
    ("support_limit_text", sa.String(length=120)),
    ("exclusion_note", sa.Text()),
    ("tenure_min_quarters", sa.Integer()),
    ("tenure_max_quarters", sa.Integer()),
]


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("policy_programs", sa.Column(name, type_, nullable=True))
    op.add_column(
        "policy_programs",
        sa.Column("requires_verification", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("policy_programs", "requires_verification")
    for name, _ in reversed(COLUMNS):
        op.drop_column("policy_programs", name)
