"""공식 공공데이터 API를 운영 입력과 분리된 스테이징 영역에 수집한다.

API 키가 없어도 ``status``와 테스트를 실행할 수 있다. 실제 수집 결과는
``data/raw/api_staging`` 아래에 버전별 JSONL/CSV와 manifest로 저장한다. 이 스크립트는
기존 소진공 분기 ZIP, 인허가 CSV, 유동인구 CSV를 덮어쓰거나 모델을 자동 활성화하지 않는다.

현재 지원하는 원천:

- ``sbiz``: 소상공인시장진흥공단 상가(상권)정보
- ``localdata``: 지방행정인허가데이터 변동분
- ``gyeonggi-flow``: 경기데이터드림 요일별 유동인구
- ``kosis-population``: KOSIS 읍면동 등록인구(통계표 파라미터 필요)

사용법:

    python ai/sync_public_data.py status
    python ai/sync_public_data.py sbiz
    python ai/sync_public_data.py localdata --start 20260825 --end 20260830
    python ai/sync_public_data.py gyeonggi-flow
    python ai/sync_public_data.py kosis-population
    python ai/sync_public_data.py sync-ready
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # 상태 확인·표준 라이브러리 테스트는 의존성 설치 전에도 가능해야 한다.
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_STAGING_ROOT = PROJECT_ROOT / "data" / "raw" / "api_staging"
SBIZ_DEFAULT_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"
LOCALDATA_DEFAULT_URL = "https://www.localdata.go.kr/platform/rest/TO0/openDataApi"
GYEONGGI_DEFAULT_BASE_URL = "https://openapi.gg.go.kr"
KOSIS_DEFAULT_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

SECRET_NAMES = {
    "apikey",
    "authkey",
    "key",
    "servicekey",
    "public_data_service_key",
    "localdata_auth_key",
    "gg_openapi_key",
    "kosis_api_key",
}


class SourceSyncError(RuntimeError):
    """API 수집 또는 응답 검증 실패."""


class MissingConfiguration(SourceSyncError):
    """필수 API 키나 통계표 설정이 비어 있음."""


@dataclass(frozen=True)
class SourceReadiness:
    source: str
    ready: bool
    missing: tuple[str, ...]
    note: str


def _staging_root() -> Path:
    configured = os.getenv("API_STAGING_DIR", "").strip()
    if not configured:
        return DEFAULT_STAGING_ROOT
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _json_env(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MissingConfiguration(f"{name}은 JSON 객체여야 합니다: {exc}") from exc
    if not isinstance(parsed, dict):
        raise MissingConfiguration(f"{name}은 JSON 객체여야 합니다")
    return parsed


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingConfiguration(f"환경변수 {name}이 비어 있습니다")
    return value


def _redact_value(name: str, value: Any) -> Any:
    if name.lower() in SECRET_NAMES or "key" in name.lower():
        return "***"
    if isinstance(value, Mapping):
        return {child: _redact_value(child, item) for child, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(name, item) for item in value]
    return value


def _redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _redact_value(key, value) for key, value in values.items()}


def redact_url(url: str) -> str:
    """예외 메시지와 manifest에서 인증키가 노출되지 않게 한다."""
    parts = urlsplit(url)
    safe_query = urlencode(_redact_mapping(dict(parse_qsl(parts.query, keep_blank_values=True))))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, parts.fragment))


class JsonHttpClient:
    """표준 라이브러리만 쓰는 재시도 가능한 JSON GET 클라이언트."""

    def __init__(
        self,
        *,
        timeout: int = 30,
        attempts: int = 3,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.timeout = timeout
        self.attempts = attempts
        self.opener = opener

    def get(self, url: str, params: Mapping[str, Any]) -> Any:
        clean_params = {key: value for key, value in params.items() if value is not None and value != ""}
        separator = "&" if "?" in url else "?"
        request_url = f"{url}{separator}{urlencode(clean_params, doseq=True)}"
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "hwaseong-commercial-ai/1.0"},
        )
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read()
                text = _decode_response(raw)
                if text.lstrip().lower().startswith("<html"):
                    raise SourceSyncError("API가 JSON 대신 HTML 차단/안내 페이지를 반환했습니다")
                return json.loads(text)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, SourceSyncError) as exc:
                last_error = exc
                if attempt < self.attempts:
                    time.sleep(attempt)
        raise SourceSyncError(
            f"API 호출 실패: {redact_url(request_url)} ({type(last_error).__name__}: {last_error})"
        ) from last_error


def _decode_response(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return value
    return None


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if "item" in value:
            return _as_list(value["item"])
        if "row" in value:
            return _as_list(value["row"])
        if value.get("@class") == "list" and len(value) == 1:
            return []
        return [value]
    return []


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def parse_sbiz_page(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    service_error = payload.get("OpenAPI_ServiceResponse")
    if service_error:
        header = service_error.get("cmmMsgHeader", {})
        raise SourceSyncError(
            f"소진공 API 오류: {header.get('returnAuthMsg') or header.get('errMsg') or service_error}"
        )
    root = payload.get("response", payload)
    header = root.get("header", {}) if isinstance(root, dict) else {}
    result_code = str(header.get("resultCode", "00"))
    if result_code not in {"00", "0", "NORMAL_SERVICE"}:
        raise SourceSyncError(f"소진공 API 오류 {result_code}: {header.get('resultMsg', '')}")
    body = root.get("body", {}) if isinstance(root, dict) else {}
    items = _as_list(body.get("items"))
    return items, _integer(body.get("totalCount"), 0)


def normalize_sbiz_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "상가업소번호": _first(row, "bizesId", "상가업소번호"),
        "시군구코드": str(_first(row, "signguCd", "시군구코드") or ""),
        "행정동코드": str(_first(row, "adongCd", "행정동코드") or ""),
        "행정동명": _first(row, "adongNm", "행정동명"),
        "상권업종대분류명": _first(row, "indsLclsNm", "상권업종대분류명"),
        "상권업종중분류명": _first(row, "indsMclsNm", "상권업종중분류명"),
        "상권업종소분류명": _first(row, "indsSclsNm", "상권업종소분류명"),
        "지번주소": _first(row, "lnoAdr", "지번주소"),
        "도로명주소": _first(row, "rdnmAdr", "도로명주소"),
        "경도": _first(row, "lon", "경도"),
        "위도": _first(row, "lat", "위도"),
    }


def validate_sbiz(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise SourceSyncError("소진공 API가 화성시 점포를 0건 반환했습니다")
    required = ("상가업소번호", "행정동명", "상권업종중분류명", "지번주소")
    complete = sum(all(row.get(field) not in (None, "") for field in required) for row in records)
    completeness = complete / len(records)
    if completeness < 0.90:
        raise SourceSyncError(f"소진공 필수컬럼 완전성 {completeness:.1%} < 90%")
    wrong_region = sum(
        bool(row.get("시군구코드")) and not str(row["시군구코드"]).startswith("41590")
        for row in records
    )
    if wrong_region:
        raise SourceSyncError(f"화성시 이외 시군구 행 {wrong_region}건이 섞였습니다")
    return {
        "required_field_completeness": round(completeness, 6),
        "unique_store_ids": len({row["상가업소번호"] for row in records if row.get("상가업소번호")}),
        "medium_industries": len({row["상권업종중분류명"] for row in records if row.get("상권업종중분류명")}),
        "promotion_allowed": False,
        "promotion_blocker": "상가업소번호 재채번 및 중분류 74→75 변경 대조 전 운영 입력 교체 금지",
    }


def parse_localdata_page(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    root = payload.get("response", payload.get("result", payload))
    if not isinstance(root, dict):
        raise SourceSyncError("LOCALDATA 응답 루트가 객체가 아닙니다")
    header = root.get("header", {})
    result_code = str(_first(header, "resultCode", "code") or "00")
    if result_code not in {"00", "0", "INFO-000"}:
        raise SourceSyncError(f"LOCALDATA API 오류 {result_code}: {_first(header, 'resultMsg', 'message')}")
    body = root.get("body", root)
    rows = _as_list(body.get("rows") if isinstance(body, dict) else None)
    rows = [row for row in rows if _first(row, "mgtNo", "mgtno", "관리번호")]
    total = _integer(_first(body, "totalCount", "totalCnt"), 0) if isinstance(body, dict) else 0
    return rows, total


def normalize_localdata_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "개방서비스ID": _first(row, "opnSvcId", "opnsvcid", "개방서비스ID"),
        "개방서비스명": _first(row, "opnSvcNm", "opnsvcnm", "개방서비스명"),
        "개방자치단체코드": _first(row, "opnSfTeamCode", "opnsfteamcode", "개방자치단체코드"),
        "관리번호": _first(row, "mgtNo", "mgtno", "관리번호"),
        "사업장명": _first(row, "bplcNm", "bplcnm", "사업장명"),
        "지번주소": _first(row, "siteWhlAddr", "sitewhladdr", "소재지전체주소", "지번주소"),
        "도로명주소": _first(row, "rdnWhlAddr", "rdnwhladdr", "도로명전체주소", "도로명주소"),
        "인허가일자": _first(row, "apvPermYmd", "apvpermymd", "인허가일자"),
        "폐업일자": _first(row, "dcbYmd", "dcbymd", "폐업일자"),
        "영업상태명": _first(row, "trdStateNm", "trdstatenm", "영업상태명"),
        "데이터갱신구분": _first(row, "updateGbn", "updategbn", "데이터갱신구분"),
        "데이터갱신일자": _first(row, "updateDt", "updatedt", "데이터갱신일자"),
    }


def validate_localdata(records: list[dict[str, Any]]) -> dict[str, Any]:
    usable = sum(bool(row.get("관리번호") and row.get("인허가일자")) for row in records)
    completeness = usable / len(records) if records else 1.0
    if records and completeness < 0.80:
        raise SourceSyncError(f"LOCALDATA 관리번호·인허가일자 완전성 {completeness:.1%} < 80%")
    return {
        "key_and_permit_date_completeness": round(completeness, 6),
        "unique_business_keys": len({
            (row.get("개방서비스ID"), row.get("개방자치단체코드"), row.get("관리번호"))
            for row in records
        }),
        "promotion_allowed": False,
        "promotion_blocker": "기존 12종 전체분과 복합키 upsert 대조 전 운영 입력 교체 금지",
    }


def parse_gyeonggi_page(payload: Mapping[str, Any], dataset_id: str) -> tuple[list[dict[str, Any]], int]:
    blocks = payload.get(dataset_id)
    if not isinstance(blocks, list):
        raise SourceSyncError(f"경기데이터드림 응답에 {dataset_id} 배열이 없습니다")
    total = 0
    rows: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        head = block.get("head")
        if isinstance(head, list):
            for item in head:
                if not isinstance(item, dict):
                    continue
                total = max(total, _integer(item.get("list_total_count")))
                result = item.get("RESULT")
                if isinstance(result, dict) and result.get("CODE") not in {None, "INFO-000"}:
                    raise SourceSyncError(
                        f"경기데이터드림 오류 {result.get('CODE')}: {result.get('MESSAGE', '')}"
                    )
        rows.extend(_as_list(block.get("row")))
    return rows, total


def validate_gyeonggi_flow(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise SourceSyncError("경기데이터드림 유동인구 API가 0건을 반환했습니다")
    area_codes = {
        str(_first(row, "ADMDONG_CD", "행정동코드"))
        for row in records
        if _first(row, "ADMDONG_CD", "행정동코드")
    }
    return {
        "area_code_count": len(area_codes),
        "promotion_allowed": False,
        "promotion_blocker": "기존 floating_pop_hwaseong.csv와 월·행정동 커버리지 대조 전 교체 금지",
    }


def _quarter_code(period: Any) -> int | None:
    digits = re.sub(r"\D", "", str(period or ""))
    if len(digits) < 6:
        return None
    year, month = int(digits[:4]), int(digits[4:6])
    if month not in {3, 6, 9, 12}:
        return None
    return year * 10 + month // 3


def _kosis_area_name(row: Mapping[str, Any]) -> str | None:
    candidates = [
        str(row[key]).strip()
        for key in sorted(row)
        if re.fullmatch(r"C\d+_NM", key) and row.get(key)
    ]
    matches = [name for name in candidates if re.search(r"(읍|면|동)$", name)]
    return matches[-1] if matches else None


def normalize_kosis_population(payload: Any) -> list[dict[str, Any]]:
    rows = _as_list(payload)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        area_name = _kosis_area_name(row)
        quarter_code = _quarter_code(_first(row, "PRD_DE", "수록시점"))
        value = _first(row, "DT", "수치")
        if not area_name or quarter_code is None or value in (None, ""):
            continue
        try:
            population = int(float(str(value).replace(",", "")))
        except ValueError:
            continue
        normalized.append({
            "행정동명": area_name,
            "기준_년분기_코드": quarter_code,
            "총인구수": population,
            "원본수록시점": _first(row, "PRD_DE", "수록시점"),
            "원본항목명": _first(row, "ITM_NM", "항목명"),
        })
    return normalized


def validate_kosis_population(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise SourceSyncError(
            "KOSIS 응답에서 분기말(03·06·09·12월) 읍면동 등록인구를 만들지 못했습니다"
        )
    duplicates = len(records) - len({(row["행정동명"], row["기준_년분기_코드"]) for row in records})
    if duplicates:
        raise SourceSyncError(f"KOSIS 읍면동×분기 중복 {duplicates}건이 있습니다")
    return {
        "area_count": len({row["행정동명"] for row in records}),
        "quarter_count": len({row["기준_년분기_코드"] for row in records}),
        "promotion_allowed": False,
        "promotion_blocker": "기존 인구 시계열과 행정구역 개편 구간 대조 전 DB 적재 금지",
    }


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _csv_text(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    fieldnames: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return "\ufeff" + buffer.getvalue()


def write_snapshot(
    source: str,
    records: list[dict[str, Any]],
    *,
    raw_records: list[dict[str, Any]] | None = None,
    request_metadata: Mapping[str, Any],
    validation: Mapping[str, Any],
    now: datetime | None = None,
    staging_root: Path | None = None,
) -> Path:
    """검증된 응답을 버전 폴더에 원자적으로 저장하고 latest 포인터를 갱신한다."""
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    root = staging_root or _staging_root()
    snapshot_dir = root / source / stamp
    if snapshot_dir.exists():
        raise SourceSyncError(f"같은 시각의 스냅샷이 이미 있습니다: {snapshot_dir}")
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    jsonl = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records)
    csv_content = _csv_text(records)
    _atomic_write_text(snapshot_dir / "records.jsonl", jsonl)
    _atomic_write_text(snapshot_dir / "records.csv", csv_content)

    raw_jsonl: str | None = None
    if raw_records is not None:
        raw_jsonl = "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in raw_records
        )
        _atomic_write_text(snapshot_dir / "raw_records.jsonl", raw_jsonl)

    digest = hashlib.sha256(jsonl.encode("utf-8")).hexdigest()
    manifest = {
        "source": source,
        "created_at_utc": timestamp.isoformat(),
        "record_count": len(records),
        "records_sha256": digest,
        "raw_record_count": len(raw_records) if raw_records is not None else None,
        "raw_records_sha256": (
            hashlib.sha256(raw_jsonl.encode("utf-8")).hexdigest()
            if raw_jsonl is not None
            else None
        ),
        "request": _redact_mapping(request_metadata),
        "validation": dict(validation),
        "files": {
            "jsonl": "records.jsonl",
            "csv": "records.csv",
            **({"raw_jsonl": "raw_records.jsonl"} if raw_records is not None else {}),
        },
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(snapshot_dir / "manifest.json", manifest_text)
    latest = {
        "snapshot": stamp,
        "manifest_sha256": hashlib.sha256(manifest_text.encode("utf-8")).hexdigest(),
    }
    _atomic_write_text(root / source / "latest.json", json.dumps(latest, indent=2) + "\n")
    return snapshot_dir


def _collect_pages(
    fetch_page: Callable[[int], tuple[list[dict[str, Any]], int]],
    *,
    page_size: int,
    max_pages: int = 10_000,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    previous_fingerprint: str | None = None
    for page in range(1, max_pages + 1):
        rows, total = fetch_page(page)
        fingerprint = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        if rows and fingerprint == previous_fingerprint:
            raise SourceSyncError(f"페이지 {page}가 직전 페이지와 동일합니다. 페이지네이션을 확인하세요")
        previous_fingerprint = fingerprint
        collected.extend(rows)
        if not rows or (total > 0 and len(collected) >= total) or len(rows) < page_size:
            return collected
    raise SourceSyncError(f"페이지 상한 {max_pages}에 도달했습니다")


def sync_sbiz(client: JsonHttpClient | None = None) -> Path:
    service_key = _require_env("PUBLIC_DATA_SERVICE_KEY")
    endpoint = os.getenv("SBIZ_API_URL", SBIZ_DEFAULT_URL).strip()
    page_size = max(1, min(_integer(os.getenv("SBIZ_PAGE_SIZE"), 1000), 1000))
    http = client or JsonHttpClient()

    def fetch(page: int) -> tuple[list[dict[str, Any]], int]:
        payload = http.get(endpoint, {
            "serviceKey": service_key,
            "divId": os.getenv("SBIZ_DIV_ID", "signguCd"),
            "key": os.getenv("SBIZ_REGION_KEY", "41590"),
            "type": "json",
            "numOfRows": page_size,
            "pageNo": page,
        })
        return parse_sbiz_page(payload)

    raw_records = _collect_pages(fetch, page_size=page_size)
    records = [normalize_sbiz_record(row) for row in raw_records]
    validation = validate_sbiz(records)
    return write_snapshot(
        "sbiz",
        records,
        raw_records=raw_records,
        request_metadata={"endpoint": endpoint, "region": "41590", "page_size": page_size},
        validation=validation,
    )


def _validate_yyyymmdd(value: str, label: str) -> str:
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise SourceSyncError(f"{label}은 YYYYMMDD 형식이어야 합니다: {value}") from exc
    return value


def sync_localdata(
    start: str | None = None,
    end: str | None = None,
    client: JsonHttpClient | None = None,
) -> Path:
    auth_key = _require_env("LOCALDATA_AUTH_KEY")
    available_end = date.today() - timedelta(days=2)
    end_value = _validate_yyyymmdd(end or available_end.strftime("%Y%m%d"), "--end")
    start_value = _validate_yyyymmdd(
        start or (available_end - timedelta(days=6)).strftime("%Y%m%d"), "--start"
    )
    if start_value > end_value:
        raise SourceSyncError("--start는 --end보다 늦을 수 없습니다")
    start_date = datetime.strptime(start_value, "%Y%m%d").date()
    end_date = datetime.strptime(end_value, "%Y%m%d").date()
    if (end_date - start_date).days > 40:
        raise SourceSyncError("LOCALDATA 변동분 조회 기간은 40일 이내로 지정하세요")

    endpoint = os.getenv("LOCALDATA_API_URL", LOCALDATA_DEFAULT_URL).strip()
    page_size = max(1, min(_integer(os.getenv("LOCALDATA_PAGE_SIZE"), 1000), 1000))
    local_code = os.getenv("LOCALDATA_LOCAL_CODE", "5530000").strip()
    http = client or JsonHttpClient()

    def fetch(page: int) -> tuple[list[dict[str, Any]], int]:
        payload = http.get(endpoint, {
            "authKey": auth_key,
            "localCode": local_code,
            "lastModTsBgn": start_value,
            "lastModTsEnd": end_value,
            "pageIndex": page,
            "pageSize": page_size,
            "resultType": "json",
        })
        return parse_localdata_page(payload)

    raw_records = _collect_pages(fetch, page_size=page_size)
    records = [normalize_localdata_record(row) for row in raw_records]
    validation = validate_localdata(records)
    return write_snapshot(
        "localdata",
        records,
        raw_records=raw_records,
        request_metadata={
            "endpoint": endpoint,
            "local_code": local_code,
            "window_start": start_value,
            "window_end": end_value,
            "page_size": page_size,
        },
        validation=validation,
    )


def sync_gyeonggi_flow(client: JsonHttpClient | None = None) -> Path:
    api_key = _require_env("GG_OPENAPI_KEY")
    dataset_id = os.getenv("GG_FLOW_DATASET_ID", "TB25BPTPOPDAYDONGM").strip()
    base_url = os.getenv("GG_OPENAPI_BASE_URL", GYEONGGI_DEFAULT_BASE_URL).rstrip("/")
    endpoint = f"{base_url}/{dataset_id}"
    page_size = max(1, min(_integer(os.getenv("GG_PAGE_SIZE"), 1000), 1000))
    extra_params = _json_env("GG_FLOW_EXTRA_PARAMS_JSON")
    http = client or JsonHttpClient()

    def fetch(page: int) -> tuple[list[dict[str, Any]], int]:
        params = {
            **extra_params,
            "KEY": api_key,
            "Type": "json",
            "pIndex": page,
            "pSize": page_size,
        }
        payload = http.get(endpoint, params)
        return parse_gyeonggi_page(payload, dataset_id)

    records = _collect_pages(fetch, page_size=page_size)
    validation = validate_gyeonggi_flow(records)
    return write_snapshot(
        "gyeonggi-flow",
        records,
        request_metadata={
            "endpoint": endpoint,
            "dataset_id": dataset_id,
            "page_size": page_size,
            "filters": extra_params,
        },
        validation=validation,
    )


def sync_kosis_population(client: JsonHttpClient | None = None) -> Path:
    api_key = _require_env("KOSIS_API_KEY")
    extra_params = _json_env("KOSIS_POPULATION_PARAMS_JSON")
    if not extra_params:
        raise MissingConfiguration(
            "KOSIS_POPULATION_PARAMS_JSON이 비어 있습니다. KOSIS URL 생성기에서 apiKey를 제외한 "
            "통계표·행정구역·항목 파라미터를 JSON으로 설정하세요."
        )
    endpoint = os.getenv("KOSIS_API_URL", KOSIS_DEFAULT_URL).strip()
    http = client or JsonHttpClient()
    payload = http.get(endpoint, {
        **extra_params,
        "method": "getList",
        "apiKey": api_key,
        "format": "json",
        "jsonVD": "Y",
    })
    records = normalize_kosis_population(payload)
    validation = validate_kosis_population(records)
    return write_snapshot(
        "kosis-population",
        records,
        raw_records=_as_list(payload),
        request_metadata={"endpoint": endpoint, "params": extra_params},
        validation=validation,
    )


def source_readiness(env: Mapping[str, str] | None = None) -> list[SourceReadiness]:
    values = os.environ if env is None else env

    def missing(*names: str) -> tuple[str, ...]:
        missing_names = []
        for name in names:
            value = str(values.get(name, "") or "").strip()
            if not value or (name.endswith("_PARAMS_JSON") and value == "{}"):
                missing_names.append(name)
        return tuple(missing_names)

    sbiz_missing = missing("PUBLIC_DATA_SERVICE_KEY")
    local_missing = missing("LOCALDATA_AUTH_KEY")
    gg_missing = missing("GG_OPENAPI_KEY")
    kosis_missing = missing("KOSIS_API_KEY", "KOSIS_POPULATION_PARAMS_JSON")
    return [
        SourceReadiness(
            "sbiz", not sbiz_missing, sbiz_missing,
            "스테이징 전용: 업종분류·상가업소번호 대조 전 운영 승격 금지",
        ),
        SourceReadiness(
            "localdata", not local_missing, local_missing,
            "변동분 전용: 기존 전체분 CSV는 초기 기준선으로 유지",
        ),
        SourceReadiness(
            "gyeonggi-flow", not gg_missing, gg_missing,
            "실행 호스트가 경기데이터드림 접근 정책을 통과해야 함",
        ),
        SourceReadiness(
            "kosis-population", not kosis_missing, kosis_missing,
            "KOSIS URL 생성기에서 통계표 파라미터를 먼저 확정해야 함",
        ),
    ]


def print_status(readiness: Iterable[SourceReadiness] | None = None) -> None:
    rows = list(readiness or source_readiness())
    print("공공데이터 API 준비 상태")
    for row in rows:
        state = "준비됨" if row.ready else "키/설정 필요"
        missing = f" ({', '.join(row.missing)})" if row.missing else ""
        print(f"- {row.source}: {state}{missing}")
        print(f"  {row.note}")
    print(f"스테이징 위치: {_staging_root()}")


SYNC_FUNCTIONS: dict[str, Callable[[], Path]] = {
    "sbiz": sync_sbiz,
    "gyeonggi-flow": sync_gyeonggi_flow,
    "kosis-population": sync_kosis_population,
}


def sync_ready_sources() -> list[Path]:
    readiness = {item.source: item for item in source_readiness()}
    outputs: list[Path] = []
    for source in ("sbiz", "localdata", "gyeonggi-flow", "kosis-population"):
        state = readiness[source]
        if not state.ready:
            print(f"[건너뜀] {source}: {', '.join(state.missing)}")
            continue
        print(f"[수집] {source}")
        output = sync_localdata() if source == "localdata" else SYNC_FUNCTIONS[source]()
        outputs.append(output)
        print(f"  저장: {output}")
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="공공데이터 API 스테이징 수집기")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="API 키와 필수 설정 준비 상태 확인")
    sub.add_parser("sbiz", help="소진공 화성시 상가정보 스냅샷 수집")
    local = sub.add_parser("localdata", help="LOCALDATA 화성시 인허가 변동분 수집")
    local.add_argument("--start", help="데이터갱신일 시작(YYYYMMDD), 기본 D-8")
    local.add_argument("--end", help="데이터갱신일 끝(YYYYMMDD), 기본 D-2")
    sub.add_parser("gyeonggi-flow", help="경기데이터드림 유동인구 수집")
    sub.add_parser("kosis-population", help="KOSIS 읍면동 등록인구 수집")
    sub.add_parser("sync-ready", help="키와 설정이 준비된 원천만 순서대로 수집")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            print_status()
            return 0
        if args.command == "sync-ready":
            outputs = sync_ready_sources()
            print(f"완료: {len(outputs)}개 원천")
            return 0
        if args.command == "localdata":
            output = sync_localdata(args.start, args.end)
        else:
            output = SYNC_FUNCTIONS[args.command]()
        print(f"저장: {output}")
        return 0
    except SourceSyncError as exc:
        print(f"실패: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
