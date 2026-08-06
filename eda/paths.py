"""
eda/ 노트북 전체가 공유하는 경로 상수.

RAW_DATA_DIR(.env)이 가리키는 폴더 안의 실제 데이터셋 폴더명이 팀원마다/시점마다
바뀔 수 있으므로(예: "Hwaseong-commercial-ai-main-dataset" -> "hwaseong-commercial-dataset"),
이 파일 한 곳에서만 하위 폴더명을 정의하고 노트북에서는 이 상수만 import해서 쓴다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", str(PROJECT_ROOT / "data" / "raw")))
RAW_DIR = RAW_DATA_DIR / "Hwaseong-commercial-ai-main-dataset"

PROCESSED_DATA_DIR = Path(os.getenv("PROCESSED_DATA_DIR", str(PROJECT_ROOT / "data" / "processed")))

# 소진공 상가(상권)정보 21개 분기 zip
SBIZ_DIR = RAW_DIR / "소상공인시장진흥공단_상가(상권)정보_분기별데이터"
SBIZ_CATEGORY_CODE_CSV = SBIZ_DIR / "소상공인시장진흥공단_상가(상권)정보 업종코드_20230228.csv"

# 인허가데이터 13종 (12종 + 학원교습소정보)
PERMIT_DIR = RAW_DIR / "화성시_인허가데이터"

# 카드매출
CARD_SALES_CSV = RAW_DIR / "card_sales_hwaseong.csv"

# 유동인구
FLOATING_POP_BROKEN_CSV = RAW_DIR / "유동인구_화성시_행정동_시간대별.csv"
FLOATING_POP_CSV = RAW_DIR / "floating_pop_hwaseong.csv"

# KOSIS
KOSIS_HOUSEHOLD_POP_CSV = RAW_DIR / "읍·면·동별_세대_및_등록인구_20260724063340.csv"
KOSIS_BUSINESS_CSV = RAW_DIR / "산업별_읍면동별_사업체수_및_종사자수_20260724063757.csv"
POP_TREND_CSV = RAW_DIR / "화성시_인구동향_시계열.csv"

# R-ONE 임대동향
RENT_VACANCY_DIR = RAW_DIR / "임대동향 지역별 공실률"
RENT_INDEX_DIR = RAW_DIR / "임대동향 지역별 임대가격지수(시계열)데이터"

# 행정구역 코드/목록
LEGAL_DONG_CODE_TXT = RAW_DIR / "법정동코드 전체자료" / "법정동코드 전체자료.txt"
GYEONGGI_DONG_LIST_CSV = RAW_DIR / "경기도_읍면동_리스트.csv"

# Phase 2/3 산출물 (점포단위/셀단위 접두사로 구분)
STORE_PANEL_CSV = PROCESSED_DATA_DIR / "store_panel.csv"
STORE_LABELS_CSV = PROCESSED_DATA_DIR / "store_labels.csv"
STORE_TRAIN_TABLE_CSV = PROCESSED_DATA_DIR / "store_train_table.csv"
CELL_TRAIN_TABLE_CSV = PROCESSED_DATA_DIR / "cell_train_table.csv"
MODEL_STORE_RESULTS_JSON = PROCESSED_DATA_DIR / "model_store_results.json"
MODEL_CELL_RESULTS_JSON = PROCESSED_DATA_DIR / "model_cell_results.json"
LGBM_MODEL_STORE_PKL = PROCESSED_DATA_DIR / "lgbm_model_store.pkl"
LGBM_MODEL_CELL_PKL = PROCESSED_DATA_DIR / "lgbm_model_cell.pkl"
