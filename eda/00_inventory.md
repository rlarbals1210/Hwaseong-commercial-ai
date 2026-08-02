# 인벤토리 — 원본 데이터 확인표 + 기존 ai/ 스크립트 정리

이 문서는 코드가 아니라 참고자료다. Phase 4(파일구조 재정리)에서 "뭘 남기고 뭘 `archive/`로
옮길지" 판단할 때 근거로 쓴다. 지금 당장 아무 파일도 삭제/이동하지 않는다.

## 1. 원본 데이터 확인표

`RAW_DATA_DIR=/Volumes/SSD/hwaseong-commercial` (`.env`), 실제 데이터는 그 아래
`hwaseong-commercial-dataset/` 폴더에 있음 (`eda/paths.py`가 이 경로들을 상수로 제공).

| 데이터 | 파일/폴더 | 상태 |
|---|---|---|
| 소진공 상가(상권)정보 분기별 | `소상공인시장진흥공단_상가(상권)정보_분기별데이터/*.zip` (21개, 2020Q4~2025Q4) | ✅ |
| 업종코드표 | `소상공인시장진흥공단_상가(상권)정보 업종코드_20230228.csv` | ✅ |
| 인허가데이터 | `화성시_인허가데이터/` (13개 CSV — 12종 + `학원교습소정보.csv`) | ✅ |
| 카드매출 | `card_sales_hwaseong.csv` | ✅ |
| 유동인구(깨진 버전) | `유동인구_화성시_행정동_시간대별.csv` | ✅ (EDA에서 결함 재확인용으로 보존) |
| 유동인구(정상 버전) | `floating_pop_hwaseong.csv` | ✅ 신규 확보 |
| KOSIS 세대·인구 | `읍·면·동별_세대_및_등록인구_20260724063340.csv` | ✅ 신규 확보 |
| KOSIS 사업체·종사자수 | `산업별_읍면동별_사업체수_및_종사자수_20260724063757.csv` | ✅ 신규 확보 |
| 화성시 인구동향 시계열 | `화성시_인구동향_시계열.csv` | ✅ |
| R-ONE 공실률 | `임대동향 지역별 공실률/` (10개 CSV) | ✅ |
| R-ONE 임대가격지수 | `임대동향 지역별 임대가격지수(시계열)데이터/` (3개 CSV) | ✅ |
| 법정동코드 전체자료 | `법정동코드 전체자료/법정동코드 전체자료.txt` | ✅ |
| 경기도 읍면동 리스트 | `경기도_읍면동_리스트.csv` | ✅ |

데이터 갭 없음 — Phase 1(EDA)부터 바로 진행 가능.

## 2. 기존 `ai/` 스크립트 27개 인벤토리

각 스크립트 자체 docstring을 근거로 요약(추측 없음). "상태" 컬럼은 Phase 4에서 정리 방향을
가늠하기 위한 잠정 분류.

### 구버전 파이프라인 (CLAUDE.md 문서화 버전, 교체 대상)

| 파일 | 역할 | 비고 |
|---|---|---|
| `build_dataset.py` | 21개 분기 스냅샷 → 행정동×업종×분기 집계(점포수/개업율/폐업율), 라벨="다음분기 점포수 증가 여부" | 매출·유동인구 미확보 상태에서 만든 대체 라벨. Phase 0 Context에서 확인한 경로 하드코딩 문제 있음(`"Hwaseong-commercial-ai-main-dataset"`) |
| `train_model.py` | `final_dataset.csv` → LightGBM 학습 → `scores.csv` | Seoul 프로젝트 `retrain_scores.py`와 동일 로직 이식 |
| `build_risk_index.py` | `scores.csv`+`final_dataset.csv` → 폐업위험지수 → `risk_index.csv` | |
| `import_to_db.py` | CSV 3종 → PostgreSQL 3개 테이블(TRUNCATE 후 재삽입) | DB 스키마 결정은 이번 계획 범위 밖이라 보류 가능 |

### 팀원 파이프라인 — 라벨링 계보 (실험본 → 최종본)

