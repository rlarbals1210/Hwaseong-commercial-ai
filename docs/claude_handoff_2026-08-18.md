# 화성시 소상공인 AI 정책지원 플랫폼 Claude 작업 인계서

- 작성일: 2026-08-18
- 프로젝트: 화성시 소상공인 AI 정책지원 플랫폼
- 프로젝트 경로: `/Users/gimgyumin/Developer/화성시-AI공모전/hwaseong-commercial-ai`
- 현재 Alembic revision: `20260818_0002 (head)`

> 현재 변경 사항은 아직 Git 커밋하지 않았다. 기존 변경을 되돌리거나 덮어쓰지 말고 작업 전
> `git status`와 `git diff`를 먼저 확인한다.

---

## 1. 현재 서비스 방향

서비스 대상을 소상공인과 공무원 양쪽에서 **공무원 전용 정책 의사결정 지원 시스템**으로 축소했다.

```text
AI 조기경보
→ 공무원 위험 셀 확인
→ 데이터 근거·AI 기여 요인 확인
→ 현장 확인 및 접촉 이력 기록
→ 특례보증·경영환경개선·상권 활성화·신규 정책 검토
→ 정책 실행 및 성과 기록
```

시민 페이지와 시민 로그인은 제거된 상태다. 공무원 계정은 `officials` 테이블과 JWT 인증을 사용한다.

---

## 2. 정규화 DB 전환

기존 레거시 테이블은 롤백 목적으로 유지한다.

```text
commercial_data
score_data
risk_index
officials
```

신규 API는 다음 정규화 테이블을 사용한다.

### 기준정보·관측 데이터

- `admin_areas`
- `industry_categories`
- `data_batches`
- `commercial_quarters`

### AI 모델

- `model_runs`
- `risk_predictions`
- `prediction_contributions`

### 위험 기준·지도 집계

- `risk_threshold_sets`
- `area_quarter_summaries`

### 공무원 업무 흐름

- `alert_cases`
- `alert_evidences`
- `alert_contacts`
- `policy_programs`
- `policy_actions`
- `policy_outcomes`

기존 레거시 테이블은 삭제하지 않았다. 신규 라우터는 정규화 테이블만 조회한다.

주요 모델: `backend/models.py`

---

## 3. Alembic 마이그레이션

마이그레이션 구성:

```text
20260818_0000_legacy_baseline.py
20260818_0001_normalized_policy_schema.py
20260818_0002_alert_contacts_and_explainability.py
```

현재 실제 PostgreSQL 상태:

```text
20260818_0002 (head)
```

`0002`에서 추가한 내용:

- `risk_threshold_sets`
- `prediction_contributions`
- `alert_contacts`
- `area_quarter_summaries`
- `commercial_quarters.risk_grade`
- `commercial_quarters.sample_insufficient`
- `commercial_quarters.threshold_set_id`
- `alert_evidences.evidence_type` CHECK 제약
- 활성 `model_runs` 1개만 허용하는 PostgreSQL 부분 유니크 인덱스

마이그레이션 파일:

```text
backend/migrations/versions/20260818_0002_alert_contacts_and_explainability.py
```

