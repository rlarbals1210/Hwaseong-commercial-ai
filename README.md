# 화성시 소상공인 AI 정책지원 플랫폼

화성시 소상공인 폐업 위험을 AI로 조기경보하고 현장점검 우선순위를 제시하는 웹앱.

## 창업 탐색 도구

공개 **상권 둘러보기(`/browse`)**에서 사용할 수 있습니다.

- **지역부터 찾기**: 읍면동을 고르면 기존 공통 적합도 점수로 비교한 업종 5개를 보여줍니다. 업종 사이의 절대 성공률이 아니므로 업종 탐색 목록에는 등급을 표시하지 않습니다.
- **지역·업종 선택**: 원하는 읍면동과 업종을 함께 정한 뒤 해당 조합의 상세를 바로 엽니다. 업종을 바꿔도 선택 지역이 유지됩니다.
- **추천 카드 → 지도·상세**: 카드 전체를 클릭하거나 키보드 Enter/Space로 선택하면 해당 지역 경계에 맞춰 지도가 확대되고 상세가 열립니다. 작은 화면에서는 지도와 상세를 위아래로 배치합니다.
- **지역 비교**: 별도 화면에서 같은 업종의 두 지역을 선택해 조건 적합도와 관측 지표를 나란히 비교합니다. 추천 카드에 비교 담기 버튼을 두지 않습니다.
- **선택 상권 → 입지·인근 상권**: 공개 GeoJSON에서 경계선을 공유하는 인접 지역 중 같은 업종의 표본이 충분한 후보를 최대 3곳 제시합니다. 시 전체에서 계산한 점수·순위를 그대로 사용하며, 후보 카드 선택 시 지도·상세로 이동합니다. 중심점 거리·이동시간 순위가 아닙니다.
- **선택 상권 → 방문·검색 패턴**: 업종과 무관한 읍면동 전체의 요일별 유동 패턴과 업종 대표 검색어의 전국 검색 관심도를 구분해 표시합니다.
- **선택 상권 → 창업비용**: 매장·초기비용 → 월 운영비 → 매출·결과의 3단계로 입력하며 초기 자금·월 고정비를 함께 확인합니다. 만원 단위 견적, 면적 빠른 입력·단위 자동 환산, 변동비율 슬라이더로 손익분기 매출과 가정 매출의 월 영업수지를 계산합니다. 입력은 지역·업종별로 페이지 새로고침 전까지 보존됩니다. 작은 화면에서는 비용 패널을 넓게 펼칩니다. 보증금과 예비자금은 초기 지출과 구분하며 임대료·매출 자동 추정이나 투자금 회수기간 예측은 하지 않습니다.

### 요일별 유동인구 적재

```bash
pip install -r requirements.txt
alembic upgrade head
python -m ai.import_weekday_flow --dry-run
python -m ai.import_weekday_flow
```

`eda/paths.py`가 지정하는 로컬 유동인구 CSV와 읍면동 코드 파일을 사용합니다. 최신 완결 월에 대해 현재 읍면동 1:1 매핑, 중복·결측·비양수, 7요일 완비 여부와 **요일 값 × 월별 해당 요일 수 ≈ 월 합계(오차 1% 이내)**를 모두 검증한 뒤 한 트랜잭션으로 upsert합니다. 원본 비율 컬럼을 요일 비중으로 사용하지 않습니다. DB에는 월~일 일평균의 평균을 100으로 둔 상대지수만 저장하며 기존 ML 파이프라인·학습 결과는 바꾸지 않습니다.

현재 검증한 보유 최신월은 **2025-06**, 29개 읍면동 × 7요일 = 203개 지수입니다. 화면에 기준월을 표시하며 측정 기준 변경이 있는 연도 간 절대 유동인구 증감 비교에는 쓰지 않습니다. 최신월 자료가 불완전하면 과거 월로 조용히 대체하지 않습니다.

### 검색 트렌드 키 연결 (선택)

