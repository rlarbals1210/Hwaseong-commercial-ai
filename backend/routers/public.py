"""상권 둘러보기 — 로그인 없이 열리는 공개 화면.

노다지(서울 프로젝트)는 예비 창업자의 입지·업종 판단을 도왔고, 이 프로젝트는 공무원의
정책 판단을 돕는다. 분석 단위가 (행정동 x 업종)으로 같으므로 같은 셀을 두 방향에서 읽는다.
공무원에게는 경보, 시민에게는 탐색이다.

2026-08-18에 제외한 것은 **기존 소상공인의 자가진단**("내 가게의 위험도")이다. 그 결정의
두 축은 (1) 집계 단위라 개인화가 원리상 불가능하다 (2) 위험한 소상공인일수록 행정을 찾아올
여력이 없다 였다. **예비 창업자에게는 둘 다 적용되지 않는다** — 아직 가게가 없으니
"동과 업종을 고른다"가 자연스러운 행동이고 그것이 이 데이터의 단위와 정확히 일치하며,
창업 준비 중인 사람은 능동적으로 정보를 찾는다. 그래서 이 화면은 8/18 결정을 뒤집는 것이
아니라 그 결정이 다루지 않은 영역이다. 가설 3("소상공인 자가진단 → 기각")은 그대로 둔다.

## 공개하지 않는 것 (이 파일이 유일한 통제 지점이다)

  위험등급(안정/주의/위험)   시가 가공한 라벨을 공표하면 그 상권 상인에게 낙인이 되고
                            임대차·권리금 협상에 실질적 영향을 준다. 관측 수치만 낸다.
  예측 순위 / 성장확률       예측값 계열. 공개 화면에서는 어떤 형태로도 내지 않는다.
  상권유형 이름("쇠퇴" 등)   이름은 낙인이 되고 설명 문장은 서술이다. 문장만 낸다.
  지원사업 매칭 결과         등록된 4개 사업의 자격 요건(공고기간·한도·법적근거)이 전부
                            비어 있다(requires_verification=True). 공무원은 "확인해봐야
                            겠다"로 읽지만 시민에게는 잘못된 정보 제공이 된다.
  개별 점포                  원본은 점포 단위지만 출력은 항상 읍면동 x 업종 집계다.

순위는 **예측 순위가 아니라 관측 폐업률 기준 순위**를 새로 계산해서 낸다. 관측 사실이라
공개해도 방어되고, 창업자에게도 예측 순위보다 이쪽이 직접적이다.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AdminArea, CommercialQuarter, IndustryCategory
from ..services.risk import WINDOW_QUARTERS, pct, quarter_label

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ai"))
    from cumulative import CELL_TYPES  # type: ignore
except Exception:  # pragma: no cover
    CELL_TYPES = {}

# 인증 가드 없음 — 공개 화면이다. 노출 필드는 이 파일에서만 결정한다.
router = APIRouter(prefix="/api/public", tags=["public"])

# 창업자 관점 문구. CELL_TYPES의 advice는 공무원 처방("~검토하시길 권장합니다")이라 그대로
# 쓸 수 없다. 어느 유형도 "여기 여세요/열지 마세요"로 쓰지 않는다 — 점포 단위 예측 성능이
# 방어되지 않으므로(AUC 0.555) 추천이 아니라 판단 재료까지가 한계다.
FOUNDER_NOTES = {
    "고회전": "들어오고 나가는 일이 모두 잦은 상권입니다. 자리를 구하기는 비교적 쉬운 편이지만, "
              "오래 지키는 것이 관건입니다.",
    "쇠퇴": "나간 자리가 잘 채워지지 않고 있습니다. 조건이 좋아 보이더라도 그 이유를 먼저 "
            "확인해 보시기 바랍니다.",
    "성장": "새로 여는 곳이 닫는 곳보다 많습니다. 다만 같은 업종이 얼마나 빠르게 늘고 있는지도 "
            "함께 보시기 바랍니다.",
    "정체": "드나듦이 모두 적은 상권입니다. 경쟁은 덜하지만 새로운 수요를 직접 만들어야 할 수 "
            "있습니다.",
}

SCOPE_NOTICE = (
    f"최근 {WINDOW_QUARTERS}분기 동안 실제로 관측된 수치입니다. 읍면동 x 업종 단위 통계이며 "
    "특정 점포의 성패를 예측하지 않습니다."
)
# 공개용 잠정 고지. services.risk의 PROVISIONAL_NOTICE를 그대로 쓰지 않는 이유는 그 문구가
# "등급은 상대 순위라 영향이 적지만"을 포함하기 때문이다. 이 화면은 등급을 일부러 내리지
# 않으므로, 읽는 사람이 본 적 없는 개념을 언급하게 되고 등급 체계의 존재만 흘리게 된다.
# 실질(최근 분기는 폐업 확정에 시간이 걸려 높게 나올 수 있음)은 그대로 전한다.
PROVISIONAL_PUBLIC = (
    "가장 최근 분기는 폐업 확정까지 시간이 걸려 실제보다 높게 나올 수 있습니다. "
    "문을 닫은 것으로 집계됐다가 다음 분기에 다시 나타나는 경우가 있어, 최근 수치는 확정치가 아닙니다."
)

SUPPORT_NOTICE = (
    "화성시에는 특례보증·경영환경개선·상권 활성화 등 소상공인 지원 제도가 있습니다. "
    "신청 자격과 접수 기간은 소관 부서 공고문으로 확인하시기 바랍니다."
)


# services.risk.pct 사용(NULL 보존). 공개 화면은 sample_insufficient 게이트로 한 번 더
# 막지만, 게이트를 통과한 셀에서도 누적값이 없을 수 있다.
_pct = pct


def _latest(db: Session) -> int:
    quarter = db.query(func.max(CommercialQuarter.quarter_code)).scalar()
    if not quarter:
        raise HTTPException(status_code=404, detail="적재된 분기 데이터가 없습니다")
    return quarter


@router.get("/areas")
def list_areas(db: Session = Depends(get_db)):
    """행정동 목록과 동별 업종 목록. 없는 조합을 고르면 404가 나므로 2단계로 좁히게 한다."""
    quarter = _latest(db)
    rows = (
        db.query(
            AdminArea.id, AdminArea.area_name,
            IndustryCategory.id, IndustryCategory.industry_name,
            CommercialQuarter.sample_insufficient,
        )
        .join(CommercialQuarter, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(CommercialQuarter.quarter_code == quarter)
        .order_by(AdminArea.area_name, IndustryCategory.industry_name)
        .all()
    )
    areas: dict[int, dict] = {}
    industries: dict[int, str] = {}
    for area_id, area_name, industry_id, industry_name, short in rows:
        industries.setdefault(industry_id, industry_name)
        areas.setdefault(area_id, {"id": area_id, "name": area_name, "industries": []})
        # 표본부족 셀도 목록에 남긴다. 지우면 "왜 우리 동네는 없냐"가 되고, 사각지대 트랙과
        # 같은 원칙이다 — 판단을 보류할 뿐 존재를 감추지 않는다.
        areas[area_id]["industries"].append({"id": industry_id, "sample_insufficient": short})
    return {
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "areas": sorted(areas.values(), key=lambda a: a["name"]),
        "industries": [{"id": i, "name": n} for i, n in sorted(industries.items(), key=lambda kv: kv[1])],
    }


@router.get("/cell")
def get_public_cell(
    area_id: int = Query(...),
    industry_id: int = Query(...),
    db: Session = Depends(get_db),
):
    quarter = _latest(db)
    row = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == quarter,
            CommercialQuarter.area_id == area_id,
            CommercialQuarter.industry_id == industry_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="해당 상권을 찾을 수 없습니다")
    cell, area_name, industry_name = row

    def _avg(*conditions) -> float | None:
        value = (
            db.query(func.avg(CommercialQuarter.closure_rate_cum4))
            .filter(
                CommercialQuarter.quarter_code == quarter,
                CommercialQuarter.sample_insufficient.is_(False),
                CommercialQuarter.closure_rate_cum4.isnot(None),
                *conditions,
            )
            .scalar()
        )
        return _pct(value)

    # 관측 폐업률 기준 순위. 예측 순위(RiskPrediction.industry_rank)는 쓰지 않는다 —
    # 공개 화면에 AI가 매긴 순위를 올리면 "시가 우리 동네를 몇 위로 매겼다"가 된다.
    observed_rank = observed_total = None
    if not cell.sample_insufficient and cell.closure_rate_cum4 is not None:
        peers = [
            r[0] for r in db.query(CommercialQuarter.closure_rate_cum4)
            .filter(
                CommercialQuarter.quarter_code == quarter,
                CommercialQuarter.industry_id == industry_id,
                CommercialQuarter.sample_insufficient.is_(False),
                CommercialQuarter.closure_rate_cum4.isnot(None),
            )
            .order_by(CommercialQuarter.closure_rate_cum4.desc())
            .all()
        ]
        observed_total = len(peers)
        if peers:
            observed_rank = peers.index(cell.closure_rate_cum4) + 1

    # 최근 분기들의 누적 폐업률 추이. 노다지 메인의 '상권 트렌드'가 있던 자리인데,
    # 노다지는 매출 추세를 그렸고 이 화면은 그릴 수 없다 — 절대 매출은 공개 대상이 아니고
    # 원본 자체가 신/구 업종코드 혼재로 불연속이다. 대신 같은 셀의 누적 폐업률이 어느 쪽으로
    # 움직였는지만 낸다. 표본부족 셀은 아예 내리지 않는다. 점포 몇 곳짜리 비율에 선을 그으면
    # 없는 추세가 보이고, 그 선은 화면에서 가장 강한 주장이 된다.
    trend = []
    if not cell.sample_insufficient:
        history = (
            db.query(CommercialQuarter.quarter_code, CommercialQuarter.closure_rate_cum4)
            .filter(
                CommercialQuarter.area_id == area_id,
                CommercialQuarter.industry_id == industry_id,
                CommercialQuarter.quarter_code <= quarter,
                CommercialQuarter.closure_rate_cum4.isnot(None),
            )
            .order_by(CommercialQuarter.quarter_code.desc())
            .limit(8)
            .all()
        )
        trend = [
            {"quarter_code": q, "quarter_label": quarter_label(q), "closure_rate_pct": _pct(v)}
            for q, v in reversed(history)
        ]

    cell_type = cell.cell_type or ""
    return {
        "area_id": area_id,
        "industry_id": industry_id,
        "area_name": area_name,
        "industry_name": industry_name,
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "window_quarters": WINDOW_QUARTERS,

        "store_count": cell.store_count,
        "sample_insufficient": cell.sample_insufficient,
        # 표본부족 셀은 비율을 아예 내리지 않는다. 점포 4곳에서 폐업 0건이 "0.0%"로 나가면
        # 화면에서 감춰도 API를 직접 부른 쪽은 그 수치를 쓰게 된다. 건수는 사실이므로 남긴다.
        "closure_rate_pct": None if cell.sample_insufficient else _pct(cell.closure_rate_cum4),
        "closure_count": cell.closure_count_cum4,
        "opening_rate_pct": None if cell.sample_insufficient else _pct(cell.opening_rate_ma4),

        # 숫자 하나만 보면 "7.2%, 그래서 뭐?"다. 세 방향 평균과 나란히 놓아야 판단이 된다.
        "comparison": {
            "city_avg_pct": _avg(),
            "industry_avg_pct": _avg(CommercialQuarter.industry_id == industry_id),
            "area_avg_pct": _avg(CommercialQuarter.area_id == area_id),
        },
        "observed_rank": observed_rank,
        "observed_total": observed_total,
        "trend": trend,

        # 유형 '이름'은 내리지 않는다. 설명 문장과 창업자 관점 문구만 낸다.
        "pattern_summary": CELL_TYPES.get(cell_type, {}).get("summary"),
        "founder_note": FOUNDER_NOTES.get(cell_type),

        "scope_notice": SCOPE_NOTICE,
        "support_notice": SUPPORT_NOTICE,
        "provisional_notice": f"{quarter_label(quarter)} 기준. {PROVISIONAL_PUBLIC}",
    }


# ---------------------------------------------------------------------------
# 업종 하나 = 화성시 한 장 (지도 + 순위표)
#
# 노다지(서울)의 메인 화면은 "업종을 고르면 지역들이 한 화면에 줄을 선다"였다. 이 화면도
# 같은 동작을 하되 정렬 축이 반대다 — 노다지는 AI 점수가 높은 순의 추천이었고, 여기는
# 관측 폐업률이 잦은 순의 서술이다. 추천으로 뒤집지 않는 이유는 이 파일 맨 위 '공개하지
# 않는 것'과 같다. 점포 단위 예측 성능(AUC 0.555)이 "여기 여세요"를 지탱하지 못한다.
# 순위 방향도 /cell의 observed_rank(잦은 순)와 일부러 같게 뒀다. 두 화면이 같은 셀에
# 다른 등수를 말하면 그 순간 둘 다 못 믿게 된다.
#
# 색: 등급색(초록-주황-빨강)을 쓰지 않는다. 공개 지도에서 빨강은 관측치가 아니라 판정으로
# 읽히고 그 읍면동 상인에게 낙인이 된다. 단일 계열 4단계로 칠하고 범례에는 실제 % 구간을
# 그대로 적는다. 색이 "얼마나"만 말하고 "좋다/나쁘다"는 말하지 않게 하는 장치다.
# 구간은 고정 임계값이 아니라 그 업종의 실제 분포 4분위다 — 고정값을 쓰면 폐업이 드문
# 업종은 전부 옅은 색, 잦은 업종은 전부 짙은 색이 되어 지도가 아무 말도 하지 않는다.
MAP_RAMP = ["#d5e3ff", "#a8c8ff", "#62aef0", "#005db2"]  # --primary-fixed ~ --primary
MAP_HOLD_COLOR = "#c1c6d5"  # --outline-variant. 공무원 지도의 판단보류와 같은 색이다.


def _quantile(values: list[float], p: float) -> float:
    """정렬된 값 목록의 분위수(선형보간). numpy를 쓰지 않는 이유는 backend가 의존하지 않기 때문."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * p
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (pos - low)


