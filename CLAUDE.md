# 화성시 소상공인 AI 정책지원 플랫폼 — Claude Code 작업 가이드

## 프로젝트 개요
**프로젝트명: 리버스 노다지(Reverse Nodaji)** — 제1회 화성 AI·DATA 기반 솔루션 경진대회(H-AIDA) 출품작.
화성시 소상공인 폐업 위험을 AI로 조기경보하고 정책자금 배분 우선순위를 제시하는 웹앱.

**핵심 개념**: "AI가 위험을 먼저 발견해 공무원에게 알린다" (경보 중심, 탐색 중심이 아님)

**이중 목표**: ① H-AIDA 경진대회 수상 ② 데이터 분석(DA) 포트폴리오 구축. 참가자는 협성대학교 재학생.
자유주제를 택한 이유는 종속변수(성장/폐업)가 명확한 예측 문제라 정확도·F1·AUC로 객관적 성능 검증이 가능해 DA 역량 증명에 유리하기 때문. (지정과제 4번 '공영주차장 최적 입지'는 정답지 없는 최적화 문제라 미선택.)

---

## 공모전 정보

| 항목 | 내용 |
|------|------|
| 주최 | 화성시 AI스마트전략실 빅데이터팀 |
| 과제 수행 | 2026.6.8 ~ 8.28 (12주) |
| 서면심사 | 2026년 8월 말 |
| **본선 발표** | **2026.9.17(목), 화성시청 대강당, 7분+Q&A 3분** |
| 최종 제출 | 8.28(금) 18:00 마감 |
| 담당 연락처 | tkooya09@korea.kr / 031-5189-2090 (빅데이터팀 신환철·전명구·이동재) |

### 주제 등록: 자유주제
공식 12개 과제에 소상공인 관련 과제 없음 → 자유주제로 출품 (운영진 사전 승인 필요).
붙임1 기타 안건에 "소상공인 관련 앱·플랫폼 개발 등"이 예시로 언급되어 있어 승인 가능성 높음.

### 필수 산출물 (8/28 제출)
| 산출물 | 분량 | 마감 |
|--------|------|------|
| 과제계획서 | A4 5p 이내 (PDF) | **6/26** |
| 데이터 분석 결과보고서 | A4 15~20p (PDF) | 8/28 |
| 소스코드 | GitHub Repository | 8/28 |
| 시제품·대시보드 | 웹앱 배포 URL | 8/28 |
| 발표자료 | PPT 10~15장 (본선 3일 전 9/14 사전 제출) | 8/28 |
| 정책 적용 제안서 | A4 2~3p | 8/28 |

### 심사 항목 (총 100점)
- 문제 정의 20점 / 데이터·AI 활용 25점 / 정책 적용 25점 / 시민 체감 20점 / 발표 10점

### AI 사용 제약 (중요)
- AI 생성 코드·텍스트 그대로 제출 금지 (검증·재구성 필수)
- **외부 AI API에 행정데이터 원본 송신 금지** → Gemini 등 텍스트 생성 AI 사용 불가
- 대회 종료 후 3개월 이내 제공 데이터 완전 폐기

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 프론트엔드 | React 19 + Vite (포트 5174) |
| 백엔드 | FastAPI + Uvicorn (포트 8000) |
| ML | LightGBM (이진분류: 성장/폐업 예측) |
| DB | PostgreSQL + SQLAlchemy |
| 지도 | Naver Maps JS API v3 (CDN, NCP 다이나믹 맵) |
| 시각화 | matplotlib (choropleth 그리드, 4분면 매트릭스, 파이프라인 다이어그램) |
| AI 텍스트 | 없음 — LightGBM 예측값으로 대체 |

**아키텍처 참고:** 이전 프로젝트 '노다지'는 Django/DRF/Celery/Redis/PostgreSQL/AWS 스택이었으나, 이번엔 코드 재사용 없이 공간분석 방법론·도메인 지식·임대료 추정 로직·과거 실패 교훈만 계승한다. ("코드는 버리고 경험은 챙긴다.")

---

## 서버 실행