다음 왕복 검증까지 완료했다.

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
alembic check
```

결과:

```text
No new upgrade operations detected.
```

---

## 4. ML 파이프라인 실행 결과

실제 외장 SSD 원본부터 전체 파이프라인을 다시 실행했다.

원본 경로:

```text
/Volumes/SSD/hwaseong-commercial/hwaseong-commercial-dataset
```

실행 순서:

```bash
python ai/build_dataset.py
python ai/train_model.py
python ai/build_risk_index.py
python ai/import_normalized_db.py
python ai/build_explanations.py --validate-only
python ai/build_explanations.py
```

정규화 DB 기준으로는 `import_to_db.py`가 아니라 `import_normalized_db.py`를 사용해야 한다.

산출 결과:

```text
원본 분기 ZIP                   21개
원본 상가 행                   817,741행
store_panel.csv               873,035행
final_dataset.csv              35,505행
cell_train_table.csv           37,456행
최신 분기 예측                   1,810개
표본 충분·예측 순위 보유 셀          382개
```

모델 성능:

```text
셀 모델 스피어만 상관계수       0.4193
상위 10% 위험군 리프트          1.444배
점포 모델 ROC-AUC              0.5550
점포 모델 PR-AUC               0.1389
```

정규화 DB 실제 적재 결과:

```text
admin_areas                     29
industry_categories             74
commercial_quarters         35,513
risk_predictions             1,810
예측순위 보유 셀                382
risk_threshold_sets              1
area_quarter_summaries           29
prediction_contributions      1,146
policy_programs                   4
```

`commercial_quarters`가 `final_dataset.csv`보다 8행 많은 이유는 최신 분기에 처음 등장해서 과거
폐업률을 계산할 수 없는 예측 셀을 점포 수 팩트로 보존했기 때문이다. 해당 셀은 표본부족으로 처리된다.

---

## 5. 정규화 임포터 변경

파일: `ai/import_normalized_db.py`

기존 TRUNCATE 방식이 아니라 복합키 upsert 방식이다.

주요 동작:

- 행정동·업종 마스터 upsert
- 데이터 배치 이력 저장
- `commercial_quarters` upsert
- 최신 예측 셀 8개 보완
- 위험 기준선 DB 저장
- 최신 셀 위험등급 저장
- 표본부족 여부 저장
- 동별 지도 요약 29행 생성
- 모델 실행 이력 저장
- 활성 모델 1개 유지
- 예측 결과 1,810행 upsert
- 정책 프로그램 4종 seed
- 업무 테이블은 삭제하거나 초기화하지 않음

임포터는 다음 파일을 요구한다.

```text
final_dataset.csv
scores.csv
cell_train_table.csv
model_cell_results.json
lgbm_model_cell.pkl
risk_thresholds.json
```

`risk_thresholds.json`의 분기가 최신 상권 분기와 다르면 적재를 중단한다.

---

## 6. 위험 기준선과 셀 등급

기존에는 `backend/services/risk.py`가 로컬 JSON 파일을 읽거나 기본값으로 폴백했다. 이제 실제 조회에
필요한 기준은 DB에 보존한다.

현재 기준:

```text
기준 분기                    2025Q4 / 20254
화성시 평균 폐업률             3.22%
위험 기준                     6.44%
동별 위험업종비율 평균          11.62%
동별 위험 기준                23.24%
표본 최소 점포 수                 30
```

`commercial_quarters`의 최신 행에는 다음이 저장된다.

```text
risk_grade
sample_insufficient
threshold_set_id
```

등급은 `안정`, `주의`, `위험`, `표본부족`이다.

신규 API는 가능한 경우 `services/risk.py`의 JSON 기준이 아니라 DB에 저장된 `risk_grade`와 요약
테이블을 사용한다.

`backend/services/risk.py`는 현재 `action_message()` 때문에 남아 있다. 기존 JSON 기반
`risk_level()`과 `dong_risk_level()`은 신규 라우터에서 사용하지 않으므로 추후 정리 가능하다.

---

## 7. 지도 집계 정상화

기존 지도 API는 매 요청마다 최신 `commercial_quarters`를 그룹 집계했다.

현재는 `area_quarter_summaries`에 동×분기 단위로 저장한 29행을 직접 조회한다.

저장 항목:

```text
total_cells
sample_sufficient_cells
risk_cells
risk_industry_ratio_pct
area_risk_grade
avg_trend_slope
threshold_set_id
batch_id
```

실제 원본 셀 재집계와 저장된 위험업종비율의 최대 오차는 `0.0`이다.

지도 API 응답에 다음 필드를 추가했다.

```text
total_cells
sample_sufficient_cells
coverage_pct
```

프론트 지도 상세 화면에도 다음을 표시한다.

```text
분석 가능 업종 n/전체 업종
표본 충족률 %
점포 수 30개 이상 기준
```

관련 파일:

```text
backend/routers/alerts.py
frontend/src/pages/MapPage.jsx
```

---

## 8. 업종 필터 문제 수정

원래 업종 필터는 전체 기간에 한 번이라도 등장한 74개 업종을 전부 표시했다.

하지만 조기경보와 정책 분석은 최신 분기 점포 수 30개 이상인 셀만 사용하므로 일부 업종을 선택하면
빈 화면이 나왔다.

현재 API:

```http
GET /api/analysis/categories
GET /api/analysis/categories?purpose=alert
GET /api/analysis/categories?purpose=policy
```

현재 결과:

```text
전체 업종                    74개
조기경보 분석 가능 업종        46개
정책 분석 가능 업종           46개
```

프론트 적용:

- 조기경보는 `purpose=alert`
- 정책 페이지는 `purpose=policy`
- 필터 아래에 분석 기준과 업종 수 표시
- 정상 빈 결과, 전체 데이터 없음, API 오류 메시지를 구분
- `일반 숙박`은 동탄1동·서신면·우정읍 3건 정상 확인

관련 파일:

```text
backend/routers/analysis.py
frontend/src/pages/DashboardPage.jsx
frontend/src/pages/PolicyPage.jsx
```

---

## 9. API 오류 처리 개선

기존 `apiFetch()`는 HTTP 401·404·500도 JSON으로 파싱해서 정상 데이터처럼 처리할 수 있었다.

`frontend/src/lib/api.js`에 `apiFetchJson()`을 추가했다.

동작:

- `response.ok`가 아니면 예외 발생
- 정상 JSON만 반환
- 빈 배열과 서버 오류를 구분

Dashboard와 Policy 페이지는 다음 상태를 구분한다.

```text
로딩 중
정상 데이터
선택 업종 표본 부족
전체 데이터 없음
API 호출 실패
업종 목록 호출 실패
```

---

## 10. JWT 보안 문제 수정

문제 원인:

`backend/auth/security.py`가 `.env`를 로드하는 `database.py`보다 먼저 import될 수 있었다. 그 결과
실행 중인 서버가 빈 문자열을 JWT 비밀키로 사용하고 있었다.

수정 내용:

- `security.py`가 프로젝트 루트 `.env`를 직접 먼저 로드
- `JWT_SECRET_KEY`가 비어 있으면 서버가 즉시 실패
- 빈 비밀키로 서명한 토큰 거부 확인

현재 검증:

```text
정상 .env 비밀키 토큰          성공
빈 비밀키 토큰                401 Unauthorized
```

이 수정 전에 발급된 브라우저 JWT는 무효이므로 사용자는 한 번 로그아웃 후 다시 로그인해야 한다.

---

## 11. React AuthContext 분리

ESLint Fast Refresh 규칙을 만족시키기 위해 Context와 Hook을 Provider 컴포넌트 파일에서 분리했다.

```text
frontend/src/context/AuthContext.jsx
    → AuthProvider만 export

