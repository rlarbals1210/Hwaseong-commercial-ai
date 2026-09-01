"""공무원 화면에서 받은 수동 데이터 파일을 검증하고 버전별로 보관한다.

업로드 완료는 운영 데이터 반영이 아니다. 현재 파이프라인이 읽는 파일을 덮어쓰지
않고 ``data/raw/manual_uploads``에 스테이징한다. 이후 별도 검토를 통과한 파일만
재학습·DB 적재 절차로 옮긴다.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UPLOAD_ROOT = PROJECT_ROOT / "data" / "raw" / "manual_uploads"
DEFAULT_MAX_UPLOAD_MB = 100
SNAPSHOT_PATTERN = re.compile(r"\d{8}T\d{12}Z")


class ManualUploadError(ValueError):
    """업로드 요청 또는 파일 검증 실패."""


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    title: str
    description: str
    expected_filename: str
    accepted_extensions: tuple[str, ...]
    required_columns: tuple[str, ...]


DATASET_SPECS: dict[str, DatasetSpec] = {
    "card_sales": DatasetSpec(
        key="card_sales",
        title="카드매출 월별 데이터",
        description="행정동×카드 업종별 월 매출액 원본",
        expected_filename="card_sales_hwaseong.csv",
        accepted_extensions=(".csv",),
        required_columns=("STD_YM", "ADMDONG_CD", "MDCLASS_INDUTYPE_CD", "SALES_AMT"),
    ),
    "card_industry_codes": DatasetSpec(
        key="card_industry_codes",
        title="카드 업종 코드표",
        description="카드 중분류 코드와 업종명 대조표",
        expected_filename="업종_중분류코드.xlsx",
        accepted_extensions=(".xlsx",),
        required_columns=("B열: 업종 중분류 코드", "C열: 업종명"),
    ),
}


def upload_root() -> Path:
    configured = os.getenv("MANUAL_UPLOAD_DIR", "").strip()
    if not configured:
        return DEFAULT_UPLOAD_ROOT
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def max_upload_bytes() -> int:
    raw = os.getenv("MANUAL_UPLOAD_MAX_MB", str(DEFAULT_MAX_UPLOAD_MB)).strip()
    try:
        size_mb = int(raw)
    except ValueError as exc:
        raise RuntimeError("MANUAL_UPLOAD_MAX_MB는 정수여야 합니다") from exc
    if not 1 <= size_mb <= 500:
        raise RuntimeError("MANUAL_UPLOAD_MAX_MB는 1~500 범위여야 합니다")
    return size_mb * 1024 * 1024


def get_dataset_spec(dataset_type: str) -> DatasetSpec:
    spec = DATASET_SPECS.get(dataset_type)
    if spec is None:
        raise ManualUploadError("지원하지 않는 데이터 유형입니다")
    return spec


def safe_filename(dataset_type: str, filename: str) -> str:
    spec = get_dataset_spec(dataset_type)
    normalized = unicodedata.normalize("NFC", filename).strip()
    if not normalized or len(normalized) > 255:
        raise ManualUploadError("파일명이 비어 있거나 너무 깁니다")
    if any(token in normalized for token in ("/", "\\", "\x00")):
        raise ManualUploadError("파일명에 경로 문자를 사용할 수 없습니다")
    suffix = Path(normalized).suffix.lower()
    if suffix not in spec.accepted_extensions:
        allowed = ", ".join(spec.accepted_extensions)
        raise ManualUploadError(f"{spec.title}은 {allowed} 파일만 업로드할 수 있습니다")
    cleaned = re.sub(r"[^0-9A-Za-zㄱ-ㆎ가-힣._()\- ]", "_", normalized)
    if cleaned in {".", ".."}:
        raise ManualUploadError("사용할 수 없는 파일명입니다")
    return cleaned


def _csv_encoding(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                handle.read(64 * 1024)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ManualUploadError("CSV 문자 인코딩을 확인할 수 없습니다")


def _valid_month(value: str) -> bool:
    if not re.fullmatch(r"\d{6}", value):
        return False
    return 1 <= int(value[4:]) <= 12


def validate_card_sales_csv(path: Path) -> dict[str, Any]:
    encoding = _csv_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        columns = [str(column or "").strip() for column in (reader.fieldnames or [])]
        required = set(DATASET_SPECS["card_sales"].required_columns)
        missing = sorted(required - set(columns))
        if missing:
            raise ManualUploadError(f"필수 컬럼이 없습니다: {', '.join(missing)}")

        row_count = 0
        invalid_rows = 0
        months: set[str] = set()
        areas: set[str] = set()
        codes: set[str] = set()
        for row in reader:
            row_count += 1
            month = str(row.get("STD_YM") or "").strip()
            area = str(row.get("ADMDONG_CD") or "").strip()
            code = str(row.get("MDCLASS_INDUTYPE_CD") or "").strip()
            amount = str(row.get("SALES_AMT") or "").strip().replace(",", "")
            valid_amount = True
            try:
                float(amount)
            except ValueError:
                valid_amount = False
            if not (_valid_month(month) and area and code and valid_amount):
                invalid_rows += 1
                continue
            months.add(month)
            areas.add(area)
            codes.add(code)

    if row_count == 0:
        raise ManualUploadError("카드매출 CSV에 데이터 행이 없습니다")
    if invalid_rows / row_count > 0.01:
        raise ManualUploadError(
            f"필수 값 형식이 올바르지 않은 행이 {invalid_rows:,}건입니다 "
            f"({invalid_rows / row_count:.1%})"
        )
    if len(codes) < 80:
        raise ManualUploadError(f"카드 업종 코드가 {len(codes)}개로 80개보다 적습니다")

    return {
        "encoding": encoding,
        "row_count": row_count,
        "invalid_row_count": invalid_rows,
        "month_start": min(months),
        "month_end": max(months),
        "month_count": len(months),
        "area_code_count": len(areas),
        "industry_code_count": len(codes),
    }


def _xlsx_cell_text(cell: ET.Element, shared: list[str], namespace: dict[str, str]) -> str:
    value = cell.find("x:v", namespace)
    if value is None or value.text is None:
        inline = cell.find("x:is/x:t", namespace)
        return inline.text.strip() if inline is not None and inline.text else ""
    if cell.attrib.get("t") == "s":
        try:
            return shared[int(value.text)].strip()
        except (IndexError, ValueError):
            return ""
    return value.text.strip()


def validate_card_code_xlsx(path: Path) -> dict[str, Any]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if any(info.flag_bits & 0x1 for info in infos):
                raise ManualUploadError("암호화된 Excel 파일은 업로드할 수 없습니다")
            if sum(info.file_size for info in infos) > 50 * 1024 * 1024:
                raise ManualUploadError("Excel 내부 풀린 크기가 50MB를 넘습니다")
            if "xl/worksheets/sheet1.xml" not in archive.namelist():
                raise ManualUploadError("Excel의 첫 번째 시트를 찾을 수 없습니다")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in shared_root.findall("x:si", namespace):
                    shared.append("".join(node.text or "" for node in item.findall(".//x:t", namespace)))
            sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except zipfile.BadZipFile as exc:
        raise ManualUploadError("올바른 XLSX 파일이 아닙니다") from exc
    except ET.ParseError as exc:
        raise ManualUploadError("Excel 내부 시트를 읽을 수 없습니다") from exc

    rows: dict[int, dict[str, str]] = {}
    for cell in sheet.findall(".//x:c", namespace):
        match = re.fullmatch(r"([A-Z]+)(\d+)", cell.attrib.get("r", ""))
        if not match:
            continue
        column, row_number = match.group(1), int(match.group(2))
        rows.setdefault(row_number, {})[column] = _xlsx_cell_text(cell, shared, namespace)

    code_rows = [
        values
        for values in rows.values()
        if re.fullmatch(r"[A-Z]\d{2}", values.get("B", "")) and values.get("C", "").strip()
    ]
    unique_codes = {values["B"] for values in code_rows}
    if len(unique_codes) < 80:
        raise ManualUploadError(
            f"B·C열에서 확인한 유효 코드가 {len(unique_codes)}개로 80개보다 적습니다"
        )
    return {
        "sheet": "sheet1",
        "industry_code_count": len(unique_codes),
        "duplicate_code_count": len(code_rows) - len(unique_codes),
    }


def validate_upload(dataset_type: str, path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise ManualUploadError("파일이 비어 있습니다")
    if dataset_type == "card_sales":
        return validate_card_sales_csv(path)
    if dataset_type == "card_industry_codes":
        return validate_card_code_xlsx(path)
    raise ManualUploadError("지원하지 않는 데이터 유형입니다")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def store_validated_upload(
    dataset_type: str,
    filename: str,
    source_path: Path,
    *,
    uploaded_by: str,
    root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    spec = get_dataset_spec(dataset_type)
    stored_filename = safe_filename(dataset_type, filename)
    size_bytes = source_path.stat().st_size
    if size_bytes > max_upload_bytes():
        raise ManualUploadError(
            f"파일 크기가 {max_upload_bytes() // (1024 * 1024)}MB 제한을 넘습니다"
        )
    validation = validate_upload(dataset_type, source_path)
    digest = _sha256(source_path)
    created = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = created.strftime("%Y%m%dT%H%M%S%fZ")
    base = root or upload_root()
    snapshot_dir = base / dataset_type / stamp
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    destination = snapshot_dir / stored_filename
    os.replace(source_path, destination)

    manifest: dict[str, Any] = {
        "upload_id": f"{dataset_type}:{stamp}",
        "dataset_type": dataset_type,
        "dataset_title": spec.title,
        "status": "validated",
        "reflection_status": "pending",
        "uploaded_at_utc": created.isoformat(),
        "uploaded_by": uploaded_by,
        "original_filename": filename,
        "stored_filename": stored_filename,
        "size_bytes": size_bytes,
        "sha256": digest,
        "validation": validation,
    }
    _atomic_json(snapshot_dir / "manifest.json", manifest)
    _atomic_json(base / dataset_type / "latest.json", {"snapshot": stamp})
    return manifest


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def latest_upload(dataset_type: str, root: Path | None = None) -> dict[str, Any] | None:
    get_dataset_spec(dataset_type)
    base = root or upload_root()
    pointer = _read_manifest(base / dataset_type / "latest.json")
    snapshot = str((pointer or {}).get("snapshot", ""))
    if not SNAPSHOT_PATTERN.fullmatch(snapshot):
        return None
    return _read_manifest(base / dataset_type / snapshot / "manifest.json")


def list_uploads(root: Path | None = None, limit: int = 20) -> list[dict[str, Any]]:
    base = root or upload_root()
    uploads: list[dict[str, Any]] = []
    for dataset_type in DATASET_SPECS:
        dataset_root = base / dataset_type
        if not dataset_root.exists():
            continue
        for manifest_path in dataset_root.glob("*/manifest.json"):
            if not SNAPSHOT_PATTERN.fullmatch(manifest_path.parent.name):
                continue
            manifest = _read_manifest(manifest_path)
            if manifest:
                uploads.append(manifest)
    uploads.sort(key=lambda item: str(item.get("uploaded_at_utc", "")), reverse=True)
    return uploads[:limit]


def management_payload(root: Path | None = None) -> dict[str, Any]:
    base = root or upload_root()
    max_size_mb = max_upload_bytes() // (1024 * 1024)
    datasets = [
        {
            "dataset_type": spec.key,
            "title": spec.title,
            "description": spec.description,
            "expected_filename": spec.expected_filename,
            "accepted_extensions": list(spec.accepted_extensions),
            "required_columns": list(spec.required_columns),
            "max_size_mb": max_size_mb,
            "latest_upload": latest_upload(spec.key, base),
        }
        for spec in DATASET_SPECS.values()
    ]
    return {
        "datasets": datasets,
        "uploads": list_uploads(base),
        "notice": "검증 완료 파일은 반영 대기 상태로 보관되며 모델·DB를 자동 변경하지 않습니다.",
    }
