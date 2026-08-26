import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# ai/build_risk_index.py가 매 실행마다 실제 관측치 기준으로 기준선을 계산해 여기에 저장한다.
# 하드코딩 금지 — 데이터 갱신 시 자동 반영. 파일이 없으면(파이프라인 미실행) 안전한 기본값으로 폴백.
# 예측값(모델 출력)은 어떤 기준선에도 관여하지 않는다 — 순위로만 쓰고 절대값은 노출하지 않는 원칙.
_PROCESSED_DIR = Path(os.getenv("PROCESSED_DATA_DIR", "data/processed"))
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_THRESHOLDS_PATH = _PROJECT_ROOT / _PROCESSED_DIR / "risk_thresholds.json"

# 2026-08-20: 기준선이 "단일 분기 시평균 x 2"에서 "4분기 누적 폐업률의 분위수"로 바뀌었다.
# danger = 상위 10% 경계, caution = 상위 30% 경계. 절대 임계가 아니라 화성시 내 상대 순위이며,
# 화면에 그 점을 명시해야 한다. 산출 근거는 ai/cumulative.py 주석 참조.
_DEFAULT_THRESHOLDS = {
    "avg_closure_rate_pct": 5.9,
    "danger_threshold_pct": 10.35,
    "caution_threshold_pct": 7.26,
    "dong_ratio_avg_pct": 12.5,
    "dong_ratio_danger_pct": 34.6,
    "sample_min": 50,
    "window_quarters": 4,
}