### 백엔드 (포트 8000)
```bash
cd hwaseong-commercial-ai
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### 프론트엔드 (포트 5174)
```bash
cd frontend
npm install
npm run dev
```

### 환경변수
**루트 `.env`**
```
DATABASE_URL=postgresql://postgres:password@localhost:5432/hwaseong_db
RAW_DATA_DIR=data/raw            ← 팀원별 원본 데이터 위치가 다를 수 있어 경로를 .env로 분리 (데이터 수령 후 적용 예정)
PROCESSED_DATA_DIR=data/processed
```

**`frontend/.env`**
```
VITE_NAVER_MAP_CLIENT_ID=       ← NCP Maps(Dynamic Map) Client ID
VITE_API_BASE=http://localhost:8000
```

네이버 지도 API 키 보관 위치·발급 방법·흔한 실수는 [README.md](README.md) 참고.

---

## 디렉토리 구조

```
hwaseong-commercial-ai/
├── .env
├── requirements.txt
├── CLAUDE.md
│
├── backend/                    # FastAPI
│   ├── main.py                 # 앱 진입점 + CORS
│   ├── database.py             # SQLAlchemy 세션
│   ├── models.py               # ORM 모델
│   ├── schemas.py              # Pydantic 스키마
│   ├── routers/
│   │   ├── alerts.py           # /api/alerts/
│   │   ├── policy.py           # /api/policy/
│   │   ├── analysis.py         # /api/analysis/
│   │   └── consultation.py     # /api/consultation/
│   └── services/
│       └── risk.py             # 폐업위험점수 계산 로직
│
├── frontend/                   # React 19 + Vite
│   ├── .env
│   ├── public/
│   │   └── hwaseong_emd.geojson  ← SGIS에서 생성 필요 (아래 참고)
│   └── src/
│       ├── App.jsx             # 라우팅 + 상단 네비게이션
│       ├── main.jsx
│       └── pages/
│           ├── DashboardPage.jsx   # 조기경보 Top 10 카드
│           ├── MapPage.jsx         # Naver Maps choropleth
│           ├── PolicyPage.jsx      # 4분면 정책자금 매트릭스
│           └── ConsultPage.jsx     # 창업 상담 조회
│
├── ai/                         # ML 파이프라인 (순서대로 실행)
│   ├── build_dataset.py        # raw CSV → final_dataset.csv
│   ├── train_model.py          # LightGBM 학습 → scores.csv
│   ├── build_risk_index.py     # 폐업위험점수 + 이상탐지 → risk_index.csv
│   └── import_to_db.py        # CSV → PostgreSQL
│
└── data/
    ├── raw/                    # 소상공인진흥공단 + 화성시 제공 데이터
    └── processed/
        ├── final_dataset.csv
        ├── scores.csv
        └── risk_index.csv