frontend/src/context/auth-context.js
    → AuthContext, useAuth export
```

다음 파일의 import 경로를 변경했다.

```text
App.jsx
OfficialLoginPage.jsx
RequireRole.jsx
```

기능 변경은 없고 린트 경고 제거 목적이다.

---

## 12. AI 예측 기여 요인

신규 파일: `ai/build_explanations.py`

LightGBM 자체 `pred_contrib=True`를 사용해서 외부 AI API 없이 로컬 계산한다.

기여 요인은 다음 3개로 묶었다.

```text
area_industry_pattern
  - 행정동명
  - 상권업종중분류명
  - 임대료_매핑그룹

avg_business_age
  - 평균업력_분기수

store_scale
  - 점포수
```

범주형 3개를 하나로 합친 이유는 임대료 그룹이 행정동명에서 파생된 중첩 변수라 LightGBM이 기여도를
임의 분배할 수 있기 때문이다.

M1 검증 기준:

```text
전체 절대 기여도에서 단일 요인 비중이 90%를 초과하면 실패
```

실제 결과:

```text
지역·업종 과거 패턴       68.1363%
평균 업력                11.1970%
점포 규모                20.6667%
M1 통과                  true
```

적재 결과:

```text
분석 가능 예측               382개
예측당 요인                    3개
prediction_contributions   1,146행
예측별 share_pct 합계         100%
```

원 기여도는 `contribution_value_internal`에 저장하지만 API에는 절대 노출하지 않는다.

API:

```http
GET /api/alerts/{prediction_id}/contributions
```

응답 항목:

```text
rank
factor_code
factor_label
direction
share_pct
```

고정 안내 문구:

```text
AI 예측의 상대적 기여 요인이며 인과관계를 의미하지 않습니다.
```

고정 문구는 `backend/services/explain.py`에 있다.

현재 기여도 API는 구현됐지만 프론트 대시보드 카드에는 아직 연결하지 않았다.

---

## 13. 예측 절대값 노출 제거

기존 조기경보와 `/api/analysis/score`는 내부 예측 폐업률의 반대값을 `growth_prob`로 변환해서
노출하고 있었다. 이를 제거했다.

현재 원칙:

```text
실제 폐업률     → 절대값 표시 가능
AI 예측         → 상대 순위만 표시
AI 기여 요인    → 상대 share_pct만 표시
내부 예측값     → API 노출 금지
내부 원 기여도  → API 노출 금지
```

OpenAPI 검사 결과:

```text
predicted_closure_rate_internal 노출       0건
contribution_value_internal 노출           0건
```

Dashboard CSV에서도 AI 성장확률 열을 제거했다.

주의: 정책 페이지의 `growth_prob` 필드는 AI 성장확률이 아니라 점포 수를 담는 기존 필드명이다.
의미가 혼동되므로 나중에 `benefit_scale` 또는 `store_count`로 이름을 바꾸는 리팩터링을 권장한다.

---

## 14. 접촉 이력 CRUD

신규 테이블: `alert_contacts`

저장 항목:

```text
alert_id
official_id
contacted_on
channel
outcome
target_scope
contacted_store_count
store_refs
note
created_at
updated_at
```

채널:

```text
visit
phone
sms
email
meeting
other
```

결과:

```text
connected
no_answer
declined
applied
pending
```

API:

```http
GET    /api/workflow/alerts/{alert_id}/contacts
POST   /api/workflow/alerts/{alert_id}/contacts
PATCH  /api/workflow/contacts/{contact_id}
DELETE /api/workflow/contacts/{contact_id}
```

`store_refs`는 아직 요청 스키마에 포함하지 않았다. 프로젝트의 개별 점포 참조 원칙이 승인되기
전까지 항상 `NULL`로 유지한다.

실제 API에서 등록·목록 조회·수정·삭제를 검증했고 테스트용 AlertCase와 Evidence를 모두 정리했다.

현재 실제 업무 데이터:

```text
alert_cases       0
alert_contacts    0
```

관련 파일:

```text
backend/routers/workflow.py
backend/schemas.py
```

접촉 이력 UI는 아직 구현하지 않았고 API와 DB만 준비된 상태다.

---

## 15. 근거 유형 A/B/C 분리

`alert_evidences.evidence_type` 자유 문자열을 다음 세 값으로 제한했다.

```text
confirmed_signal
model_contribution
field_check
```

마이그레이션에서 기존 대문자 코드가 존재하면 변환한다.

```text
OBSERVED_SIGNAL        → confirmed_signal
MODEL_CONTRIBUTION     → model_contribution
CONTEXT_INDICATOR      → model_contribution
OFFICIAL_CONFIRMATION  → field_check
```

DB CHECK 제약이 실제로 존재하는 것까지 확인했다.

초기 경보 생성 시 자동 근거:

- 실제 폐업률
- 실제 개업률
- 폐업률 추세
- AI 상대 위험 순위

평균 폐업률 baseline은 이제 로컬 JSON 상수가 아니라 해당 셀의 `threshold_set_id`를 통해 DB에서
조회한다.

---

## 16. 활성 모델 단일 제약

PostgreSQL 부분 유니크 인덱스:

```sql
CREATE UNIQUE INDEX uq_model_runs_single_active
ON model_runs (is_active)
WHERE is_active;
```

현재 활성 `model_run` 수는 1개다.

임포터도 기존 활성 모델을 먼저 비활성화하고 새 실행을 활성화한다. 애플리케이션 방어와 DB 제약을
모두 적용했다.

---

## 17. 현재 API 핵심 상태

```http
GET /api/analysis/dongs
GET /api/analysis/categories
GET /api/analysis/categories?purpose=alert
GET /api/analysis/categories?purpose=policy
GET /api/analysis/dong
GET /api/analysis/score
GET /api/analysis/quarters

