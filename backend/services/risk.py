def risk_level(score: float) -> tuple[str, str]:
    if score >= 70:
        return "위험", "#EF4444"
    if score >= 50:
        return "주의", "#F59E0B"
    return "안전", "#10B981"


def action_message(score: float, anomaly: bool) -> str:
    if anomaly:
        return "즉시 현장 점검 필요 (트렌드 이상)"
    if score >= 70:
        return "정책자금 지원 우선 검토"
    if score >= 50:
        return "분기별 모니터링 강화"
    return "정기 관찰 유지"