```

---

## MVP 기능 (동일 예측 엔진 재사용)

빌드 우선순위: **모델링·분석 80% / 툴링 20%.** 위험예측 엔진과 공실위험 지도(①②)가 핵심 구현 대상.

1. **위험예측 엔진** — LightGBM 이진분류 + 트렌드 이상탐지, 읍면동×업종 단위 폐업위험점수 산출
2. **공실위험 지도** — 읍면동 단위 choropleth 시각화 (MapPage)
3. **조기경보 Top 10** — 읍면동×업종 단위 고위험 리스트 (DashboardPage)
4. **정책자금 우선순위 매트릭스** — 폐업위험도(x) × 정책잠재력(y) 4분면, Q1(고위험+고잠재력)=1순위 (PolicyPage)
   - x축 = 폐업위험점수(확정) / **y축 '정책잠재력' 계산식 미확정 — 매출규모·점포수(수혜규모)·개업률(회복여력) 중 택일 후 문서에 명시할 것.** 심사 방어 논리에 직결됨
5. **창업 상담 조회** — 예비창업자 대상 읍면동×업종 창업 생존확률 + 근거 3가지 (ConsultPage)

### 프라이버시 설계 원칙
- 모든 출력은 **읍면동 × 업종 집계 단위** — 개별 점포 노출 없음 (원본 데이터가 집계 단위)
- 행정데이터 원본은 외부로 전송하지 않음 (공모전 규정)

---

## DB 모델 (backend/models.py)

### CommercialData
읍면동×업종×분기 상권 지표 (소상공인진흥공단 원본 기반)
- 주요 컬럼: `행정동명`, `통합카테고리`, `기준_년분기_코드`, `당월매출합`, `점포수`, `총_유동인구_수`, `폐업_률_평균`, `개업_율_평균`, `업종_포화도`, `경쟁강도`, `업종_점포당매출`

### ScoreData
행정동×업종 AI 성장확률 점수 (train_model.py 출력)
- 주요 컬럼: `행정동명`, `통합카테고리`, `기준_년분기_코드`, `성장확률` (0~100), `등급` (A/B/C/D), `업종내_순위`, `상위_퍼센트`

### RiskIndex
폐업위험지수 + 트렌드 이상탐지 (build_risk_index.py 출력)
- `폐업위험점수 = (100 - 성장확률) × 0.6 + 폐업_률_평균 × 0.4`
- `트렌드_기울기`: 최근 4분기 폐업률 선형회귀 기울기
- `이상탐지_플래그`: 기울기 > 전체 기울기 1 std → True
- `공실위험지수`: 읍면동 내 업종별 평균 폐업위험점수 × 0.7 + 이상탐지 비율 × 0.3

---

## API 엔드포인트

### 조기경보 (`/api/alerts/`)
| URL | 메서드 | 파라미터 | 설명 |
|-----|--------|----------|------|
| `/api/alerts/closure-risk` | GET | `limit=10`, `category`(선택) | Top N 고위험 읍면동×업종 |
| `/api/alerts/vacancy-risk/map` | GET | - | 읍면동별 공실위험지수 (choropleth용) |

### 정책자금 (`/api/policy/`)
| URL | 메서드 | 파라미터 | 설명 |
|-----|--------|----------|------|
| `/api/policy/fund-priority` | GET | `category`(선택) | 4분면 매트릭스 (Q1=고위험+고잠재력=1순위) |

### 분석 (`/api/analysis/`)
| URL | 메서드 | 파라미터 | 설명 |
|-----|--------|----------|------|
| `/api/analysis/dongs` | GET | - | 화성시 전체 읍면동 목록 |
| `/api/analysis/dong` | GET | `dong`, `category`, `quarter` | 읍면동 상권 분석 |
| `/api/analysis/score` | GET | `dong`, `category` | AI 성장확률 + 폐업위험점수 |
| `/api/analysis/categories` | GET | - | 전체 업종 목록 |
| `/api/analysis/quarters` | GET | `dong`(선택) | 가용 분기 목록 |

### 창업 상담 (`/api/consultation/`)
| URL | 메서드 | 파라미터 | 설명 |
|-----|--------|----------|------|
| `/api/consultation/startup` | GET | `dong`, `category` | 창업 생존확률 + 근거 3가지 |

---

## ML 파이프라인 실행 순서

데이터 수령 후 아래 순서로 실행:

```bash
# 1. 화성시 raw 데이터(시군구코드=41590) → final_dataset.csv
python ai/build_dataset.py --input data/raw/ --output data/processed/final_dataset.csv

# 2. LightGBM 학습 → scores.csv (AUC ≥ 0.60 목표, 0.55 수용)
python ai/train_model.py

# 3. 폐업위험지수 계산 → risk_index.csv
python ai/build_risk_index.py

