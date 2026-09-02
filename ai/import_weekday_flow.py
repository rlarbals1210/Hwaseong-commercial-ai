"""최신 완결 월 검증 → 요일 상대지수만 적재. 원본·기존 ML 산출물은 변경하지 않는다.

python -m ai.import_weekday_flow --dry-run
python -m ai.import_weekday_flow
"""
import argparse
import calendar
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import math

import pandas as pd
from sqlalchemy.dialects.postgresql import insert

from backend.database import SessionLocal
from backend.models import AdminArea, AreaWeekdayFlow
from eda.paths import FLOATING_POP_CSV, GYEONGGI_DONG_LIST_CSV

DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def validate_month(frame, code_to_area, month):
    """모든 지역을 먼저 검증한다. 한 지역이라도 실패하면 전체 적재를 보류한다."""
    start = datetime.strptime(month, "%Y%m").date()
    if start >= date.today().replace(day=1):
        raise ValueError("완결되지 않은 월은 적재하지 않습니다")
    counts = Counter(date(start.year, start.month, day).weekday()
                     for day in range(1, calendar.monthrange(start.year, start.month)[1] + 1))
    if set(frame["ADMDONG_CD"]) != set(code_to_area):
        raise ValueError("읍면동 코드 매핑과 원본 지역 범위가 다릅니다")
    if frame.duplicated(["ADMDONG_CD", "WDAY_CD"]).any():
        raise ValueError("지역·요일 중복키가 있습니다")
    rows = []
    for code, group in frame.groupby("ADMDONG_CD"):
        if set(group["WDAY_CD"]) != {*DAYS, "TOT"}:
            raise ValueError("요일 7개 또는 월 합계가 누락됐습니다")
        values = dict(zip(group["WDAY_CD"], pd.to_numeric(group["DYNMC_POPLTN_CNT"], errors="raise")))
        if any(not math.isfinite(v) or v <= 0 for v in values.values()):
            raise ValueError("유동인구 값에 결측·비양수·무한값이 있습니다")
        reconstructed = sum(values[day] * counts[i] for i, day in enumerate(DAYS))
        # 요일별 일평균 × 해당 월 요일 수 ≈ 월 합계인지 검사한다.
        # 원본 반올림을 고려해 1% 허용. 이 조건 없이 공급자 RATE를 비중으로 쓰지 않는다.
        if abs(reconstructed / values["TOT"] - 1) > .01:
            raise ValueError("요일 값으로 월 합계가 재현되지 않습니다. 측정 단위를 재검토하세요")
        mean = sum(values[day] for day in DAYS) / 7
        for i, day in enumerate(DAYS):
            rows.append(dict(area_id=code_to_area[code], month=start.strftime("%Y-%m"),
                             weekday=i, relative_index=values[day] / mean * 100))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source = pd.read_csv(FLOATING_POP_CSV, dtype=str,
                         usecols=["STD_YM", "ADMDONG_CD", "WDAY_CD", "DYNMC_POPLTN_CNT"])
    month = source["STD_YM"].max()
    latest = source[source["STD_YM"] == month]
    names = pd.read_csv(GYEONGGI_DONG_LIST_CSV, encoding="cp949", dtype=str)
    with SessionLocal() as db:
        areas = {area.area_name: area.id for area in db.query(AdminArea).filter(AdminArea.is_current.is_(True))}
        mapping = names[names["읍면동코드"].isin(latest["ADMDONG_CD"]) & names["읍면동명"].isin(areas)]
        mapping = mapping[["읍면동코드", "읍면동명"]].drop_duplicates()
        if (mapping["읍면동코드"].duplicated().any() or mapping["읍면동명"].duplicated().any()
                or set(mapping["읍면동명"]) != set(areas)):
            raise ValueError("현재 읍면동과 원본 코드의 1:1 대응 검증 실패")
        code_to_area = {code: areas[name] for code, name in mapping.itertuples(index=False, name=None)}
        rows = validate_month(latest, code_to_area, month)
        digest = hashlib.sha256(FLOATING_POP_CSV.read_bytes()).hexdigest()
        for row in rows:
            row.update(source_sha256=digest, imported_at=datetime.now(timezone.utc))
        if not args.dry_run:
            statement = insert(AreaWeekdayFlow).values(rows)
            db.execute(statement.on_conflict_do_update(
                constraint="uq_area_month_weekday",
                set_={key: getattr(statement.excluded, key)
                      for key in ("relative_index", "source_sha256", "imported_at")},
            ))
            db.commit()
    print(f"{'검증 완료' if args.dry_run else '적재 완료'}: {month}, {len(code_to_area)}개 지역, {len(rows)}개 요일 지수")


if __name__ == "__main__":
    main()
