import calendar
from datetime import date, datetime, timedelta, timezone
import io
import json
from urllib.error import HTTPError

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai.import_weekday_flow import DAYS, validate_month
from backend.models import AdminArea, AreaWeekdayFlow
from backend.routers.exploration import weekday_flow
from backend.schemas import SearchTrendResponse, WeekdayFlowResponse
from backend.services import search_interest as search
from backend.services.area_neighbors import area_neighbors, build_neighbors


def source_fixture():
    values = [100, 110, 120, 130, 140, 200, 210]
    total = sum(values[date(2025, 6, d).weekday()] for d in range(1, calendar.monthrange(2025, 6)[1] + 1))
    return pd.DataFrame({"ADMDONG_CD": ["x"] * 8, "WDAY_CD": [*DAYS, "TOT"],
                         "DYNMC_POPLTN_CNT": [*values, total]})


def test_flow_validation_and_api_preserve_weekday_daily_averages():
    rows = validate_month(source_fixture(), {"x": 1}, "202506")
    assert sum(row["relative_index"] for row in rows) / 7 == pytest.approx(100)
    engine = create_engine("sqlite://")
    AdminArea.__table__.create(engine)
    AreaWeekdayFlow.__table__.create(engine)
    with Session(engine) as db:
        db.add(AdminArea(id=1, area_code="test", area_name="테스트동", area_type="동"))
        db.add_all(AreaWeekdayFlow(**row, source_sha256="0" * 64) for row in rows)
        db.commit()
        result = WeekdayFlowResponse.model_validate(weekday_flow(area_id=1, db=db))
        assert result.status == "ready"
        assert result.weekend_vs_weekday_pct == pytest.approx(70.8)
        # 최신 월에 한 요일이 빠지면 과거의 완결 월로 몰래 대체하지 않는다.
        db.add(AreaWeekdayFlow(area_id=1, month="2025-07", weekday=0, relative_index=100, source_sha256="1" * 64))
        db.commit()
        result = weekday_flow(area_id=1, db=db)
        assert result["status"] == "no_data"
        assert result["month"] == "2025-07"


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "unit", "nan", "mapping"])
def test_flow_rejects_incomplete_or_inconsistent_source(mutation):
    frame = source_fixture()
    mapping = {"x": 1}
    if mutation == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif mutation == "missing":
        frame = frame.iloc[:-2]
    elif mutation == "unit":
        frame.loc[7, "DYNMC_POPLTN_CNT"] *= 10
    elif mutation == "nan":
        frame.loc[0, "DYNMC_POPLTN_CNT"] = float("nan")
    else:
        mapping = {"unknown": 1}
    with pytest.raises(ValueError):
        validate_month(frame, mapping, "202506")


def test_boundary_neighbors_exclude_corner_contact_and_are_symmetric():
    def square(name, x, y):
        return {"properties": {"dong_name": name}, "geometry": {"type": "Polygon", "coordinates": [
            [[x, y], [x+1, y], [x+1, y+1], [x, y+1], [x, y]]]}}
    graph = build_neighbors([square("a", 0, 0), square("b", 1, 0), square("c", 1, 1)])
    assert graph["a"] == {"b"}
    real = area_neighbors()
    assert len(real) == 29
    assert all(name not in others and all(name in real[other] for other in others) for name, others in real.items())


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    search._cache.clear()
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)


def test_search_missing_key_unsupported_and_completed_calendar_range():
    assert search.complete_month_range(date(2026, 1, 3)) == (date(2025, 1, 1), date(2025, 12, 31))
    assert search.complete_month_range(date(2024, 3, 1))[1] == date(2024, 2, 29)
    result = SearchTrendResponse.model_validate(search.search_interest(1, "비알코올 ", today=date(2026, 9, 2)))
    assert result.status == "not_configured"
    assert result.keywords == ["카페", "커피숍"]
    assert search.search_interest(2, "기타 전문 과학")["status"] == "unsupported"


def test_search_cache_and_upstream_auth_failure_never_become_user_auth_failure(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    calls = []
    def upstream(request, timeout):
        body = json.loads(request.data)
        calls.append(body)
        assert set(body) == {"startDate", "endDate", "timeUnit", "keywordGroups"}
        assert timeout == 8
        return io.BytesIO(json.dumps({"results": [{"data": [{"period": "2026-08-01", "ratio": 100}]}]}).encode())
    monkeypatch.setattr(search, "urlopen", upstream)
    first = search.search_interest(1, "한식", today=date(2026, 9, 2))
    assert first["status"] == "ready"
    assert search.search_interest(1, "한식", today=date(2026, 9, 2)) == first
    assert len(calls) == 1
    def denied(*args, **kwargs):
        raise HTTPError("test", 403, "denied", {}, None)
    monkeypatch.setattr(search, "urlopen", denied)
    next(iter(search._cache.values()))["expires"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    stale = search.search_interest(1, "한식", today=date(2026, 9, 2))
    assert stale["status"] == "stale"
    assert stale["points"] == first["points"]
    assert search.search_interest(2, "중식", today=date(2026, 9, 2))["status"] == "unavailable"


@pytest.mark.parametrize("data,expected", [([], "no_data"), ([{"period": "2026-08-01", "ratio": 0}], "no_data"),
    ([{"period": "2026-09-01", "ratio": 100}], "unavailable"), ([{"period": "2026-08-01", "ratio": 101}], "unavailable")])
def test_search_zero_empty_and_invalid_series(monkeypatch, data, expected):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(search, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps({"results": [{"data": data}]}).encode()))
    assert search.search_interest(1, "한식", today=date(2026, 9, 2))["status"] == expected