# 4. PostgreSQL 임포트
python ai/import_to_db.py --table all
```

---

## GeoJSON 준비 (선행 작업)

화성시 읍면동 경계 shapefile → GeoJSON 변환:

```bash
pip install geopandas
python -c "
import geopandas as gpd
gdf = gpd.read_file('BND_EMD_PG.shp', encoding='cp949')
hw = gdf[gdf['SGG_CD'].str.startswith('41590')]
hw = hw.copy()
hw['dong_name'] = hw['EMD_KOR_NM']
hw.to_file('frontend/public/hwaseong_emd.geojson', driver='GeoJSON')
print(hw['dong_name'].tolist())
"
```

다운로드: SGIS 포털 (sgis.kostat.go.kr) → 행정구역경계 → 읍면동 → 경기도 화성시

### 화성시 읍면동 목록 (21개, 코드 앞 5자리 41590)
읍 4개: 우정읍, 향남읍, 남양읍, 봉담읍
면 9개: 팔탄면, 장안면, 양감면, 정남면, 비봉면, 마도면, 송산면, 서신면, 매송면
동 8개: 동탄1동, 동탄2동, 동탄3동, 동탄4동, 동탄5동, 동탄6동, 동탄7동, 동탄8동

---

## 데이터 출처 및 확보 전략

### 자체 수집
- 소상공인진흥공단 상권분석서비스 공공 API → 시군구코드 **41590** 필터
- 분기별 CSV 다운로드 → `data/raw/` 저장

### 화성시 제공 데이터 (요청 필요)
- 서식 3 (정보 제공 요청서) → tkooya09@korea.kr 제출
- 요청 항목: 읍면동별 폐업/개업 통계, 상권 활성화 지수, 임대료 시계열

### 필요 데이터 6종 및 확보 방법
| # | 데이터 | 필수도 | 확보 방법 |
|---|--------|--------|-----------|
| 1 | 상가 개·폐업 이력 | 필수(모델 정답값, 시계열 필요) | 담당자 직접 문의 |
| 2 | 유동인구 | 높음 | 담당자 문의(통신사 빅데이터 여부 확인) |
| 3 | 업종밀도 | 중간 | 폐업 데이터에서 파생 가능 |
| 4 | 임대료·공실률 | 중간 | 한국부동산원 공개데이터 |
| 5 | 정책자금 지원이력 | 높음(내부데이터) | 담당자 문의(비식별화 형태 요청) |
| 6 | 행정구역 경계 GIS | 낮음 | 공개데이터(행정안전부/SGIS) |

**담당자 문의 우선순위:** ① 상가 개·폐업 시계열 이력 존재 여부 → ⑤ 정책자금 지원이력 비식별화 제공 가능 여부 → ② 화성시 빅데이터팀의 통신사 유동인구 데이터 보유 여부.

---

## 12주 일정

| 주차 | 기간 | 핵심 마일스톤 |
|------|------|--------------|
| 3주 | 6/22–6/28 | **과제계획서 6/26 제출**, 데이터 수령 |
| 4주 | 6/29–7/5 | 데이터 전처리, ML 학습 |
| 5주 | 7/6–7/12 | **1차 중간점검**, API 완성 |
| 8주 | 7/27–8/2 | **시제품 1차 구현** |
| 9주 | 8/3–8/9 | **2차 중간점검**, 배포 |
| 12주 | 8/24–8/28 | **최종 제출 8/28 18:00** |
| 본선 | **9/17(목)** | 발표 7분 + Q&A 3분, 화성시청 대강당 |

---

## 발표 서사 (심사 항목 매핑)

```
[문제 정의 — 20점]  ※ 프레이밍 확정: 시 전체가 메인, 동탄2는 대표 케이스
메인 서사(시 전체): 화성시는 인구 100만·출생률 전국 1위 고성장 도시이나
  경기도 내 소상공인 폐업률 3위(7.12%)라는 역설적 구조
→ 공무원은 어디가 위험한지 사후에야 알 수 있다
대표 케이스(클로즈업): 동탄2신도시 — 인구는 느는데 상가 공실은 증가
  (시 전체 통계에 구체성을 더하는 예시로만 사용. 프레이밍 중심은 시 전체.
   화성시 주최 대회이므로 특정 지역 한정보다 시 전체 문제로 가는 것이 정책 적용가능성·데이터 신뢰성 측면에서 유리)

[데이터·AI — 25점]
소상공인진흥공단 분기별 데이터 + 화성시 제공 데이터
→ LightGBM 이진분류 + 트렌드 이상탐지 (선형회귀 기울기)

[정책 적용 — 25점]
발견(공실 지도) → 분석(조기경보 Top 10) → 행동(정책자금 우선순위)
각 기능 → 화성시 담당 부서 즉시 적용 시나리오

