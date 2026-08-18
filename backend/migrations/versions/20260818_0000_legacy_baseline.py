"""create the legacy schema for fresh databases

Existing databases already created through Base.metadata.create_all must be stamped at this
revision before upgrading: alembic stamp 20260818_0000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260818_0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("기준_년분기_코드", sa.Integer()),
        sa.Column("행정동명", sa.String(50)),
        sa.Column("통합카테고리", sa.String(50)),
        sa.Column("당월매출합", sa.BigInteger()),
        sa.Column("점포수", sa.Integer()),
        sa.Column("총_유동인구_수", sa.Integer()),
        sa.Column("폐업_률_평균", sa.Float()),
        sa.Column("개업_율_평균", sa.Float()),
        sa.Column("업종_포화도", sa.Float()),
        sa.Column("경쟁강도", sa.Float()),
        sa.Column("업종_점포당매출", sa.BigInteger()),
        sa.Column("업종_매출점유율", sa.Float()),
        sa.Column("총_직장_인구_수", sa.Integer()),
        sa.Column("주거인구", sa.Integer()),
        sa.Column("월_평균_소득_금액", sa.Integer()),
        sa.Column("매출_20대합", sa.BigInteger()),
        sa.Column("매출_30대합", sa.BigInteger()),
        sa.Column("매출_40대합", sa.BigInteger()),
        sa.Column("매출_50대합", sa.BigInteger()),
        sa.Column("매출_60대이상합", sa.BigInteger()),
        sa.Column("월요일매출합", sa.BigInteger()),
        sa.Column("화요일매출합", sa.BigInteger()),
        sa.Column("수요일매출합", sa.BigInteger()),
        sa.Column("목요일매출합", sa.BigInteger()),
        sa.Column("금요일매출합", sa.BigInteger()),
        sa.Column("토요일매출합", sa.BigInteger()),
        sa.Column("일요일매출합", sa.BigInteger()),
        sa.Column("유동_20대", sa.Integer()),
        sa.Column("유동_30대", sa.Integer()),
        sa.Column("유동_40대", sa.Integer()),
        sa.Column("유동_50대", sa.Integer()),
        sa.Column("유동_60대이상", sa.Integer()),
        sa.UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_commercial_dong_cat_quarter"),
    )
    op.create_index("ix_commercial_data_id", "commercial_data", ["id"])
    op.create_index("ix_commercial_data_기준_년분기_코드", "commercial_data", ["기준_년분기_코드"])
    op.create_index("ix_commercial_data_행정동명", "commercial_data", ["행정동명"])
    op.create_index("ix_commercial_data_통합카테고리", "commercial_data", ["통합카테고리"])
    op.create_table(
        "score_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("행정동명", sa.String(50)),
        sa.Column("통합카테고리", sa.String(50)),
        sa.Column("기준_년분기_코드", sa.Integer()),
        sa.Column("성장확률", sa.Float()),
        sa.Column("등급", sa.String(2)),
        sa.Column("상위_퍼센트", sa.Float()),
        sa.Column("업종내_순위", sa.Integer()),
        sa.Column("업종내_전체동수", sa.Integer()),
        sa.UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_score_dong_cat_quarter"),
    )
    op.create_index("ix_score_data_id", "score_data", ["id"])
    op.create_index("ix_score_data_기준_년분기_코드", "score_data", ["기준_년분기_코드"])
    op.create_index("ix_score_data_행정동명", "score_data", ["행정동명"])
    op.create_index("ix_score_data_통합카테고리", "score_data", ["통합카테고리"])
    op.create_table(
        "officials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(50)),
    )
    op.create_index("ix_officials_id", "officials", ["id"])
    op.create_index("ix_officials_username", "officials", ["username"], unique=True)
    op.create_table(
        "risk_index",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("행정동명", sa.String(50)),
        sa.Column("통합카테고리", sa.String(50)),
        sa.Column("기준_년분기_코드", sa.Integer()),
        sa.Column("실제폐업률_pct", sa.Float()),
        sa.Column("위험등급", sa.String(10)),
        sa.Column("위험업종비율", sa.Float()),
        sa.Column("표본부족_플래그", sa.Boolean()),
        sa.Column("점포수", sa.Integer()),
        sa.Column("개업률_pct", sa.Float()),
        sa.Column("업종_포화도", sa.Float()),
        sa.Column("예측순위", sa.Integer()),
        sa.Column("성장확률", sa.Float()),
        sa.Column("트렌드_기울기", sa.Float()),
        sa.Column("이상탐지_플래그", sa.Boolean()),
        sa.UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_risk_dong_cat_quarter"),
    )
    op.create_index("ix_risk_index_id", "risk_index", ["id"])
    op.create_index("ix_risk_index_기준_년분기_코드", "risk_index", ["기준_년분기_코드"])
    op.create_index("ix_risk_index_행정동명", "risk_index", ["행정동명"])
    op.create_index("ix_risk_index_통합카테고리", "risk_index", ["통합카테고리"])


def downgrade() -> None:
    op.drop_table("risk_index")
    op.drop_table("officials")
    op.drop_table("score_data")
    op.drop_table("commercial_data")
