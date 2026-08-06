# 발표용 팩트시트 (2026-08-04 기준 실제 파일 검증)

이 문서는 실제 산출 파일(json/csv/log/pkl)만 읽어서 작성했다. 모든 숫자 옆에 근거 파일을 표기했다.
확인 못 한 항목은 "확인 불가"로 남겼다. `CLAUDE.md`(2026-08-03/04 갱신)는 이번 조사와 정합적이라
그대로 신뢰 가능한 반면, `docs/modeling.md`는 **Phase 4 재작성 이전(구 파이프라인 t11/v3 기준) 문서라
현재 상태와 다수 어긋난다** — 아래 각 절에서 "과거 문서 → 현재 파일" 형태로 명시했다.

---

## 1. 현재 최종 모델

### 1-1. 모델 정체 (가장 중요)

| 항목 | 현재 값 | 근거 파일 |
|---|---|---|
| 파이프라인 재작성 시점 | Phase 4, 2026-08-03 | `CLAUDE.md` |
| 학습 스크립트(현재) | `ai/train_model.py` | 파일 존재 확인 |
| 데이터 생성 스크립트(현재) | `ai/build_dataset.py` | 파일 존재 확인 |
| 구버전 스크립트 위치 | `ai/archive/`(23개 파일, train_closure_model.py~v4, build_and_train_v3_t11.py 등) | `ai/archive/` 디렉토리 목록 |
| **주력(프로덕션) 모델** | **셀단위(행정동×상권업종중분류) LightGBM 회귀** — `폐업률` 연속값 직접 예측 | `ai/train_model.py` 주석, `data/processed/lgbm_model_cell.pkl` |
| 참고용 모델 | 점포단위(개별 점포) LightGBM 이진분류 — `label_h2`(관측분기+2분기 시점 폐업 여부) | `ai/train_model.py`, `data/processed/lgbm_model_store.pkl` |
| 셀 모델 feature | 행정동명, 상권업종중분류명, 임대료_매핑그룹, 평균업력_분기수, 점포수 | `data/processed/model_cell_results.json` |
| 점포 모델 feature | 행정동명, 상권업종대분류명, 상권업종중분류명, 임대료_매핑그룹, 업력_분기수, 최근1분기이탈률 | `data/processed/model_store_results.json` |
| 셀 모델 하이퍼파라미터 | LGBMRegressor, n_estimators=1000, lr=0.05, num_leaves=31, min_child_samples=20, early_stopping(50) | `ai/train_model.py` |
| 점포 모델 하이퍼파라미터 | LGBMClassifier, n_estimators=2000, lr=0.05, num_leaves=63, min_child_samples=50, early_stopping(100) | `ai/train_model.py` |
| Train/Valid/Test 분할 | Train ≤2023Q2 / Valid ~2024Q2 / Test 2024Q3~ | `model_store_results.json` (`split`), `ai/train_model.py` |
| DB `통합카테고리` grain | 상권업종중분류 74개 (구버전: 대분류 10개) | `CLAUDE.md`, `ai/build_dataset.py` 주석 |

### 1-2. 구 LightGBM(v3-t11) 모델과의 차이

| 항목 | 과거(v3-t11, `ai/archive/build_and_train_v3_t11.py`) | 현재(Phase 4, `ai/train_model.py`) |
|---|---|---|
| 라벨 | "다음분기 점포수 증가 여부"(구버전 초기) → v3-t11에서 폐업여부(1분기 부재=폐업, 갭필링 threshold=11) | `label_h2`(관측분기 기준 **+2분기** 시점 폐업 여부, 갭필링 threshold=11 그대로 유지) |
| 프로덕션 주력 단위 | 점포단위 이진분류(PR-AUC 0.075 기준점) | **셀단위(중분류) 회귀**로 전환 |
| `통합카테고리` grain | 실험상 대분류/중분류 병행 비교 | 중분류(74개)로 확정, DB 3개 테이블 전부 통일 |
| 결과 파일 | `data/processed/model_v3_t11_results.json` (Jul 24) | `data/processed/model_cell_results.json` + `model_store_results.json` (Aug 4, 최신) |

### 1-3. 현재 실제 성능 지표

