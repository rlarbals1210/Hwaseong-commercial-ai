"""읍면동 배후인구(등록인구) 분기 시계열을 적재할 자리를 만든다.

번호가 0007이 아니라 0009인 이유: 같은 날 팀원이 0007(avg_tenure_quarters)과
0008(store_clusters)을 올렸다. 셋 다 0006 뒤에 붙으면 alembic head가 갈라져
`alembic upgrade head`가 "Multiple head revisions" 로 멈춘다. 뒤에 이어 붙인다.

왜 이 데이터만 쓰는가 —
외부 데이터 3종 중 추이 그래프로 쓸 수 있는 건 등록인구 하나뿐이다.

  카드매출   업종 코드체계가 우리 데이터와 달라 같은 업종의 값이 2.3~524배까지 벌어진다.
  유동인구   2022년 1월에 측정 기준이 바뀌어 그 전후로 동별 값이 0~22배 튄다.
  등록인구   2020Q4~2026Q2 분기별, 화성시 29개 읍면동 전부. 결측 1.6%(동탄9동 신설 전).

무엇에 쓰는가 —
등급·상권유형 판정에는 **쓰지 않는다**. 인구증감과 폐업률의 순위상관은 +0.238로 약하고
부호도 직관과 반대다(정남면 인구 -9.8%인데 폐업률 0.04, 봉담읍 +25.9%인데 0.05).
판정 축으로 넣으면 근거 없는 가중치가 된다.

같은 "쇠퇴·위험"이라도 배후인구가 늘고 있으면 원인이 수요 부족이 아니라는 뜻이므로,
담당자가 현장에서 무엇을 볼지 갈린다. 그 목적의 **설명 근거**로만 화면에 붙인다.

결측을 0으로 채우지 않는다 —
동탄9동은 2023Q3부터 값이 있다. 그 전은 인구가 0명이었던 게 아니라 동이 없었다.
0으로 채우면 화면에 "인구 폭증"으로 그려진다(개업률에서 이미 겪은 결함이다).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260827_0009"
down_revision = "20260826_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "area_population_quarters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("admin_areas.id"), nullable=False, index=True),
        sa.Column("quarter_code", sa.Integer(), nullable=False, index=True),
        sa.Column("total_population", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="kosis_registered"),
        sa.UniqueConstraint("area_id", "quarter_code", name="uq_area_population_quarter"),
    )


def downgrade() -> None:
    op.drop_table("area_population_quarters")
