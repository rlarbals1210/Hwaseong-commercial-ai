# 공공데이터 API 자동수집 준비

## 목적

기존 모델 입력 파일을 보존하면서 공식 API 응답을 별도 스테이징 영역에 누적한다.
API 키가 발급돼도 수집 결과가 곧바로 모델이나 PostgreSQL에 반영되지는 않는다.
기존 데이터와 행 수·분기·행정동·업종·식별자 체계를 대조해 통과한 원천만 이후 단계에서 승격한다.

```text
공식 API
  → data/raw/api_staging/<source>/<UTC시각>/
      ├── records.jsonl
      ├── records.csv
      ├── raw_records.jsonl
      └── manifest.json
  → 기존 파일과 대조
  → 별도 승인 후 운영 입력 전환
```

원본·API 응답은 Git에 포함하지 않는다. manifest에도 API 키는 `***`로 마스킹한다.
`raw_records.jsonl`은 공급자의 원본 필드를 보존하고, `records.*`는 현재 파이프라인과
대조하기 위한 정규화 뷰다.

## 현재 준비된 원천

| 원천 | 환경변수 | 수집 범위 | 현재 승격 차단 사유 |
|---|---|---|---|
| 소진공 상가정보 | `PUBLIC_DATA_SERVICE_KEY` | 화성시 시군구코드 41590 | 상가업소번호 재채번 및 중분류 74→75 변경 |
| LOCALDATA | `LOCALDATA_AUTH_KEY` | 화성시 변동분 | 기존 12종 전체분과 복합키 upsert 대조 필요 |
| 경기데이터드림 유동인구 | `GG_OPENAPI_KEY` | `TB25BPTPOPDAYDONGM` | 기존 정상판과 월·행정동 커버리지 대조 필요 |
| KOSIS 등록인구 | `KOSIS_API_KEY` + 통계표 파라미터 | 분기말 읍면동 등록인구 | 2026년 구 신설 전후 행정구역 중복 대조 필요 |

카드매출 `card_sales_hwaseong.csv`와 카드 업종 코드표는 현재 파일 제공 방식이므로 이 API 수집기의
대상이 아니다. 두 파일은 공무원 로그인 후 **데이터 관리** 화면에서 업로드하며,
`data/raw/manual_uploads/`에 검증된 버전으로 보관된다.

## 키 발급 전

```bash
cp .env.example .env
python ai/sync_public_data.py status
python -m unittest ai.tests.test_sync_public_data
```

기존 `.env`가 있으면 덮어쓰지 말고 `.env.example`의 API 항목만 옮긴다.

## 키 발급처

- 소진공: 공공데이터포털 `소상공인시장진흥공단_상가(상권)정보_API` 활용신청
- LOCALDATA: `데이터받기 → OPEN API(변동분) → OPEN API 신청`
- 경기데이터드림: `OpenAPI → 인증키발급`
- KOSIS: `공유서비스 → OPEN API 인증키 신청`

키 값은 채팅, Git, 프론트엔드 환경변수에 넣지 않는다. 루트 `.env`에만 저장한다.

## 수집 명령

```bash
# 준비 상태만 확인 — 키 값은 출력하지 않는다.
python ai/sync_public_data.py status

# 소진공 현재 영업 점포 스냅샷
python ai/sync_public_data.py sbiz

# LOCALDATA 변동분. 공식 제한 때문에 날짜를 빠뜨리지 않고 주기 실행해야 한다.
python ai/sync_public_data.py localdata --start 20260825 --end 20260830

# 경기데이터드림 유동인구
python ai/sync_public_data.py gyeonggi-flow

# KOSIS 등록인구
python ai/sync_public_data.py kosis-population

# 설정이 끝난 원천만 실행
python ai/sync_public_data.py sync-ready
```

LOCALDATA는 전체분이 아니라 제한된 기간의 변동분만 제공한다. 기존 12종 CSV를 초기 기준선으로
유지하고, 향후에는 `(개방서비스ID, 개방자치단체코드, 관리번호)` 복합키로 변동분을 누적해야 한다.

## KOSIS 추가 설정

KOSIS는 API 키만으로 어느 통계표와 항목을 가져올지 알 수 없다. KOSIS URL 생성기에서 다음 조건을
선택한 뒤, 생성된 URL의 `apiKey`를 제외한 파라미터를 JSON으로 옮긴다.

- 지역: 화성시 읍면동
- 항목: 총인구수
- 주기: 월
- 기간: 필요한 전체 기간 또는 최근 갱신분

예시는 특정 통계표 ID를 임의로 고정하지 않기 위해 비워 둔다.

```dotenv
KOSIS_POPULATION_PARAMS_JSON={"orgId":"발급 화면 값","tblId":"발급 화면 값","prdSe":"M","startPrdDe":"202001","endPrdDe":"202612","objL1":"발급 화면 값"}
```

수집기는 3·6·9·12월만 분기코드로 변환하고, 읍·면·동이 아닌 시·구 합계는 제외한다.

## 운영 승격 전 검증

### 소진공

- 기존 2025Q4와 신규 API의 상가업소번호 교집합
- 중분류 74개와 신규 75개 매핑
- 29개 행정동 커버리지
- 식별자 변경을 폐업으로 오인하지 않는지

### LOCALDATA

- 기존 전체분과 변동분 복합키 중복·수정 처리
- `인허가일자`, `지번주소`, `폐업일자` 완전성
- 기존 12종 인허가 범위와 서비스ID 일치 여부

### 경기데이터드림·KOSIS

- 기존 파일과 최신 공통 월의 행 수 및 행정동 수
- 행정구역 개편 전후 코드 중복
- 유동인구 측정 기준 변경에 따른 절대값 단절
- KOSIS 구 단위와 읍면동 단위 중복 합산 방지

검증 실패 시 스테이징 데이터는 보관하되 기존 파일·모델·DB를 유지한다.