| 파일 | 역할 | 상태 |
|---|---|---|
| `build_sbiz_labels.py` | 점포×분기 패널, 라벨 v1(1분기 부재=폐업) | 실험본(초기) |
| `build_sbiz_labels_v2.py` | 라벨 v2(연속 2분기 부재=폐업), v1 파일은 보존 | 실험본 |
| `build_labels_v3.py` | 라벨 v3 — 갭필링으로 2023Q1 결함 복원 | 실험본 |
| `build_labels_v3b.py` | 라벨 v3b — 고정 4분기 확인창으로 최근분기 과대계상 보정 | 실험본 |
| `build_and_train_v3_t11.py` | 갭필링 임계값 8→11, 라벨+feature+모델 통합 재구축 | **최종본**(`docs/modeling.md` 명시) |

### 팀원 파이프라인 — feature 결합 보조 스크립트

| 파일 | 역할 |
|---|---|
| `build_panel_skeleton.py` | 업종체계 파악 → 행정동×업종×분기 뼈대 + label_h1/h2 집계(feature 없음) |
| `build_train_table.py` | 점포×분기 학습 테이블 — 인허가 매칭·업력·면적 등 feature 결합 |
| `add_kosis_features.py` | KOSIS 사업체·인구 통계 결합(2024~2025는 2023 carry-forward) |
| `build_card_sales_mapped.py` | 카드매출 신/구 코드 → 공통업종 14개 매핑 + 연속성 검증 |
| `analyze_industry_mapping.py` | 위 매핑표의 1차 초안 생성(확정 아님, 확신도 낮게 표시) |
| `identify_share_shift_dongs.py` | 카드매출 share 변화가 큰 행정동 식별 |
| `extract_sbiz_names.py` | 상호명 재추출(2023Q1 코호트 인허가 교차검증용) |

### 팀원 파이프라인 — 모델 학습 계보 (실험본)

| 파일 | 역할 |
|---|---|
| `train_closure_model.py` | 1차 — 라벨 3종×타깃 2종 비교, 베이스라인 3종 |
| `train_closure_model_v2.py` | 2차 — early stopping/시간대리변수 수정, 셀단위 회귀 추가 |
| `train_closure_model_v3.py` | 3차 — 업력 좌측절단 보정 |
| `train_closure_model_v4.py` | 예측기간 확대(`label_h1to4`) 실험 — 문서상 결과 나쁨(폐기 후보) |

### 검증 전용 (모델에 직접 안 들어감)

| 파일 | 역할 |
|---|---|
| `verify_2022_2023_drop_external.py` | 2022→2023 급감 vs 통계청 외부 대조 |
| `verify_2022q4_2023q1_gap.py` | 2023Q1 급감이 상가업소번호 재채번 때문인지 검증 |
| `verify_2023q1_departure_nature.py` | 2023Q1 이탈 성격 규명(핵심 — 라벨 최종 판정 근거) |
| `verify_new_flow_pop_continuity.py` | 유동인구(정상판) 연속성 검증 |
| `verify_scale_invariant_share.py` | share 기반 feature 사용 가능성 검증 |
| `verify_share_vs_closure.py` | 카드매출 share 변화와 실제 폐업률 관계 검증 |
| `verify_to_series.py` | 카드매출 TO(총계) 시계열 사용 가능성 검증 |

## 3. Phase 4 정리 방향 메모 (잠정, 확정 아님)
- 최종본 후보: `build_and_train_v3_t11.py`(팀원 기준) — 이번 재작업(`eda/`)에서 나온 결론으로 대체하거나 검증 후 채택
- 검증전용 7개는 결론만 `eda/00_inventory.md`·`eda/01_eda.ipynb`에 남기고 스크립트 자체는 `archive/`로 이동 후보
- 라벨링/학습 계보의 중간 버전(v1/v2/v3/v3b, train_closure_model v1~v3)은 진화 과정 기록용으로 `archive/`에 보존, 최종 파이프라인에는 최신 버전 로직만 반영
