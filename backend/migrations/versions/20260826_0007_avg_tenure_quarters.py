"""셀 평균 업력(분기 수)을 상권 분기 지표에 적재한다.

값은 `data/processed/cell_train_table.csv`의 `평균업력_분기수`에 이미 있다. 모델이 학습
피처로 쓰던 값인데 DB에는 올라오지 않아 API가 읽을 수 없었다.

## 무엇에 쓰는가 — 점수가 아니라 표시용이다

원래는 노다지 종합점수의 유동인구 자리(가중 0.15)에 '정착도' 축으로 넣으려 했다.
**계측 결과 그 용도로는 쓰지 않기로 했다.**

2026-08-26, 표본충분 231셀 기준으로 각 후보 축과 최근 1년 누적 폐업률의 스피어만:

    평균 업력            -0.064
    보정 개업률          +0.420   ← 방향이 반대(개업 많은 곳이 폐업도 많다)
    읍면동 전체 점포수    -0.042
    업종 점포수          +0.026
    업종 포화도          +0.068

업력 1위 셀(송산면 식료품 소매, 107.9분기)의 폐업률이 11.93%로 가장 높은 축에 속하고,
업력 최하위(동탄6동 전문 디자인, 9.1분기)는 0.75%다. 업력은 안전도가 아니라 사실상
**신도시 여부의 대리변수**다 — 상위는 면·읍, 하위는 동탄이다. 이걸 점수에 넣으면
"동탄은 감점, 면지역은 가점"이 되고, 그건 창업 적합도로 방어할 수 없다.

그래서 이 컬럼은 **추천 카드의 표시 지표**로만 쓴다("이 상권 점포들이 평균 몇 분기나
유지됐는가"). 판단 재료로는 의미가 있고, 가중치를 부여할 근거는 없다.

원본을 지우지 않는 것과 같은 원칙이다 — 재료는 남기되 주장하지 않는다.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260826_0007"
down_revision = "20260826_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commercial_quarters",
        sa.Column("avg_tenure_quarters", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commercial_quarters", "avg_tenure_quarters")