**셀단위(주력, 중분류, n≥30) — 회귀:**

| 지표 | 값 | 근거 |
|---|---|---|
| 스피어만 상관 | **0.4193** | `data/processed/model_cell_results.json` |
| 리프트(상위 10%, 분위수 기준) | **1.444x** | 同 |
| Test n | 1,565 | 同 |
| best_iteration | 88 | 同 |
| 팀원 벤치마크(구 점포모델 집계, 중분류) 대비 | 0.293 → 0.419 (상회) | `ai/train_model.py` 주석, `docs/modeling.md` 6절 |

**점포단위(참고용) — 이진분류:**

| 지표 | 값 | 근거 |
|---|---|---|
| ROC-AUC | **0.5550** | `data/processed/model_store_results.json` |
| PR-AUC | **0.1389** | 同 |
| Test n | 148,585 | 同 |
| Test 양성비율(=폐업률) | 11.79% | 同 |
| best_iteration | 44 | 同 |

**과거 문서 → 현재 파일 (성능 지표 불일치 주의):**
`docs/modeling.md` 6절은 "최종 모델"로 `model_v3_t11_results.json`을 인용하며 PR-AUC 0.075/ROC-AUC 0.555,
셀 회귀(중분류) 스피어만 0.293/리프트 1.501x를 제시한다. **이는 Phase 4 이전 구버전 결과다.**
현재 파일 기준 점포모델 ROC-AUC는 우연히 거의 같은 0.555이지만 PR-AUC는 0.075→0.139로 크게 달라졌고,
셀 회귀(주력) 스피어만은 0.293→**0.419**로 개선됐다(집계 방식·feature·grain이 바뀐 결과로 추정,
`docs/modeling.md`가 갱신되지 않아 발생한 불일치 — **발표 자료는 반드시 `model_cell_results.json`/
`model_store_results.json`(Aug 4) 수치를 써야 함**).

---

## 2. 현재 모델이 실제로 쓰는 데이터

### 2-1. 데이터 소스 (현재 `ai/build_dataset.py` 기준)

| 소스 | 역할 | 비고 |
|---|---|---|
| 소진공 상가(상권)정보 21개 분기 zip(2020Q4~2025Q4) | 점포 존재 여부 원천, 라벨 생성 | `eda_paths.SBIZ_DIR` |
| 화성시 인허가데이터(12종, `PERMIT_DIR`) | 업력(`업력_분기수`) 계산용 인허가일자 매칭만 사용 | 학원교습소정보.csv는 스키마 달라 자동 제외 |
| — | — | — |

**현재 스크립트에서 제외/미사용:**

| 데이터 | 제외 여부 | 근거 |
|---|---|---|
| 카드매출 | `ai/build_dataset.py`/`train_model.py`에 카드매출 관련 컬럼·로직 없음 → 미사용 | `docs/modeling.md` 2-3절: "포함 여부와 무관하게 PR-AUC 완전히 동일(0.0737)" 실험 결론에 따라 제외된 것으로 추정 |
| 유동인구 | 미사용(feature 목록에 없음) | `docs/modeling.md` 2-4절: 절대값 불연속, share만 보존 |
| KOSIS 지역통계 | 미사용 | `docs/modeling.md` 2-5절: carry-forward 플래그가 시간 대리변수화되는 문제로 배제 |
| R-ONE 임대가격지수·공실률 | 미사용(대신 `임대료_매핑그룹`=동탄권/병점권/기타 3분류로 대체) | `ai/build_dataset.py`의 `rent_group()` |

### 2-2. 최종 학습 테이블 (실측)

| 파일 | 행 수 | 근거 |
|---|---|---|
| `data/processed/store_panel.csv`(갭필링 패널) | 873,035행 | `wc -l` |
| `data/processed/final_dataset.csv`(CommercialData 원천) | 35,505행 | `wc -l` (CLAUDE.md 수치와 일치) |
| `data/processed/store_train_table.csv`(점포단위 학습용) | 873,035행, 19개 컬럼 | `wc -l` + 헤더 확인 |
| `data/processed/cell_train_table.csv`(셀단위 학습용, n≥30 필터 전) | 37,456행, 7개 컬럼 | 同 |

