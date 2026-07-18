from sqlalchemy import Column, Integer, String, Float, Boolean, BigInteger, UniqueConstraint
from .database import Base


class CommercialData(Base):
    __tablename__ = "commercial_data"
    __table_args__ = (
        UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_commercial_dong_cat_quarter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    기준_년분기_코드 = Column(Integer, index=True)
    행정동명 = Column(String(50), index=True)
    통합카테고리 = Column(String(50), index=True)

    당월매출합 = Column(BigInteger, nullable=True)
    점포수 = Column(Integer, nullable=True)
    총_유동인구_수 = Column(Integer, nullable=True)
    폐업_률_평균 = Column(Float, nullable=True)
    개업_율_평균 = Column(Float, nullable=True)
    업종_포화도 = Column(Float, nullable=True)
    경쟁강도 = Column(Float, nullable=True)
    업종_점포당매출 = Column(BigInteger, nullable=True)
    업종_매출점유율 = Column(Float, nullable=True)

    총_직장_인구_수 = Column(Integer, nullable=True)
    주거인구 = Column(Integer, nullable=True)
    월_평균_소득_금액 = Column(Integer, nullable=True)

    매출_20대합 = Column(BigInteger, nullable=True)
    매출_30대합 = Column(BigInteger, nullable=True)
    매출_40대합 = Column(BigInteger, nullable=True)
    매출_50대합 = Column(BigInteger, nullable=True)
    매출_60대이상합 = Column(BigInteger, nullable=True)

    월요일매출합 = Column(BigInteger, nullable=True)
    화요일매출합 = Column(BigInteger, nullable=True)
    수요일매출합 = Column(BigInteger, nullable=True)
    목요일매출합 = Column(BigInteger, nullable=True)
    금요일매출합 = Column(BigInteger, nullable=True)
    토요일매출합 = Column(BigInteger, nullable=True)
    일요일매출합 = Column(BigInteger, nullable=True)

    유동_20대 = Column(Integer, nullable=True)
    유동_30대 = Column(Integer, nullable=True)
    유동_40대 = Column(Integer, nullable=True)
    유동_50대 = Column(Integer, nullable=True)
    유동_60대이상 = Column(Integer, nullable=True)


class ScoreData(Base):
    __tablename__ = "score_data"
    __table_args__ = (
        UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_score_dong_cat_quarter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    행정동명 = Column(String(50), index=True)
    통합카테고리 = Column(String(50), index=True)
    기준_년분기_코드 = Column(Integer, index=True)
    성장확률 = Column(Float)
    등급 = Column(String(2))
    상위_퍼센트 = Column(Float, nullable=True)
    업종내_순위 = Column(Integer, nullable=True)
    업종내_전체동수 = Column(Integer, nullable=True)


class Official(Base):
    __tablename__ = "officials"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String(50), nullable=True)


class RiskIndex(Base):
    __tablename__ = "risk_index"
    __table_args__ = (
        UniqueConstraint("행정동명", "통합카테고리", "기준_년분기_코드", name="uq_risk_dong_cat_quarter"),
    )

    id = Column(Integer, primary_key=True, index=True)
    행정동명 = Column(String(50), index=True)
    통합카테고리 = Column(String(50), index=True)
    기준_년분기_코드 = Column(Integer, index=True)
    폐업위험점수 = Column(Float)
    트렌드_기울기 = Column(Float, nullable=True)
    이상탐지_플래그 = Column(Boolean, default=False)
    공실위험지수 = Column(Float, nullable=True)