[시민 체감 — 20점]
창업 상담 조회: 예약 없이 3분 내 창업 적합도 분석
```

---

## 기존 Seoul 프로젝트와의 차이점

| 항목 | Seoul 프로젝트 | 화성시 프로젝트 |
|------|---------------|----------------|
| 위치 | `~/Desktop/Developer/commercial-area-analysis-ai/` | `~/Desktop/Developer/hwaseong-commercial-ai/` |
| 백엔드 | Django 5 | FastAPI |
| 행정구역 | 서울 25개 구 / 행정동 | 화성시 21개 읍면동 |
| GeoJSON | `seoul_gu.geojson`, `seoul_hangjeongdong.geojson` | `hwaseong_emd.geojson` |
| 목적 | 창업 입지 탐색 | 폐업 위험 조기경보 |
| AI 텍스트 | Gemini 2.5 Flash | 없음 (행정데이터 외부 전송 금지) |
| 데이터 필터 | 서울 전체 | 시군구코드 41590 (화성시) |
| ML 코드 | `ai/retrain_scores.py` | `ai/train_model.py` (동일 로직) |

---

## 협업 가이드라인 (Claude 사용 시 공통 준수사항)

### 작업 방식
- **구현 전 논의 먼저**: 코드·파일을 만들기 전에 접근 방식을 먼저 논의한다. 최종 확정 전까지는 파일 출력보다 채팅 내 초안 검토를 선호.
- **문서화 흐름**: EDA → 전처리 → 모델링 → 인사이트 내러티브 순서로 문서화해 분석 역량이 드러나게 구성.
- 주요 결정사항은 Markdown으로 정리해 관리.

### 이미 결정된 구조 — 재논의 금지
Claude가 다시 제안하더라도 아래 결정사항은 바꾸지 않는다.

| 항목 | 결정사항 |
|------|---------|
| API base URL | `frontend/src/lib/api.js` 단일 관리. 각 페이지에 직접 선언 금지 |
| 읍면동 목록 | 프론트엔드 하드코딩 금지 — `/api/analysis/dongs` API 호출 사용 |
| Pydantic 스키마 | `model_config = ConfigDict(from_attributes=True)` 사용. `class Config` 방식 금지 |
| DB UniqueConstraint | 3개 테이블 모두 `(행정동명, 통합카테고리, 기준_년분기_코드)` 복합 제약 적용됨 |
| CORS 오리진 | `CORS_ORIGINS` 환경변수로 관리. `main.py` 하드코딩 금지 |
| 배포 전략 | 단일 VPS + Nginx. DB를 외부 서비스(Supabase 등)로 이전 금지 |

### 데이터 보안 (공모전 규정 — 위반 시 실격)
- **행정데이터 원본을 외부 AI API에 절대 전송 금지** (Gemini, GPT, Claude API 포함)
- `data/raw/`, `data/processed/` → `.gitignore` 적용, 커밋 금지
- `*.pkl`, `*.csv`, `*.env` 파일 커밋 금지

### AI 파이프라인 주의사항
- 실행 순서 반드시 준수: `build_dataset.py` → `train_model.py` → `build_risk_index.py` → `import_to_db.py`
- **데이터 수령 후 가장 먼저**: `ai/build_dataset.py` Line 16 `CATEGORY_MAP = {}` 채울 것 (원본 업종 컬럼명 → 통합카테고리 매핑)
- **데이터 수령 후**: `build_dataset.py`/`build_risk_index.py`/`import_to_db.py`/`train_model.py`의 경로 인자 기본값을 `RAW_DATA_DIR`/`PROCESSED_DATA_DIR` 환경변수(`python-dotenv`)로 대체 — 팀원마다 원본 데이터 보관 위치가 다를 수 있으므로 하드코딩 대신 `.env`로 관리
- 학습된 모델은 `data/processed/lgbm_model.pkl`에 저장됨 (joblib, `{"model", "features", "auc"}` 키)
- `import_to_db.py`는 TRUNCATE 후 재삽입 방식 — 여러 번 실행해도 중복 없음

### 코딩 컨벤션
- 새 API 엔드포인트 추가 시 `backend/schemas.py`에 Pydantic 스키마 먼저 정의
- 주석은 WHY가 비자명할 때만. WHAT 설명 주석 금지
- 환경변수는 반드시 `.env`에 — 코드에 키/비밀값 하드코딩 금지

---

## 핵심 교훈 (프로젝트 원칙)

- **예측 문제 vs. 최적화 문제**: 정답지가 있는 예측 문제(이진분류)가 검증 가능성 측면에서 포트폴리오 목적에 압도적으로 유리.
- **스냅샷 vs. 시계열**: 단순 현황 스냅샷이 아닌 개·폐업 **시계열 이력**이 모델 정답값(레이블) 생성에 필수. 이 존재 여부 확인이 프로젝트 성패를 가름 — 데이터 수령 시 최우선 확인.
- **데이터 가용성이 스토리 설계보다 선행**: 내러티브 프레이밍은 데이터 신뢰성이 뒷받침될 때만 채택.
- **노다지 계승 방식**: 코드는 재사용하지 않고 방법론·도메인 지식·과거 실패 교훈만 계승.

---

## 확장 계획 (경진대회 이후)
- 기존 소상공인 대상 셀프 위험진단 (본인 동의 기반 개별 진단 — 별도 데이터·설계 필요)
- 창업 적합도 진단 고도화 (별도 모델)
- 상권현황 공개 대시보드