**라벨(`label_h2`) 통계 — `store_train_table.csv` 실측(직접 재계산):**

| 항목 | 값 |
|---|---|
| 라벨 판정 가능 행(notna) | 784,408 / 873,035 |
| 전체 양성비율(폐업률) | 8.20% |
| 폐업(양성) 총합 | 64,288건 |

**연도별 폐업률(직접 집계, `label_h2` 기준):**

| 연도 | 폐업률 | 폐업건수 | 관측행수 |
|---|---|---|---|
| 2020 | 6.07% | 2,122 | 34,938 |
| 2021 | 5.77% | 8,641 | 149,788 |
| 2022 | 9.06% | 14,829 | 163,704 |
| 2023 | 6.76% | 11,297 | 167,175 |
| 2024 | 9.51% | 16,698 | 175,579 |
| 2025 | 11.48%(연도 미완결) | 10,701 | 93,224 |

(위 표는 `label_h2` 기준 — 소진공 스냅샷 raw diff가 아니라 갭필링 패널 기준이므로 2023Q1 결함이 반영되지 않음. 2025년은 연도 데이터가 부분적이라 절대비교 주의.)

**최종 라벨 파일명(현재):** 별도 `sbiz_labels_*.csv` 파일이 아니라 `store_train_table.csv` 자체가 `label_h2` 컬럼을 포함한 최종 라벨 테이블. 구버전 라벨 파일(`archive/labels/sbiz_labels_v3_t11.csv` 등)은 archive로 이동되어 더 이상 파이프라인에서 참조되지 않음(`ai/train_model.py`, `ai/build_dataset.py`에 해당 경로 미참조 확인).

---

## 3. 데이터 검증 서사 (2023Q1 결함 등)

**출처: `docs/modeling.md`(Phase 3, `ai/verify_*.py`/`.log` 로그 기반). 이 서사 자체는 갭필링 로직(threshold=11)이 Phase 4에도 그대로 유지되므로 현재 데이터에도 유효하다.**

| 검증 항목 | 수치 | 근거 로그 |
|---|---|---|
| 2022Q4→2023Q1 이탈 점포 수 | 11,223개(다른 분기 평균 1,696개) | `ai/verify_2023q1_departure.log` |
| 통계청(KOSIS) 대조 | 소진공 -16.9%(업종 좁혀도 -13.4%) vs 통계청 도소매+숙박음식업 -5.2% | `ai/verify_2022_2023_external.log` |
| 행정동별 증감률 상관(소진공 vs 통계청) | 피어슨 -0.088~0.268(거의 무관) | 同 |
| 인허가 교차검증 — "영업/정상" 잔류 비율 | 46.8%(5,248/11,223건) | `ai/verify_2023q1_departure.log` |
| 2023Q1 폐업확인율 | 36.3%(다른 분기 평균 48.6%) | 同 |
| 재등장률(상가업소번호 기준) | 72.1%(8,091/11,223) | 同 |
| 재등장률(상호명+주소 기준) | 78.9% | 同 |
| 실물(인허가상태) 확인 표본 | 10건 전부 "영업/정상" (외부 지도 실사 확인은 미실시 — **확인 불가**) | 同 |

**갭필링 임계값 검증(threshold 4→8→11):**

| threshold | 2025Q3 잔여 개업 스파이크 |
|---|---|
| 4 | 4,106건 |
| 8 | 2,491건 |
| 11(채택) | 1,443건 |

근거: `ai/build_and_train_v3_t11.log`. 2024Q4 스파이크는 threshold 8/11 모두 9,090건으로 불변(갭필링으로 못 고치는 잔여 이상치로 결론).

**라벨 버전 히스토리(archive 실측):**

| 버전 | 행수 | 파일 |
|---|---|---|
| v1 | 773,454행, 12컬럼 | `archive/labels/sbiz_labels.csv` |
| v2 | 817,741행, 12컬럼 | `archive/labels/sbiz_labels_v2.csv` |
| v3 | 862,367행, 13컬럼 | `archive/labels/sbiz_labels_v3.csv` |
| v3b | 862,367행, 14컬럼(label_h1 포함) | `archive/labels/sbiz_labels_v3b.csv` |
| **최종(Phase 4)** | `store_train_table.csv`(873,035행, label_h2) | 갭필링 패널 기반, 별도 labels 파일 없이 build_dataset.py에서 직접 생성 |