GET /api/alerts/closure-risk
GET /api/alerts/closure-rate-ranking
GET /api/alerts/vacancy-risk/map
GET /api/alerts/{prediction_id}/contributions

GET /api/policy/fund-priority

POST   /api/workflow/alerts/{prediction_id}
GET    /api/workflow/alerts
PATCH  /api/workflow/alerts/{alert_id}
GET    /api/workflow/alerts/{alert_id}/evidence
POST   /api/workflow/alerts/{alert_id}/evidence
GET    /api/workflow/alerts/{alert_id}/contacts
POST   /api/workflow/alerts/{alert_id}/contacts
PATCH  /api/workflow/contacts/{contact_id}
DELETE /api/workflow/contacts/{contact_id}
GET    /api/workflow/programs
POST   /api/workflow/actions
POST   /api/workflow/actions/{action_id}/outcomes
```

---

## 18. 검증 결과

최종 검증:

```text
pytest                         11 passed
frontend npm run lint          통과
frontend npm run build         통과
alembic current                20260818_0002 (head)
alembic check                  차이 없음
OpenAPI internal 필드 노출      0건
지도 집계 오차                  0.0
예측별 기여도 합계              100%
접촉 이력 CRUD                  통과
반복 임포트                     중복 없이 동일 결과
```

추가 테스트 파일:

```text
backend/tests/test_category_filters.py
backend/tests/test_explanations.py
backend/tests/test_security.py
backend/tests/test_normalized_import.py
```

문서:

```text
docs/database_migration.md
AGENTS.md
```

---

## 19. 현재 Git 작업 트리

수정 파일:

```text
AGENTS.md
ai/import_normalized_db.py
backend/auth/security.py
backend/models.py
backend/routers/alerts.py
backend/routers/analysis.py
backend/routers/policy.py
backend/routers/workflow.py
backend/schemas.py
backend/tests/test_normalized_import.py
docs/database_migration.md
frontend/src/App.jsx
frontend/src/components/RequireRole.jsx
frontend/src/context/AuthContext.jsx
frontend/src/lib/api.js
frontend/src/pages/DashboardPage.jsx
frontend/src/pages/MapPage.jsx
frontend/src/pages/OfficialLoginPage.jsx
frontend/src/pages/PolicyPage.jsx
```

신규 미추적 파일:

```text
ai/build_explanations.py
backend/migrations/versions/20260818_0002_alert_contacts_and_explainability.py
backend/services/explain.py
backend/tests/test_category_filters.py
backend/tests/test_explanations.py
backend/tests/test_security.py
frontend/src/context/auth-context.js
docs/claude_handoff_2026-08-18.md
```

커밋하기 전에 반드시 신규 파일까지 포함해야 한다.

---

## 20. Claude가 이어서 할 때 주의할 점

1. `alembic stamp`를 다시 실행하지 말 것. 현재 DB는 이미 `20260818_0002`까지 적용됐다.
2. 정규화 DB 적재에는 `import_normalized_db.py`를 사용할 것. `import_to_db.py`는 레거시 테이블용이다.
3. 레거시 테이블을 삭제하지 말 것. 현재는 롤백 목적으로 유지한다.
4. `data/raw`, `data/processed`, 모델 PKL, CSV, `.env`를 커밋하지 말 것.
5. 행정데이터나 원본 데이터를 외부 AI API로 전송하지 말 것.
6. `predicted_closure_rate_internal`과 `contribution_value_internal`을 API에 노출하지 말 것.
7. AI 예측은 절대확률이 아니라 상대 위험 순위로만 표현할 것.
8. `store_refs`는 별도 승인 전까지 입력받거나 저장하지 말 것.
9. 기여도 스크립트는 M1 실패 시 테이블을 비우는 것이 정상 동작이다.
10. 새 API를 수정할 경우 Pydantic 스키마를 먼저 변경할 것.
11. 기존 브라우저 JWT는 보안 수정으로 무효화됐으므로 재로그인이 필요하다.
12. 현재 접촉 이력과 기여 요인 API는 있지만 프론트 UI는 아직 없다.
13. 정책 API의 `growth_prob`는 실제로 점포 수이므로 추후 명칭 정리가 필요하다.
14. `backend/services/risk.py`의 JSON 기반 등급 함수는 신규 라우터에서 거의 사용되지 않으므로 추후 정리 가능하다.
15. 레거시 `risk_index` 실제 DB 스키마와 SQLAlchemy 레거시 `RiskIndex` 모델 사이에 컬럼 불일치가 있다.
    신규 API는 사용하지 않아 현재 서비스에는 영향이 없지만 레거시 테이블을 ORM으로 직접 조회하면
    `실제폐업률_pct` 미존재 오류가 날 수 있다. 레거시 정리 단계에서 별도로 처리해야 한다.

---

## 21. 권장 후속 작업 순서

1. 조기경보 카드에 상대 기여 요인 표시
2. 경보 상세 화면에 접촉 이력 UI 연결
3. 정책 필드 `growth_prob`를 `store_count` 또는 `benefit_scale`로 명확화
4. 사용하지 않는 JSON 기반 위험등급 함수 정리 검토
5. 레거시 테이블·ORM 불일치 정리 여부 검토

대규모 구조 변경 전에는 현재 코드와 이 문서가 일치하는지 먼저 검증하고 사용자 승인을 받는다.

---

## 22. Claude에게 전달할 요청문

```text
이 인계 문서를 기준으로 현재 Git diff와 실제 코드를 먼저 검토해줘.

이미 완료된 정규화 DB, 0002 마이그레이션, 임포터, JWT, 업종 필터, 지도 요약,
예측 기여도, 접촉 이력 구현을 되돌리거나 재작성하지 마.

먼저 코드와 인계 내용이 일치하는지 검증하고 결과를 알려줘. 이후 남은 우선순위는
1) 조기경보 카드에 상대 기여 요인 표시
2) 경보 상세 화면에 접촉 이력 UI 연결
3) 정책 필드 growth_prob 명칭 정리
4) 레거시 스키마 정리 여부 검토
순서다.

행정데이터 원본을 외부 AI API에 전송하지 말고, predicted_closure_rate_internal과
contribution_value_internal을 API에 노출하지 마. 승인 없이 대규모 구조 변경이나 레거시 테이블
삭제를 하지 마.
```
