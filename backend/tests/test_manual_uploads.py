import csv
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.auth.dependencies import get_current_official
from backend.routers.data_management import router
from backend.services.manual_uploads import (
    ManualUploadError,
    latest_upload,
    list_uploads,
    management_payload,
    safe_filename,
    store_validated_upload,
    validate_card_code_xlsx,
    validate_card_sales_csv,
)


def _write_card_sales(path: Path, *, missing_column: str | None = None) -> None:
    columns = ["STD_YM", "ADMDONG_CD", "MDCLASS_INDUTYPE_CD", "SALES_AMT"]
    if missing_column:
        columns.remove(missing_column)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index in range(1, 81):
            row = {
                "STD_YM": "202608",
                "ADMDONG_CD": "4159059000",
                "MDCLASS_INDUTYPE_CD": f"Q{index:02d}",
                "SALES_AMT": str(index * 1000),
            }
            writer.writerow({key: value for key, value in row.items() if key in columns})


def _write_card_codes(path: Path) -> None:
    rows = []
    for index in range(1, 81):
        rows.append(
            f'<row r="{index}"><c r="B{index}" t="inlineStr"><is><t>Q{index:02d}</t></is></c>'
            f'<c r="C{index}" t="inlineStr"><is><t>industry-{index}</t></is></c></row>'
        )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(rows)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def test_data_management_router_requires_official_role():
    assert any(dependency.dependency is get_current_official for dependency in router.dependencies)


def test_card_sales_validation_reports_coverage():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "card_sales_hwaseong.csv"
        _write_card_sales(path)

        result = validate_card_sales_csv(path)

    assert result["row_count"] == 80
    assert result["month_start"] == "202608"
    assert result["month_end"] == "202608"
    assert result["industry_code_count"] == 80


def test_card_sales_validation_rejects_missing_columns():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "card_sales_hwaseong.csv"
        _write_card_sales(path, missing_column="SALES_AMT")

        with pytest.raises(ManualUploadError, match="SALES_AMT"):
            validate_card_sales_csv(path)


def test_card_code_validation_reads_b_and_c_columns():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "업종_중분류코드.xlsx"
        _write_card_codes(path)

        result = validate_card_code_xlsx(path)

    assert result["industry_code_count"] == 80
    assert result["duplicate_code_count"] == 0


@pytest.mark.parametrize("filename", ["../card_sales_hwaseong.csv", "folder/file.csv", "bad.txt"])
def test_safe_filename_rejects_paths_and_wrong_extensions(filename):
    with pytest.raises(ManualUploadError):
        safe_filename("card_sales", filename)


def test_store_upload_creates_versioned_manifest_and_latest_pointer():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        temp_root = root / ".tmp"
        temp_root.mkdir()
        source = temp_root / "incoming"
        _write_card_sales(source)

        uploaded = store_validated_upload(
            "card_sales",
            "card_sales_hwaseong.csv",
            source,
            uploaded_by="official1",
            root=root,
            now=datetime(2026, 9, 1, 12, 30, 15, 123456, tzinfo=timezone.utc),
        )

        latest = latest_upload("card_sales", root)
        history = list_uploads(root)
        payload = management_payload(root)

    assert uploaded["status"] == "validated"
    assert uploaded["reflection_status"] == "pending"
    assert uploaded["uploaded_by"] == "official1"
    assert latest == uploaded
    assert history == [uploaded]
    assert payload["datasets"][0]["latest_upload"] == uploaded
    assert len(uploaded["sha256"]) == 64