**기타 데이터 함정(`docs/modeling.md` 2절 실측):**

| 함정 | 수치 | 근거 |
|---|---|---|
| 유동인구 API(`TB25BPTGGPOPSIGDONGTMM`) 중복 | 24개 행정동 값이 전부 15,660.49로 동일(고유값 1개) | `docs/modeling.md` 2-4절 |
| 유동인구 대체 API(`floating_pop_hwaseong.csv`) share 상관 | 스피어만 0.922 (절대값은 2021-12→2022-01 사이 0.143→4.4배로 단절) | `ai/new_flow_pop_continuity.log` |
| 카드매출 결측 구간 | 2024-02~2024-12(11개월) 원본 자체 없음 | `docs/modeling.md` 2-3절 |
| 카드매출 신·구 코드 불연속 | 종합소매 2021Q4→2024Q1 -69.2%, 자동차 -96.7%(실제 매출 감소 아님) | `archive/card/card_industry_continuity_check.csv` |
| 카드매출 포함 여부 성능 차이 | 없음(PR-AUC 0.0737로 동일, 공정비교) | `archive/experiments/model_comparison_results.json` |
| 인허가 매칭률 | 70.3%(인허가일자 유효값 기준)/80.8%(주소만 기준) | `ai/train_closure_model_v3.log`, `ai/train_table.log` |

---

## 4. 상권분석 결과

### 4-1. 연도별 개업 vs 폐업 트렌드 (직접 재계산, `final_dataset.csv` 트레일링 통계)

| 연도 | 개업율 평균 | 폐업률 평균 |
|---|---|---|
| 2021 | 5.64% | 2.15% |
| 2022 | 5.02% | 2.44% |
| 2023 | 5.98% | 4.17% |
| 2024 | 9.15% | 4.43% |
| 2025 | **3.75%** | **4.27%** |

**2025년(부분 연도) 최초로 폐업률이 개업율을 역전** — 데이터가 있는 최신 시점(20254=2025Q4)까지 포함한 결과. 다만 2025년은 연도가 아직 완결되지 않았고 분기별 변동이 큰 편(20251 폐업률 6.11% vs 20254 2.68%)이라 "확정 크로스오버"로 단정하기보다 "주의 신호"로 표현하는 것이 안전함.

### 4-2. 행정동별 폐업률 랭킹 (`final_dataset.csv` 직접 집계)

**낮은 폐업률 Top5:**

| 행정동 | 폐업률 평균 | 개업율 평균 |
|---|---|---|
| 매송면 | 2.28% | 3.04% |
| 양감면 | 2.65% | 4.61% |
| 기배동 | 2.66% | 3.99% |
| 비봉면 | 2.71% | 5.80% |
| 팔탄면 | 2.88% | 4.53% |

**높은 폐업률 Top5:**

| 행정동 | 폐업률 평균 | 개업율 평균 |
|---|---|---|
| 동탄8동 | 4.10% | 10.29% |
| 동탄5동 | 4.33% | 7.53% |
| 동탄1동 | 4.35% | 6.82% |
| 동탄7동 | 4.53% | 11.18% |
| 새솔동 | **4.89%** | 10.60% |

**해석**: 신흥개발지(동탄7·8동, 새솔동)는 개업율도 폐업률도 모두 높은 "고회전" 지역이라는 `docs/modeling.md` 5절(share변화↔폐업률변화 피어슨 +0.598)의 결론과 방향이 일치한다. 다만 `docs/modeling.md`는 "카드매출 share 상승 Top1=동탄7동(+5.02%p)"을 근거로 들었는데 그 카드매출 share 분석 파일(`dong_share_shift_ranked.csv`, `share_vs_closure_check.csv`)은 Phase 4 이전 산출물이라 현재 파이프라인이 재생성하지 않는다 — **이 상관계수(+0.598) 자체는 재검증 못 함, 확인 불가**로 남긴다. 위 폐업률 랭킹표는 현재 `final_dataset.csv`로 직접 재계산한 것이라 신뢰 가능하다.