def _load_thresholds() -> dict:
    try:
        with open(_THRESHOLDS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _DEFAULT_THRESHOLDS


_THRESHOLDS = _load_thresholds()
AVG_CLOSURE_RATE_PCT = _THRESHOLDS["avg_closure_rate_pct"]
DANGER_THRESHOLD_PCT = _THRESHOLDS["danger_threshold_pct"]
DONG_RATIO_AVG_PCT = _THRESHOLDS["dong_ratio_avg_pct"]
DONG_RATIO_DANGER_PCT = _THRESHOLDS["dong_ratio_danger_pct"]
CAUTION_THRESHOLD_PCT = _THRESHOLDS.get("caution_threshold_pct", AVG_CLOSURE_RATE_PCT)
SAMPLE_MIN = _THRESHOLDS["sample_min"]
WINDOW_QUARTERS = _THRESHOLDS.get("window_quarters", 4)
# 기준선을 산출한 표본충분 셀 수. 화면이 "상위 10개"를 전체 분석 대상으로 오해시키지 않도록
# 실제 모수를 함께 내려준다.
ELIGIBLE_CELLS = _THRESHOLDS.get("eligible_cells")
GRADE_NOTICE = (
    f"등급은 최근 {WINDOW_QUARTERS}분기 누적 폐업률 기준이며, "
    "화성시 내 상대 순위입니다(위험 = 상위 10%, 주의 = 상위 30%). 절대 기준이 아닙니다."
)

# 0~1 비율을 퍼센트로 옮기는 공용 헬퍼.
#
# NULL을 0.0으로 바꾸지 않는다. 이게 중요한 이유 —
# ai/cumulative.py가 rolling(4, min_periods=4)라 셀의 처음 4분기는 누적값이 없고 DB에
# NULL로 들어간다(전체 35,505행 중 7,466행 = 21%). 예전 라우터들은 `(value or 0.0) * 100`을
# 써서 그 NULL을 0.0%로 바꿨고, 그 결과 "값이 없는 구간"이 "폐업이 0이던 구간"으로 읽혔다.
# 모든 셀의 추이 차트가 0%에서 시작해 4분기째 급등하는 모양이 됐다(2026-08-25 감사).
#
# 없는 값은 없는 값으로 내려보내고, 화면이 "—"나 선 끊김으로 처리하게 한다.
def pct(value) -> float | None:
    """0~1 비율 -> 퍼센트(소수점 2자리). None은 None 그대로."""
    return None if value is None else round(value * 100, 2)


# 동 단위 등급의 최소 분모.
#
# 셀 단위 소표본은 Wilson 하한으로 보정했지만 동 단위 집계에는 같은 방어가 없었다.
# 동 등급 기준선이 위험업종비율 34.64%라서 표본충분 셀이 3개인 동은 2개만 위험이면
# 66.7%가 되어 "위험"으로 칠해진다. 실측(2026-08-25): 29개 동 중 19개가 표본충분 셀
# 10개 미만이고, 지도에서 가장 빨간 두 동이 동탄8동 2/3, 새솔동 4/6이었다.
# 표본충분 셀이 0개인 동(기배동 0/54, 매송면 0/48)은 분모가 0이라 비율이 0.0으로
# 저장됐고, 그 0.0이 "안정"(초록)으로 칠해졌다 — 판단 불가가 안전으로 읽혔다.
# 판정 보류 기준. 임계 10이 통계적으로는 가장 방어하기 쉬웠지만(29개 동 중 21개 보류)
# 그러면 위험 등급 동이 0개가 되어 지도가 "어디가 위험한가"를 못 보여준다. 안 보는 화면은
# 틀린 화면보다 나을 게 없다고 판단해 5로 두고, 근거가 얕은 동은 아래 기준으로 흐리게 칠한다.
# 5는 가장 심한 왜곡(동탄8동 2/3 = 66.7%)을 걷어내면서 20개 동의 판정을 남긴다.
AREA_MIN_SUFFICIENT_CELLS = 5

# 이 수 미만이면 판정은 하되 "근거가 얕다"고 화면에 표시한다(폴리곤 투명도·배지).
# 숨기는 대신 알려주는 쪽이 감사 대응에도 유리하다.
AREA_THIN_EVIDENCE_CELLS = 10
AREA_HOLD_LEVEL = "판단보류"
AREA_HOLD_NOTICE = (
    f"표본이 충분한 업종이 {AREA_MIN_SUFFICIENT_CELLS}개 미만이라 동 단위 등급 판정을 "
    "보류했습니다. 위험하지 않다는 뜻이 아니라 판단할 근거가 부족하다는 뜻입니다."
)
AREA_THIN_NOTICE = (
    f"표본이 충분한 업종이 {AREA_THIN_EVIDENCE_CELLS}개 미만입니다. 등급은 냈지만 "
    "적은 수의 업종으로 계산된 값이므로 셀 단위로 확인하시기 바랍니다."
)


LATEST_QUARTER = _THRESHOLDS.get("quarter")


def quarter_label(code) -> str:
    """20254 -> '2025Q4'. 코드가 없거나 형식이 다르면 원값을 문자열로 돌려준다."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return str(code) if code is not None else ""
    year, quarter = divmod(code, 10)
    return f"{year}Q{quarter}" if 1 <= quarter <= 4 else str(code)


# 최신 분기는 폐업 확정에 시간이 걸린다. 스냅샷에서 사라진 점포가 이후 분기에 다시 나타나는
# 사례가 있어(2023Q1은 72.1%가 재등장) 사라짐이 곧 폐업이라고 단정할 수 없는데, 최근 분기는
# 그 재등장 여부를 관측할 기간 자체가 아직 없다. 따라서 최신 분기 폐업은 과대 계상될 수 있다.
# 등급은 화성시 내 상대 순위라 모든 셀이 같이 영향을 받으면 순위는 보존되지만, 절대 수치를
# 확정치로 읽으면 안 되므로 화면에 그대로 고지한다.
PROVISIONAL_NOTICE = (
    f"{quarter_label(LATEST_QUARTER)}는 잠정치입니다. 최근 분기는 폐업 확정에 시간이 걸려 "
    "실제보다 높게 나올 수 있습니다. 등급은 상대 순위라 영향이 적지만, 절대 수치는 확정치가 아닙니다."
)


def risk_level(cumulative_closure_rate_pct: float) -> tuple[str, str]:
    """셀 단위 등급 — 4분기 누적 관측 폐업률(%)만 사용. 예측값은 관여하지 않는다.

    주의: 단일 분기 폐업률을 넣으면 안 된다. 기준선이 누적 기준이라 거의 전부 "안정"으로 나온다.
    정규화 DB를 쓰는 신규 라우터는 저장된 risk_grade를 그대로 읽으므로 이 함수를 쓰지 않는다.
    """
    if cumulative_closure_rate_pct >= DANGER_THRESHOLD_PCT:
        return "위험", "#D51B4C"
    if cumulative_closure_rate_pct >= CAUTION_THRESHOLD_PCT:
        return "주의", "#F59E0B"
    return "안정", "#10B981"


def dong_risk_level(risk_ratio_pct: float) -> tuple[str, str]:
    """읍면동 단위 등급 — 위험 업종 비율(%) 기준. 셀단위 기준선과 스케일이 달라 별도 기준선 사용."""
    if risk_ratio_pct >= DONG_RATIO_DANGER_PCT:
        return "위험", "#D51B4C"
    if risk_ratio_pct >= DONG_RATIO_AVG_PCT:
        return "주의", "#F59E0B"
    return "안정", "#10B981"


def action_message(level: str, anomaly: bool) -> str:
    """후속 조치 '검토안' 문구 — 규칙 기반 템플릿(외부 LLM 미사용).

    AI가 지원 대상을 결정한다는 오해를 막기 위해 "정책자금 지원"처럼 집행을 단정하는 표현을
    쓰지 않는다. 모든 문구는 공무원의 다음 행동(확인·관찰)을 제안하는 형태로만 쓴다.
    """
    if anomaly:
        return "트렌드 이상 — 현장 확인 우선"
    if level == "표본부족":
        return "표본 부족 — 통계 판단 보류, 현장 확인 권장"
    if level == "위험":
        return "현장 확인 우선순위 높음"
    if level == "주의":
        return "분기별 모니터링 강화"
    return "정기 관찰 유지"
