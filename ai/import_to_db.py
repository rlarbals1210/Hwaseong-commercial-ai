"""
CSV → PostgreSQL 임포트
사용법:
    python ai/import_to_db.py --table scores   # scores.csv → score_data
    python ai/import_to_db.py --table risk     # risk_index.csv → risk_index
    python ai/import_to_db.py --table all      # 전체
"""
import argparse
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv(".env")
engine = create_engine(os.getenv("DATABASE_URL"))


def import_scores():
    df = pd.read_csv("data/processed/scores.csv", encoding="utf-8-sig")
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE score_data RESTART IDENTITY"))
        conn.commit()
    df.to_sql("score_data", engine, if_exists="append", index=False)
    print(f"score_data 임포트 완료: {len(df):,}행")


def import_risk():
    df = pd.read_csv("data/processed/risk_index.csv", encoding="utf-8-sig")
    df["이상탐지_플래그"] = df["이상탐지_플래그"].astype(bool)
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE risk_index RESTART IDENTITY"))
        conn.commit()
    df.to_sql("risk_index", engine, if_exists="append", index=False)
    print(f"risk_index 임포트 완료: {len(df):,}행")


def import_commercial():
    df = pd.read_csv("data/processed/final_dataset.csv", encoding="utf-8-sig", low_memory=False)
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE commercial_data RESTART IDENTITY"))
        conn.commit()
    df.to_sql("commercial_data", engine, if_exists="append", index=False, chunksize=1000)
    print(f"commercial_data 임포트 완료: {len(df):,}행 (최신 분기: {df['기준_년분기_코드'].max()})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", choices=["scores", "risk", "commercial", "all"], default="all")
    args = parser.parse_args()

    if args.table in ("scores", "all"):
        import_scores()
    if args.table in ("risk", "all"):
        import_risk()
    if args.table in ("commercial", "all"):
        import_commercial()