동탄1동은 `docs/modeling.md`에서 "건강한 희석"(폐업률 변화가 27개 동 중 중앙값 수준)이라고 서술했으나, 현재 데이터 재계산 결과 동탄1동은 폐업률 Top5(4.35%)에 든다 — **과거 문서(중앙값 수준) → 현재 재계산(상위권)**, 판단 기준(전년대비 변화율 vs 절대 수준)이 달라 직접 비교는 어려우나 "동탄1동=안정적"이라는 서술을 발표에 그대로 쓰지 않는 것을 권장.

### 4-3. 폐업위험점수 분포 (`risk_index.csv` 실측)

| 항목 | 값 |
|---|---|
| 전체 범위 | 0.1 ~ 16.9 (CLAUDE.md가 명시한 "0~20 근처로 좁게 나옴" 이슈와 일치) |
| 위험점수 낮은 Top5 | 서신면(2.03), 양감면(2.32), 팔탄면(2.52), 우정읍(2.62), 화산동(2.65) |
| 위험점수 높은 Top5 | 동탄8동(5.32), 동탄7동(5.81), 동탄4동(6.16), 새솔동(6.77), **동탄9동(7.24)** |
| 이상탐지 플래그 True 비율 | 95 / 1,810행 (5.2%) |

---

## 5. 대시보드/기능 구현 현황

`CLAUDE.md`에 기술된 라우터·페이지 파일이 실제로 전부 존재함을 확인(내용까지 정합적):

| 파일 | 줄 수 | 상태 |
|---|---|---|
| `backend/routers/auth.py` | 33줄 | 존재 |
| `backend/routers/alerts.py` | 105줄 | 존재 — `/api/alerts/closure-risk`, `/api/alerts/vacancy-risk/map` |
| `backend/routers/policy.py` | 93줄 | 존재 — `/api/policy/fund-priority` |
| `backend/routers/analysis.py` | 99줄 | 존재 — `/api/analysis/dongs`, `/dong`, `/score`, `/categories`, `/quarters` |
| `backend/routers/consultation.py` | 84줄 | 존재 — `/api/consultation/startup` |
| `frontend/src/pages/DashboardPage.jsx` | 247줄 | 존재(조기경보 Top10) |
| `frontend/src/pages/MapPage.jsx` | 238줄 | 존재(Naver Maps choropleth) |
| `frontend/src/pages/PolicyPage.jsx` | 263줄 | 존재(4분면 매트릭스) |
| `frontend/src/pages/ConsultPage.jsx` | 214줄 | 존재(창업 상담) |
| `frontend/src/pages/OfficialLoginPage.jsx` / `CitizenLoginPage.jsx` / `RoleSelectPage.jsx` | 190/191/112줄 | 존재(로그인 흐름) |

**데모 영상에 보여줄 수 있는 화면**: 역할 선택 → 로그인(공무원/시민) → 대시보드(조기경보 Top10) → 지도(공실위험 choropleth) → 정책자금 매트릭스(공무원) / 창업 상담(시민). 6개 화면 모두 코드 존재 확인됨. 단, 실제 브라우저 구동·API 응답까지는 이번 조사에서 실행 검증하지 않음(정적 코드 확인만) — **런타임 동작 확인 불가**.

**아직 구현 안 된 것**: `당월매출합`, `총_유동인구_수` 컬럼은 원본 데이터 미확보로 DB에 항상 NULL(`CLAUDE.md`). 셀프 위험진단, 창업 적합도 고도화, 공개 대시보드는 "확장 계획(경진대회 이후)"로 명시되어 미구현.

---

## 6. 한계 (정직하게)