키가 없어도 다른 기능은 동작하며 검색 화면에 **API 키 연결 대기**가 표시됩니다. 나중에 [네이버 개발자센터](https://developers.naver.com/apps/#/register)에서 **데이터랩(검색어트렌드)** 사용이 설정된 애플리케이션을 등록한 뒤, 루트 `.env`에 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 입력하고 백엔드를 재시작하세요. NCP 지도 키와 다르며 `VITE_` 변수에 넣지 않습니다.

`backend/services/search_interest.py`의 명시적 대표 검색어 매핑을 사용합니다(현재 20개 중분류 지원, 미지원 업종은 별도 안내). 원본 행정데이터나 지역 정보는 외부로 보내지 않고 일반 검색어와 기간만 전송합니다. 최근 완료된 12개 달을 조회하며 기간 내 최대값 100인 전국 상대지수로, 검색 건수·화성시 수요를 의미하지 않습니다. [네이버 검색 API 명세](https://developers.naver.com/docs/serviceapi/datalab/search/search.md)를 따릅니다.

외부 호출은 프로세스 메모리에 최대 128개, 정상 응답 24시간 캐시합니다. 실패 시 5분간 재호출을 억제하고 기존 같은 기간 자료가 있으면 이전 수집 시각과 함께 표시합니다. 서버 재시작 시 캐시가 비워지고 다중 worker 간에는 공유되지 않습니다. 자동 주기 수집은 하지 않습니다. 외부 인증 실패는 앱 로그인 실패(401/403)로 전달하지 않습니다.

검증 명령:

```bash
python -m pytest backend/tests/test_exploration.py backend/tests/test_recommend.py -q
node --test frontend/tests/startupCosts.test.mjs
```

## 기술 스택

- 프론트엔드: React 19 + Vite (포트 5174)
- 백엔드: FastAPI + Uvicorn (포트 8000)
- DB: PostgreSQL + SQLAlchemy
- 지도: Naver Maps JS API v3 (NCP 다이나믹 맵)

## 실행 방법

### 백엔드
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### 프론트엔드
```bash
cd frontend
npm install
npm run dev
```
→ http://localhost:5174

## 환경변수 설정

`.env`는 git에 올라가지 않으므로 팀원마다 로컬에 직접 채워야 한다.

**루트 `.env`**
```
DATABASE_URL=postgresql://postgres:password@localhost:5432/hwaseong_db
RAW_DATA_DIR=data/raw
PROCESSED_DATA_DIR=data/processed
```

**`frontend/.env`** (템플릿: `frontend/.env.example` 복사해서 사용)
```
VITE_NAVER_MAP_CLIENT_ID=
VITE_API_BASE=http://localhost:8000
```

**루트 `.env`에 추가 (인증용)**
```
JWT_SECRET_KEY=       ← openssl rand -hex 32 로 각자 생성. 절대 커밋 금지
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
```

공공데이터 API 키를 이용한 수집은 루트 [`.env.example`](.env.example)과
[자동수집 운영 문서](docs/public-data-automation.md)를 따른다. 수집 결과는 기존 모델 입력을
덮어쓰지 않고 `data/raw/api_staging/`에 버전별로 저장된다.

공무원은 로그인 후 사이드바 하단의 **데이터 관리**에서 카드매출 CSV와 카드 업종
코드표 XLSX를 업로드할 수 있다. 업로드된 파일은 `data/raw/manual_uploads/`에 버전별로
보관되며, 형식 검증을 통과해도 모델·DB에는 자동 반영되지 않는다.

## 로그인 계정 — 팀원 필독

**이 서비스는 공무원 전용이다.** 2026-08-18 설계 결정으로 시민(소상공인) 직접조회 기능과 시민 로그인을 제거했다 — 사유는 [CLAUDE.md](CLAUDE.md)의 '설계 결정' 절 참조. 앱에 접속하면 역할 선택 없이 바로 공무원 로그인 화면이 뜬다.

### 공무원 로그인
- 아이디+비밀번호 방식. **계정은 각 팀원의 로컬 PostgreSQL DB에 저장되는 데이터라 git에 올라가지 않는다** — pull만 받으면 테이블(`officials`)은 생기지만 계정 데이터는 비어있음.
- 최초 1회 아래 명령으로 직접 계정을 만들어야 함:
  ```bash
  python -m backend.scripts.create_official <아이디> <비밀번호> [표시이름]
  # 예: python -m backend.scripts.create_official admin demo1234 "테스트관리자"
  ```
- 배포 서버에도 별도로 최소 1개 계정을 시딩해야 함 (배포 체크리스트에 포함시킬 것).

### 제거된 시민 로그인에 대해
- `backend/utils/business_number.py`(사업자등록번호 체크섬 검증)와 그 테스트는 **삭제하지 않고 보존**한다. "시민 인증 수단을 검토했고 주민등록번호가 아닌 방식까지 구현한 뒤 의도적으로 제외했다"는 판단 근거를 결과보고서에서 인용하기 위함이다.
- 주민등록번호는 배포 URL이 공개되는 특성상 법적 리스크가 있어 어떤 경우에도 사용하지 않는다.

## 네이버 지도 API 키 — 팀원 필독

### 키 보관 위치
- 실제 키 값은 `frontend/.env`의 `VITE_NAVER_MAP_CLIENT_ID`에만 존재한다.
- `frontend/.env`는 `.gitignore`에 등록되어 있어 **git에 절대 올라가지 않는다** — 각자 로컬에 직접 채워야 함.
- 값 없는 템플릿은 `frontend/.env.example`에 있으니 복사(`cp frontend/.env.example frontend/.env`)해서 본인 키를 채울 것.
- 팀 공용 키가 필요하면 Slack/노션 등 코드 저장소 밖 채널로 공유 — **절대 커밋 금지**.

### 키 발급 방법
1. https://www.ncloud.com 가입 → 콘솔 로그인
2. **AI·NAVER API > Application** 등록 → 사용 API에서 **Maps** 선택
3. **Web 서비스 URL**에 개발 서버 주소(`http://localhost:5174`)를 반드시 등록 — 안 하면 지도 인증 실패
4. 발급된 Client ID를 `frontend/.env`에 채우고 `npm run dev` 재시작 (Vite는 `.env` 변경 시 재시작해야 반영됨)

### 흔한 실수 (실제로 겪은 문제)
- **`ncpClientId` vs `ncpKeyId` 파라미터 혼동**: 2024년 NCP Maps API 개편 이후 신규 발급 키는 도메인·파라미터명이 다르다.
  - 구 키: `openapi.map.naver.com/openapi/v3/maps.js?ncpClientId=...`
  - **신규 키(대부분 이 경우)**: `oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=...`
  - 현재 `frontend/src/pages/MapPage.jsx`는 신규 방식(`ncpKeyId`)으로 구현되어 있음. "네이버 지도 Open API 인증이 실패했습니다" 에러가 뜨면 이 조합부터 확인할 것.
- Web 서비스 URL 미등록 → 인증 실패. 로컬 개발용 `http://localhost:5174`와 배포 도메인 둘 다 등록 필요.
- `.env` 수정 후 브라우저 새로고침만으로는 반영 안 될 수 있음 → `npm run dev` 재시작 권장.

## 팀원 DB 셋업

팀원 모두 동일한 DB 상태로 맞추려면 [docs/팀원-DB-셋업.md](docs/팀원-DB-셋업.md)를 따른다.
요약하면 이렇다.

```bash
git pull
source .venv/bin/activate
createdb hwaseong_db
alembic upgrade head
python ai/import_normalized_db.py      # import_to_db.py 아님(레거시)
python ai/build_explanations.py
python -m backend.scripts.create_official admin demo1234 "테스트관리자"
```

`build_dataset.py`·`train_model.py`는 외장 SSD 원본이 필요하므로 **돌리지 않는다.**
그 산출물 6개(6.5MB)를 리포에 포함해 두었다.

---

## 데이터 정책

### 리포에 포함하는 것 (읍면동 × 업종 집계 단위, 총 6.5MB)

```
data/processed/final_dataset.csv        상권 집계
data/processed/cell_train_table.csv     셀 학습 테이블
data/processed/scores.csv               최신 분기 예측 점수
data/processed/lgbm_model_cell.pkl      학습된 셀 모델
data/processed/model_cell_results.json  모델 성능 지표
data/processed/risk_thresholds.json     등급 기준선
data/processed/industry_hierarchy.csv   업종 계층(대분류 10 × 중분류 74)
```

전부 **집계 단위라 개별 점포를 식별할 수 없다.** 이 저장소는 공개이므로 이 기준을 벗어나는 파일은 넣지 않는다.

### 절대 커밋하지 않는 것

```
data/raw/                      원본 zip(소진공 상가정보·인허가)
data/processed/store_*.csv     개별 점포 단위 — 상가업소번호·지번주소·좌표 포함
                               store_train_table.csv(193M) / store_panel.csv(145M) / store_labels.csv(135M)
.env                           DB 접속정보·JWT 비밀키
```

`.gitignore`가 `data/processed/*`를 차단하고 위 6개만 `!` 예외로 허용한다.
**개별 점포 파일을 예외 목록에 추가하지 말 것.**

### 대회 규정 (공모전 유의사항 Ⅴ-5)

- 제공받은 데이터는 본 대회 목적 외 사용 금지
- 행정데이터 원본을 외부 AI API에 전송 금지 (위반 시 실격)
- **대회 종료 후 3개월 이내 제공 데이터 완전 폐기 + 폐기확인서 제출** — 시상금 지급 조건
  - 이 저장소의 `data/processed/*`도 폐기 대상이다
  - **폐기는 수동으로 진행한다.** 자동 삭제 스크립트를 두지 않는다

---

## 자세한 개발 가이드

프로젝트 구조, API 명세, ML 파이프라인, 협업 규칙 등은 [CLAUDE.md](CLAUDE.md) 참고.
