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

_DEFAULT_THRESHOLDS = {
    "avg_closure_rate_pct": 3.2,
    "danger_threshold_pct": 6.4,
    "dong_ratio_avg_pct": 11.6,
    "dong_ratio_danger_pct": 23.2,
    "sample_min": 30,
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
SAMPLE_MIN = _THRESHOLDS["sample_min"]


def risk_level(closure_rate_pct: float) -> tuple[str, str]:
    """셀 단위 등급 — 실제 관측 폐업률(%)만 사용. 예측값은 관여하지 않는다."""
    if closure_rate_pct >= DANGER_THRESHOLD_PCT:
        return "위험", "#D51B4C"
    if closure_rate_pct >= AVG_CLOSURE_RATE_PCT:
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
    if anomaly:
        return "즉시 현장 점검 필요 (트렌드 이상)"
    if level == "표본부족":
        return "표본 부족 — 참고용, 정책 판단 보류 권장"
    if level == "위험":
        return "정책자금 지원 우선 검토"
    if level == "주의":
        return "분기별 모니터링 강화"
    return "정기 관찰 유지"
