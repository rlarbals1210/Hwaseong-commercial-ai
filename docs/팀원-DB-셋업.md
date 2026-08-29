# 팀원 DB 셋업 가이드

목적: 모든 팀원이 **동일한 DB 상태**에서 개발·시연할 수 있게 한다.
소요: 5~10분 (PostgreSQL이 이미 설치돼 있다는 전제)

---

## 왜 DB 덤프가 아니라 이 방식인가

`pg_dump`로 39MB 덤프를 공유할 수도 있지만 이 리포는 **산출물 CSV를 공유하고 파이프라인으로 재현**하는 방식을 택했다.

- 덤프는 바이너리라 diff가 안 되고 갱신할 때마다 리포가 부푼다
- 소스코드 심사에서 "파이프라인으로 재현된다"가 "덤프를 받았다"보다 낫다
- 커밋되는 파일이 전부 **읍면동×업종 집계 단위**라 개별 점포 정보가 리포에 들어가지 않는다

---

## 준비물 확인

```bash
psql --version          # PostgreSQL 설치 확인
python --version        # 가상환경 활성화 후 3.12.x
```

가상환경이 없다면 먼저 만든다. 이 프로젝트는 `uv`로 만든 `.venv`를 쓴다.

```bash
python3 -m venv .venv         # 또는 uv venv
source .venv/bin/activate
pip install -r requirements.txt
```

> `source .venv/bin/activate`를 **매번** 해야 한다. 안 하면 `zsh: command not found: python`이 뜨거나
> 시스템 파이썬이 잡혀서 `pandas`/`lightgbm`/`psycopg2` import 에러가 난다.
> 프롬프트 앞에 `(.venv)`가 보이는지 확인할 것.

---

## 1. 코드·데이터 받기

```bash
git pull
```

아래 6개 파일이 함께 받아진다(총 6.5MB). 이게 DB를 채우는 재료다.

```
data/processed/final_dataset.csv        3.1M   상권 집계(29개 동 × 74개 업종 × 21분기)
data/processed/cell_train_table.csv     3.1M   셀 학습 테이블
data/processed/scores.csv               132K   최신 분기 예측 점수
data/processed/lgbm_model_cell.pkl      324K   학습된 셀 모델
data/processed/model_cell_results.json    4K   모델 성능 지표
data/processed/risk_thresholds.json       4K   등급 기준선(평균 3.22% / 위험 6.44% / 표본 50)
```

---

## 2. `.env` 만들기

`.env`는 git에 올라가지 않으므로 **각자 직접 만든다.**

```bash
cat > .env <<'ENVEOF'
DATABASE_URL=postgresql://postgres:password@localhost:5432/hwaseong_db
RAW_DATA_DIR=data/raw
PROCESSED_DATA_DIR=data/processed
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
ENVEOF
```

`JWT_SECRET_KEY`는 각자 생성해서 채운다. **비어 있으면 서버가 즉시 실패한다**(의도된 동작).

```bash
openssl rand -hex 32
```

프론트 환경변수도 필요하다.

```bash
cp frontend/.env.example frontend/.env
# VITE_NAVER_MAP_CLIENT_ID 를 본인 NCP 키로 채울 것
```

---

## 3. DB 생성 + 스키마 적용

```bash
createdb hwaseong_db
alembic upgrade head
```

확인:

```bash
psql -d hwaseong_db -c "SELECT version_num FROM alembic_version;"
```

→ `20260818_0002` 가 나와야 정상.

```bash
psql -d hwaseong_db -c "\dt" | wc -l
```

→ 테이블 20개 (레거시 4 + 정규화 15 + alembic_version 1)

---

## 4. 데이터 적재

```bash
python ai/import_normalized_db.py
python ai/build_explanations.py
```

> `import_to_db.py`는 **레거시 전용이므로 쓰지 않는다.** 정규화 테이블은 `import_normalized_db.py`가 채운다.
> `build_dataset.py`·`train_model.py`도 **돌릴 필요 없다** — 외장 SSD 원본이 필요한데,
> 그 산출물을 CSV로 공유하고 있기 때문이다.

기대 출력:

```json
{ "areas": 29, "industries": 74, "commercial_quarters": 35513,
  "predictions": 1810, "ranked_predictions": 231, "latest_quarter": 20254 }

{ "m1_passed": true, "eligible_predictions": 231, "written": 693 }
```

---

## 5. 공무원 계정 만들기

계정은 DB 데이터라 git에 없다. **최초 1회 직접 생성한다.**

```bash
python -m backend.scripts.create_official admin demo1234 "테스트관리자"
```

---

## 6. 검증

```bash
psql -d hwaseong_db -c "
SELECT (SELECT count(*) FROM commercial_quarters)                        AS 상권셀,
       (SELECT count(*) FROM risk_predictions)                           AS 예측,
       (SELECT count(*) FROM risk_predictions WHERE predicted_rank IS NOT NULL) AS 순위보유,
       (SELECT count(*) FROM prediction_contributions)                   AS 기여도,
       (SELECT count(*) FROM area_quarter_summaries)                     AS 동요약,
       (SELECT sample_min FROM risk_threshold_sets ORDER BY id DESC LIMIT 1) AS 표본기준;"
```

**기준값 — 이 숫자가 나와야 팀원 간 상태가 동일하다.**

| 항목 | 값 |
|---|---|
| 상권셀 | 35,513 |
| 예측 | 1,810 |
| 순위보유 | **382** |
| 기여도 | **1,146** |
| 동요약 | 29 |
| 표본기준 | **30** |

유령 행이 없는지도 확인한다(0이어야 정상).

```bash
psql -d hwaseong_db -c "
SELECT count(*) AS 유령행 FROM prediction_contributions pc
JOIN risk_predictions rp ON rp.id = pc.prediction_id
WHERE rp.predicted_rank IS NULL;"
```

---

## 7. 서버 실행

```bash
uvicorn backend.main:app --reload --port 8000     # 터미널 1
cd frontend && npm install && npm run dev          # 터미널 2
```

→ http://localhost:5174

화면 확인 포인트:

- 조기경보 대시보드의 전체 분석 대상이 **382개**
- 업종 필터가 **46개**, 안내 문구가 "점포 수 30개 이상"
- 사이드바에 **현장점검 우선순위** (구 "정책자금 우선순위")

---

## 자주 겪는 문제

| 증상 | 원인 · 해결 |
|---|---|
| `command not found: python` | 가상환경 미활성화 → `source .venv/bin/activate` |
| `JWT_SECRET_KEY 환경변수가 설정되지 않았습니다` | `.env`의 `JWT_SECRET_KEY`가 빔 → `openssl rand -hex 32`로 생성 |
| 로그인은 되는데 API가 401 | 보안 수정 이전 토큰이 남음 → **로그아웃 후 재로그인** |
| `ranked_predictions`가 231 | DB가 옛 기준(`sample_min: 50`) → `git pull` 후 `python ai/import_normalized_db.py` 재실행 |
| 지도가 "인증 실패" | `frontend/.env`의 NCP 키 없음/미등록 → README의 네이버 지도 절 참고 |
| 테이블이 안 생김 | `alembic upgrade head` 누락, 또는 `.env`의 DB 이름 확인 |
| 엉뚱한 DB에 테이블 생성 | `.env`가 `hwaseong_db`를 가리키는지 확인. 같은 서버의 `commercial_db`는 **구 서울 프로젝트**다 |

---

## 데이터 취급 주의

- **원본(`data/raw/`)과 개별 점포 파일(`store_*.csv`)은 절대 커밋하지 않는다.**
  `store_train_table.csv`(193M)·`store_panel.csv`(145M)·`store_labels.csv`(135M)에는
  상가업소번호·지번주소·좌표가 들어 있고, 이 리포는 **공개 저장소**다.
- 리포에 포함된 6개 파일은 전부 읍면동×업종 집계 단위라 개별 점포를 식별할 수 없다.
- 행정데이터 원본을 외부 AI API로 전송하지 않는다(공모전 규정, 위반 시 실격).
- **대회 종료 후 3개월 이내에 제공 데이터를 폐기하고 폐기확인서를 제출해야 한다**(시상금 지급 조건).
  이 리포의 `data/processed/*` 포함 대상이며, **폐기는 수동으로 진행한다.**
