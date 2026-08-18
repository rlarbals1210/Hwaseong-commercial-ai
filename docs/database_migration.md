# 정규화 DB 전환 절차

기존 `commercial_data`·`score_data`·`risk_index`는 롤백을 위해 보존한다. 신규 API는
`admin_areas`·`industry_categories`·`commercial_quarters`·`model_runs`·
`risk_predictions`를 조회한다. `20260818_0002`부터 위험 기준선·동별 요약·예측 기여도와
공무원 접촉 이력을 별도 grain으로 저장한다.

## 1. 사전 준비

```bash
pip install -r requirements.txt
```

운영 또는 팀원 DB는 실행 전 `pg_dump`로 별도 백업한다. 비밀번호·백업 파일은 저장소에 커밋하지 않는다.

## 2. Migration 적용

기존 DB처럼 레거시 테이블이 이미 있고 `alembic_version`만 없는 경우 최초 1회:

```bash
alembic stamp 20260818_0000
alembic upgrade head
```

비어 있는 신규 DB인 경우:

```bash
alembic upgrade head
```

현재 revision 확인:

```bash
alembic current
```

`20260818_0002 (head)`가 표시되어야 한다.

## 3. 검증 산출물 적재

```bash
python ai/import_normalized_db.py

# M1 기여도 쏠림 검증(90% 이하) 후 통과한 경우에만 적재
python ai/build_explanations.py --validate-only
python ai/build_explanations.py
```

적재기는 다음 원칙을 지킨다.

- 관측 팩트는 `행정동×업종×분기` 복합키 upsert
- 모델 결과는 `model_run`별 이력 보존
- 활성 모델은 한 실행만 유지
- `risk_index.csv` 구버전에 의존하지 않고 최신 4분기 추세와 예측 순위를 재계산
- 최신 예측에만 있고 트레일링 비율을 계산할 수 없는 신규 셀은 점포수를 보존하고 표본부족으로 처리
- 정책 프로그램 4종을 idempotent seed
- 최신 분기의 위험 기준선·표본 기준을 `risk_threshold_sets`에 이력 저장
- 셀 등급과 표본 판정을 `commercial_quarters`에 저장
- 지도용 29개 동 집계를 `area_quarter_summaries`에 저장
- 기여 요인은 범주형 중첩 변수를 병합하고 M1 검증 통과 시에만 적재

현재 산출물 기준 기대값:

```text
admin_areas                29
industry_categories        74
commercial_quarters    35,513
risk_predictions        1,810
예측순위 보유 셀           382
risk_threshold_sets         1
area_quarter_summaries      29
prediction_contributions 1,146
policy_programs              4
```

`commercial_quarters`가 기존 `final_dataset.csv`보다 8행 많은 이유는 최신 분기에 처음 등장해
개·폐업률이 아직 계산되지 않은 점포 1~2개짜리 예측 셀을 관측 팩트로 보존하기 때문이다.

## 4. 동작 확인

백엔드 실행 후 아래 기능을 확인한다.

- `/api/analysis/dongs`: 29개
- `/api/analysis/categories`: 74개
- `/api/alerts/closure-risk`: 표본충분 예측 순위
- `/api/alerts/vacancy-risk/map`: 29개 동
- `/api/alerts/{prediction_id}/contributions`: 상대 기여 요인(원 기여도 비노출)
- `/api/policy/fund-priority`: Q1~Q4 결과
- `/api/workflow/alerts/{alert_id}/contacts`: 접촉 이력 조회·추가
- `/api/workflow/contacts/{contact_id}`: 접촉 이력 수정·삭제
- `/api/workflow/*`: 경보 확인→근거·접촉 추가→정책 실행→성과 기록

## 5. 레거시 제거

이번 전환에서는 레거시 3개 분석 테이블을 삭제하지 않는다. 신규 API와 배포 DB 검증이 완료된 뒤
별도 migration으로 `_legacy` 이름 변경 및 최종 삭제를 수행한다.
