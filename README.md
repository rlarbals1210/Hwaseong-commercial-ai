# 화성시 소상공인 AI 정책지원 플랫폼

화성시 소상공인 폐업 위험을 AI로 조기경보하고 현장점검 우선순위를 제시하는 웹앱.

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
