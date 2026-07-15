# 화성시 소상공인 AI 정책지원 플랫폼 (리버스 노다지)

화성시 소상공인 폐업 위험을 AI로 조기경보하고 정책자금 배분 우선순위를 제시하는 웹앱.

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

## 자세한 개발 가이드

프로젝트 구조, API 명세, ML 파이프라인, 협업 규칙 등은 [CLAUDE.md](CLAUDE.md) 참고.
