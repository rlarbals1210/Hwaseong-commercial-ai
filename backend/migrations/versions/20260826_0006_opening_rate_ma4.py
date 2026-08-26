"""보정 개업률(4분기 이동평균)을 상권 분기 지표에 적재한다.

왜 필요한가 —
상권유형 4분류는 `개업_율_보정_ma4`(ai/fix_opening_rate.py가 만드는 보정 컬럼)로 판정하는데,
DB에는 원본 `개업_율_평균`만 저장하고 있었다. 그래서 한 화면에서 유형 배지와 개업률 숫자가
서로 다른 컬럼 기반이었고, 판정 근거를 화면에서 확인할 방법이 없었다.

원본 컬럼에는 수록 지연 결함이 남아 있다(2026-08-26 실측, 표본충분 231셀 기준):

    분기      0인 셀 비율   평균
    2024Q3      77.0%      0.26%
    2024Q4       0.0%     28.48%
    2025Q4      26.8%      3.27%

즉 화면에 뜨는 개업률의 **4분의 1이 0.0%** 였다. 보정 컬럼은 0인 셀이 5.2%다.

원본을 지우지는 않는다. 두 값의 차이가 보정의 근거이고, 감사에서 물으면 둘 다 보여야 한다.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260826_0006"
down_revision = "20260823_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commercial_quarters",
        sa.Column("opening_rate_ma4", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commercial_quarters", "opening_rate_ma4")
