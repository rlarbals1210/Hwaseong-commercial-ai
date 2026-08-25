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
GRADE_NOTICE = (
    f"등급은 최근 {WINDOW_QUARTERS}분기 누적 폐업률 기준이며, "
    "화성시 내 상대 순위입니다(위험 = 상위 10%, 주의 = 상위 30%). 절대 기준이 아닙니다."
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