@router.get("/industry-map")
def industry_map(industry_id: int = Query(...), db: Session = Depends(get_db)):
    quarter = _latest(db)
    rows = (
        db.query(CommercialQuarter, AdminArea.area_name, IndustryCategory.industry_name)
        .join(AdminArea, CommercialQuarter.area_id == AdminArea.id)
        .join(IndustryCategory, CommercialQuarter.industry_id == IndustryCategory.id)
        .filter(
            CommercialQuarter.quarter_code == quarter,
            CommercialQuarter.industry_id == industry_id,
        )
        .order_by(AdminArea.area_name)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="해당 업종을 찾을 수 없습니다")
    industry_name = rows[0][2]

    # 표본충분 셀만으로 구간을 만든다. 표본부족 셀의 비율을 섞으면 점포 4곳짜리 0%가
    # 1분위 경계를 끌어내려, 실제로는 평범한 읍면동이 가장 옅은 색을 받는다.
    measured = sorted(
        _pct(cell.closure_rate_cum4)
        for cell, _, _ in rows
        if not cell.sample_insufficient and cell.closure_rate_cum4 is not None
    )
    cuts = [_quantile(measured, p) for p in (0.25, 0.5, 0.75)] if measured else []

    def _bin(value: float) -> int:
        for i, cut in enumerate(cuts):
            if value < cut:
                return i
        return len(cuts)

    # 순위는 잦은 순(내림차순). 동률이면 같은 등수를 준다 — 소수점 두 자리가 같은데
    # 등수가 갈리면 "왜 우리가 한 칸 아래냐"에 답할 근거가 없다.
    ordered = sorted(measured, reverse=True)

    areas = []
    for cell, area_name, _ in rows:
        value = None if cell.sample_insufficient else _pct(cell.closure_rate_cum4)
        entry = {
            "area_id": cell.area_id,
            "area_name": area_name,
            "store_count": cell.store_count,
            "closure_count": cell.closure_count_cum4,
            "sample_insufficient": cell.sample_insufficient,
            "closure_rate_pct": value,
            "color": MAP_HOLD_COLOR if value is None else MAP_RAMP[_bin(value)],
            "rank": None if value is None else ordered.index(value) + 1,
        }
        areas.append(entry)

    # 범례 문구도 서버에서 만든다. 프론트에서 조립하면 구간 정의가 두 곳에 생기고,
    # 파이프라인이 갱신됐을 때 색과 설명이 어긋난다(이 파일 맨 위 원칙과 같다).
    legend = []
    if cuts:
        bounds = [None, *cuts, None]
        for i, color in enumerate(MAP_RAMP):
            low, high = bounds[i], bounds[i + 1]
            if low is None:
                label = f"{high:.1f}% 미만"
            elif high is None:
                label = f"{low:.1f}% 이상"
            else:
                label = f"{low:.1f} ~ {high:.1f}%"
            legend.append({"label": label, "color": color})
    legend.append({"label": "판단보류 (점포 50곳 미만)", "color": MAP_HOLD_COLOR})

    city_avg = (
        db.query(func.avg(CommercialQuarter.closure_rate_cum4))
        .filter(
            CommercialQuarter.quarter_code == quarter,
            CommercialQuarter.industry_id == industry_id,
            CommercialQuarter.sample_insufficient.is_(False),
            CommercialQuarter.closure_rate_cum4.isnot(None),
        )
        .scalar()
    )

    return {
        "quarter_code": quarter,
        "quarter_label": quarter_label(quarter),
        "window_quarters": WINDOW_QUARTERS,
        "industry_id": industry_id,
        "industry_name": industry_name,
        "industry_avg_pct": _pct(city_avg),
        "measured_count": len(measured),
        "total_count": len(areas),
        "legend": legend,
        "areas": areas,
        "scope_notice": SCOPE_NOTICE,
        "provisional_notice": f"{quarter_label(quarter)} 기준. {PROVISIONAL_PUBLIC}",
    }
