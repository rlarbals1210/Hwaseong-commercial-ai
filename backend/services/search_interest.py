"""네이버 전국 검색 추이. 원본 행정데이터 없이 일반 검색어만 전송한다.

단일 VPS용 프로세스 메모리 캐시(최대 128개, 성공 24시간, 실패 재시도 5분).
다중 worker에서는 캐시가 분리되며 재시작 때 초기화된다.
"""
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from threading import Lock
from urllib.request import Request, urlopen

# 서비스 중분류의 일부를 대표 검색어로 연결한다. 실제 업종 분류/검색 건수와 동일하지 않다.
# 지원하지 않는 업종을 임의의 단어로 자동 변환하지 않는다.
KEYWORDS = {
    "한식": ["한식", "한식당"], "중식": ["중식", "중국집"],
    "일식": ["일식", "일식집"], "서양식": ["양식", "레스토랑"],
    "동남아시아": ["베트남 음식", "태국 음식"], "비알코올": ["카페", "커피숍"],
    "주점": ["술집", "주점"], "구내식당·뷔페": ["뷔페", "구내식당"],
    "이용·미용": ["미용실", "이발소"], "세탁": ["세탁소", "빨래방"],
    "일반 교육": ["학원", "입시학원"], "스포츠 서비스": ["헬스장", "필라테스"],
    "자동차 수리·세차": ["자동차 정비", "세차장"], "식물 소매": ["꽃집", "화원"],
    "애완동물·용품 소매": ["반려동물 용품", "애견용품"],
    "가구 소매": ["가구점", "가구 매장"], "컴퓨터 수리": ["컴퓨터 수리"],
    "사진 촬영": ["사진관", "증명사진"], "일반 숙박": ["호텔", "모텔"],
    "욕탕·신체관리": ["목욕탕", "사우나"],
}
_cache = OrderedDict()
_lock = Lock()


def complete_month_range(today=None):
    first = (today or date.today()).replace(day=1)
    return first.replace(year=first.year - 1), first - timedelta(days=1)


def _fetch(keywords, start, end):
    body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "month",
            "keywordGroups": [{"groupName": "업종 관심도", "keywords": keywords}]}
    # 구 developers.naver.com 오픈 API는 NAVER API HUB로 이관됐다. 게이트웨이 헤더·경로만
    # 다르고 요청 body와 응답 구조는 동일하다.
    request = Request("https://naverapihub.apigw.ntruss.com/search-trend/v1/search",
                      data=json.dumps(body).encode(), method="POST", headers={
                          "Content-Type": "application/json",
                          "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_CLIENT_ID"],
                          "X-NCP-APIGW-API-KEY": os.environ["NAVER_CLIENT_SECRET"],
                      })
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list) or len(payload["results"]) != 1:
        raise ValueError("Unexpected search response")
    points = []
    for item in payload["results"][0]["data"]:
        day = date.fromisoformat(item["period"])
        value = float(item["ratio"])
        if not start <= day <= end or day.day != 1 or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Invalid search period or index")
        points.append({"month": day.strftime("%Y-%m"), "index": value})
    if len({p["month"] for p in points}) != len(points):
        raise ValueError("Duplicate search period")
    return sorted(points, key=lambda p: p["month"])


def search_interest(industry_id, industry_name, today=None):
    start, end = complete_month_range(today)
    keywords = KEYWORDS.get(industry_name.strip(), [])
    base = dict(industry_id=industry_id, industry_name=industry_name, keywords=keywords,
                start_date=start.isoformat(), end_date=end.isoformat())
    if not keywords:
        return dict(base, status="unsupported", message="이 업종은 검색 트렌드를 대표할 검색어가 지정되어 있지 않아 표시하지 않습니다.")
    if not all(os.getenv(key, "").strip() for key in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")):
        return dict(base, status="not_configured", message="검색 트렌드 API 키 연결 대기 중입니다.")
    key = (tuple(keywords), start, end)
    now = datetime.now(timezone.utc)
    # 요청을 합쳐 새로고침 연타가 외부 일일 호출량을 소진하지 않게 한다.
    with _lock:
        cached = _cache.get(key)
        if cached and now < cached["expires"]:
            _cache.move_to_end(key)
            return dict(base, **cached["result"])
        try:
            points = _fetch(keywords, start, end)
            result = dict(status="ready" if points and any(p["index"] > 0 for p in points) else "no_data",
                          points=points, fetched_at=now,
                          message=f"완결된 최근 12개월 중 {len(points)}개월의 검색지수입니다.")
            ttl = timedelta(hours=24)
        except (OSError, ValueError, KeyError, TypeError):
            # 외부 401/403은 앱 로그인 실패가 아니다. 응답 본문/키를 로그에 기록하지 않는다.
            old = cached["result"] if cached else {}
            result = dict(status="stale" if old.get("points") else "unavailable",
                          points=old.get("points", []), fetched_at=old.get("fetched_at"),
                          message="검색 자료를 갱신하지 못했습니다. 5분 후 다시 시도할 수 있습니다.")
            ttl = timedelta(minutes=5)
        _cache[key] = dict(expires=now + ttl, result=result)
        _cache.move_to_end(key)
        while len(_cache) > 128:
            _cache.popitem(last=False)
        return dict(base, **result)
