from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai.sync_public_data import (
    SourceSyncError,
    _collect_pages,
    normalize_kosis_population,
    normalize_localdata_record,
    normalize_sbiz_record,
    parse_gyeonggi_page,
    parse_localdata_page,
    parse_sbiz_page,
    redact_url,
    source_readiness,
    validate_kosis_population,
    write_snapshot,
)


class PublicDataSyncTest(unittest.TestCase):
    def test_redact_url_hides_all_key_values(self):
        safe = redact_url(
            "https://example.test/api?serviceKey=secret-a&authKey=secret-b&normal=value"
        )

        self.assertNotIn("secret-a", safe)
        self.assertNotIn("secret-b", safe)
        self.assertIn("normal=value", safe)

    def test_parse_and_normalize_sbiz_page(self):
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
                "body": {
                    "totalCount": 1,
                    "items": [{
                        "bizesId": "S1",
                        "signguCd": "41590",
                        "adongCd": "4159059000",
                        "adongNm": "봉담읍",
                        "indsLclsNm": "음식",
                        "indsMclsNm": "한식",
                        "indsSclsNm": "한식 일반 음식점업",
                        "lnoAdr": "경기도 화성시 봉담읍 1",
                        "lon": 127.0,
                        "lat": 37.0,
                    }],
                },
            }
        }

        rows, total = parse_sbiz_page(payload)
        normalized = normalize_sbiz_record(rows[0])

        self.assertEqual(total, 1)
        self.assertEqual(normalized["상가업소번호"], "S1")
        self.assertEqual(normalized["시군구코드"], "41590")
        self.assertEqual(normalized["상권업종중분류명"], "한식")

    def test_sbiz_error_does_not_echo_service_key(self):
        with self.assertRaisesRegex(SourceSyncError, "등록되지 않은 서비스키"):
            parse_sbiz_page({
                "OpenAPI_ServiceResponse": {
                    "cmmMsgHeader": {"returnAuthMsg": "등록되지 않은 서비스키"}
                }
            })

    def test_parse_and_normalize_localdata_page(self):
        payload = {
            "body": {
                "totalCount": 1,
                "rows": [{
                    "opnSvcId": "07_24_04_P",
                    "opnSvcNm": "일반음식점",
                    "opnSfTeamCode": "5530000",
                    "mgtNo": "M1",
                    "bplcNm": "예시 사업장",
                    "siteWhlAddr": "경기도 화성시 예시로 1",
                    "apvPermYmd": "20260801",
                    "updateGbn": "I",
                }],
            }
        }

        rows, total = parse_localdata_page(payload)
        normalized = normalize_localdata_record(rows[0])

        self.assertEqual(total, 1)
        self.assertEqual(normalized["관리번호"], "M1")
        self.assertEqual(normalized["개방서비스명"], "일반음식점")
        self.assertEqual(normalized["지번주소"], "경기도 화성시 예시로 1")
        self.assertEqual(normalized["인허가일자"], "20260801")

    def test_localdata_empty_list_marker_is_not_a_record(self):
        rows, total = parse_localdata_page({"body": {"rows": [{"@class": "list"}]}})
        self.assertEqual(rows, [])
        self.assertEqual(total, 0)

    def test_parse_gyeonggi_page(self):
        payload = {
            "TB25BPTPOPDAYDONGM": [
                {"head": [
                    {"list_total_count": 1},
                    {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}},
                ]},
                {"row": [{"STD_YM": "202506", "ADMDONG_CD": "4159059000"}]},
            ]
        }

        rows, total = parse_gyeonggi_page(payload, "TB25BPTPOPDAYDONGM")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["STD_YM"], "202506")

    def test_collect_pages_rejects_repeated_page(self):
        def repeated_page(_page):
            return [{"same": True}], 10

        with self.assertRaisesRegex(SourceSyncError, "페이지네이션"):
            _collect_pages(repeated_page, page_size=1)

    def test_normalize_kosis_population_keeps_quarter_end_months_only(self):
        payload = [
            {
                "C1_NM": "경기도",
                "C2_NM": "화성시",
                "C3_NM": "봉담읍",
                "ITM_NM": "총인구수[명]",
                "PRD_DE": "2026.03",
                "DT": "100,000",
            },
            {
                "C1_NM": "경기도",
                "C2_NM": "화성시",
                "C3_NM": "봉담읍",
                "ITM_NM": "총인구수[명]",
                "PRD_DE": "2026.04",
                "DT": "100100",
            },
        ]

        records = normalize_kosis_population(payload)
        validation = validate_kosis_population(records)

        self.assertEqual(records, [{
            "행정동명": "봉담읍",
            "기준_년분기_코드": 20261,
            "총인구수": 100000,
            "원본수록시점": "2026.03",
            "원본항목명": "총인구수[명]",
        }])
        self.assertEqual(validation["area_count"], 1)

    def test_write_snapshot_redacts_request_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = write_snapshot(
                "test-source",
                [{"value": 1}],
                raw_records=[{"value": 1, "extra": "preserved"}],
                request_metadata={"serviceKey": "never-save-me", "region": "41590"},
                validation={"promotion_allowed": False},
                now=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
                staging_root=root,
            )

            manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertNotIn("never-save-me", manifest_text)
            self.assertEqual(manifest["request"]["serviceKey"], "***")
            self.assertEqual(manifest["record_count"], 1)
            self.assertEqual(manifest["raw_record_count"], 1)
            self.assertTrue((output / "raw_records.jsonl").exists())
            self.assertTrue((root / "test-source" / "latest.json").exists())

    def test_source_readiness_never_requires_secret_values_to_be_printed(self):
        rows = source_readiness({
            "PUBLIC_DATA_SERVICE_KEY": "secret",
            "LOCALDATA_AUTH_KEY": "",
            "GG_OPENAPI_KEY": "secret",
            "KOSIS_API_KEY": "secret",
            "KOSIS_POPULATION_PARAMS_JSON": "",
        })
        by_source = {row.source: row for row in rows}

        self.assertTrue(by_source["sbiz"].ready)
        self.assertEqual(by_source["localdata"].missing, ("LOCALDATA_AUTH_KEY",))
        self.assertTrue(by_source["gyeonggi-flow"].ready)
        self.assertFalse(by_source["kosis-population"].ready)
        self.assertNotIn("secret", repr(rows))


if __name__ == "__main__":
    unittest.main()