| 한계 | 내용 | 근거 |
|---|---|---|
| 점포단위 예측력 낮음 | PR-AUC 0.139로 절대적으로 낮은 편(양성비율 11.8% 대비) — 개별 점포 운명보다 "동네·업종 단위 위험도"가 이 데이터로는 더 현실적 목표 | `model_store_results.json`, `docs/modeling.md` 6절 |
| 셀단위 표본 희소성 | 중분류 셀 36,355개 중 점포수 중앙값 7개(평균 22.49) — n≥30 필터로 학습하지만 필터링 전 원본 셀 대부분은 표본이 매우 작음 | `docs/modeling.md` 4절(`ai/panel_skeleton.log`) — 이 로그 자체는 Phase 4 이전 산출이라 정확한 재현치는 **확인 불가**, 다만 `cell_train_table.csv` 37,456행 중 n≥30 필터 후 실제 학습에 쓰인 행은 Test 기준 1,565행뿐(`model_cell_results.json`)이라 필터링으로 상당수가 제외됨은 확인됨 |
| 폐업 vs 장기휴업 미구분 | 소진공 스냅샷은 명단 존재 여부만 알려줄 뿐 폐업/휴업/명의변경/데이터누락을 구분 못함. 갭필링(threshold=11)도 짧은 부재를 존속으로 간주하는 보정일 뿐, 진위를 확정하지 않음 | `docs/modeling.md` 3-3절 — 이 한계는 Phase 4에서도 해소되지 않음(갭필링 로직 자체가 유지됨) |
| 2024Q4 잔여 이상치 | 갭필링 threshold를 8→11로 올려도 2024Q4 스파이크(9,090건)는 불변 — 데이터 제공처의 주기적 재동기화로 추정 | `ai/build_and_train_v3_t11.log`(Phase 4 이전 로그, 현재 파이프라인도 threshold=11 그대로 사용하므로 유효할 가능성 높으나 **직접 재검증은 안 함 — 확인 불가**) |
| `폐업위험점수` 단위 불일치 | `(100-성장확률)×0.6 + 폐업_률_평균×0.4` 산식에서 성장확률(0~100)과 폐업_률_평균(0~1)의 스케일이 안 맞아 결과가 0.1~16.9 좁은 범위로 나옴(실측 확인) | `CLAUDE.md`, `data/processed/risk_index.csv` |
| **`risk_level()` 임계값-실제값 불일치(신규 발견)** | `backend/services/risk.py`의 `risk_level()`이 위험/주의/안전을 70/50 기준으로 나누는데, 실제 `폐업위험점수`는 0.1~16.9 범위라 이 함수는 사실상 모든 행을 "안전"으로 분류함(70·50 임계값에 도달하는 행이 없음) | `backend/services/risk.py`(1~6행) + `risk_index.csv` 실측 범위 대조. `/api/alerts/vacancy-risk/map`(`backend/routers/alerts.py`)이 이 함수를 그대로 씀 — **문서에 언급 없는 실제 버그로 추정, 발표 전 확인 권장** |
| 카드매출·유동인구·KOSIS 미사용 | 검증 결과 효용 없음(카드매출) 또는 절대값 신뢰 불가(유동인구)로 최종 feature에서 배제 | 3절 표 참고 |
| 2025년 데이터 미완결 | 폐업률 역전(4-1절)이 부분 연도 기준이라 확정적 트렌드로 단정 시 주의 | `final_dataset.csv` 직접 집계 |

---

## 부록: 파일 mtime 기준 "현재 vs 과거" 판정 근거

| 파일 | mtime | 판정 |
|---|---|---|
| `data/processed/model_cell_results.json` | Aug 4 17:42 | **현재** |
| `data/processed/model_store_results.json` | Aug 4 17:42 | **현재** |
| `data/processed/lgbm_model_cell.pkl` / `lgbm_model_store.pkl` | Aug 4 17:42 | **현재** |
| `data/processed/scores.csv` / `risk_index.csv` | Aug 4 17:42/17:55 | **현재** |
| `data/processed/model_v3_t11_results.json` | Jul 24 17:02 | 과거(참고용) |
| `data/processed/train_table_v3_t11.csv` 등 t11 계열 | Jul 24 | 과거 |
| `docs/modeling.md` | (git상 Phase 3 산출, 74개 grain·model_cell_results.json 언급 없음) | 과거 문서 — 갱신 필요 |
| `CLAUDE.md` | 2026-08-03/04 갱신 명시 | **현재와 정합** |
| `models/lgbm_v3_h2.txt` | Jul 24 13:27 | 과거(archive 파이프라인 산출물로 추정, 현재 학습 스크립트는 `.pkl`로 저장하며 이 `.txt` 미참조) |
