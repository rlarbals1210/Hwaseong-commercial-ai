"""두 상권 비교 — "함부로 비교하지 않기"를 담당하는 모듈.

비교 화면의 위험은 노이즈를 차이로 읽게 만드는 것이다. 점포 55개와 60개 상권에서 폐업이
1건 다르면 폐업률은 1.7%p 벌어져 보이지만 이건 표본 크기의 산물이다. 단일 분기 지표를
버린 이유(분기 간 순위 상관 +0.296)와 같은 문제가 비교 화면에서 되살아난다.

그래서 두 셀의 Wilson 신뢰구간이 겹치면 "차이 없음"으로 명시한다.

주의 — 기존 원칙과의 관계:
    `closure_rate_lower4`(Wilson 하한)는 "정렬·순위에만 쓰고 등급 판정에는 쓰지 않는다"가
    프로젝트 원칙이다(CLAUDE.md). 여기서도 등급을 바꾸는 데는 쓰지 않는다. 등급은 저장된
    risk_grade를 그대로 읽고, 신뢰구간은 오직 "이 차이를 말해도 되는가"만 판정한다.

구간 겹침은 보수적인 검정이다(겹친다고 반드시 유의하지 않은 것은 아니다). 즉 실제보다
"차이 없음"을 자주 말한다. 이 방향의 오류를 택한 것은 의도적이다 — 없는 차이를 있다고
말하는 쪽이 행정 판단에서 더 비싸다.
"""
import math

from .risk import WINDOW_QUARTERS

Z = 1.96  # 95%


def wilson_interval(count: int, n: int, z: float = Z) -> tuple[float, float]:
    """이항 비율의 Wilson 점수 구간. (하한, 상한) 0~1.

    정규근사(Wald)를 쓰지 않는 이유: 폐업은 드문 사건이라 p가 0에 가깝고 n이 작을 때
    Wald 구간은 하한이 음수로 나가거나 폭이 0으로 붕괴한다.
    """
    if n <= 0:
        return 0.0, 1.0
    p = count / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def cumulative_denominator(cell) -> tuple[int | None, bool]:
    """4분기 누적 폐업률의 분모(= 4개 분기 직전점포수 합)를 복원한다.

    누적 비율은 건수합/분모합으로 계산되므로(ai/cumulative.py) 건수와 비율이 모두 0이
    아니면 분모가 정확히 복원된다. 폐업 0건인 셀은 비율도 0이라 복원이 불가능해서
    현재 점포수 x 창 길이로 근사하고, 근사했음을 호출부에 알린다(두 번째 반환값).

    반환: (분모, 근사여부)
    """
    rate, count = cell.closure_rate_cum4, cell.closure_count_cum4
    if rate and count:
        return max(1, round(count / rate)), False
    if cell.store_count:
        return cell.store_count * WINDOW_QUARTERS, True
    return None, True


def closure_interval_pct(cell) -> dict | None:
    """셀의 누적 폐업률 신뢰구간(%)."""
    n, approximate = cumulative_denominator(cell)
    if n is None:
        return None
    lower, upper = wilson_interval(cell.closure_count_cum4 or 0, n)
    return {
        "lower_pct": round(lower * 100, 2),
        "upper_pct": round(upper * 100, 2),
        "denominator": n,
        "approximate": approximate,
    }


def two_proportion_z(c1: int, n1: int, c2: int, n2: int) -> float | None:
    """두 비율 차이의 z통계량(양측). 표본이 없거나 분산이 0이면 None."""
    if min(n1, n2) <= 0:
        return None
    pooled = (c1 + c2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    return abs(c1 / n1 - c2 / n2) / se


def rates_distinguishable(left_ci: dict | None, right_ci: dict | None,
                          left_count: int, right_count: int) -> bool:
    """이 차이를 말해도 되는가. 두 비율의 z검정(alpha=0.05).

    신뢰구간 겹침 여부로 판정하지 않는다. 겹침 판정은 실질 alpha가 0.005 수준으로 과하게
    보수적이라 실측에서 "위험 vs 안정" 등급 조합조차 79.3%만 구분됐다(z검정은 94.6%).
    구간은 화면에 함께 보여주되(불확실성의 크기를 보여주는 역할), 판정은 z검정으로 한다.

    실측 구분가능 비율(2025Q4, 표본충분 231셀):
        위험 vs 안정 94.6% / 주의 vs 안정 59.8% / 위험 vs 주의 32.2%
        같은 동 다른 업종 46.4% / 같은 업종 다른 동 14.0%
    마지막 줄은 격자 검증(docs/격자-검증-2026-08-25.md)의 결론과 같은 방향이다 —
    정보는 공간이 아니라 업종 축에서 나온다.
    """
    if not left_ci or not right_ci:
        return False
    z = two_proportion_z(left_count, left_ci["denominator"], right_count, right_ci["denominator"])
    return z is not None and z > Z


def build_verdict(left: dict, right: dict, distinguishable: bool) -> str:
    """비교 결론 한 줄 — 규칙 기반(외부 LLM 미사용).

    용어 규칙(CLAUDE.md)을 따른다. "지원이 시급합니다"처럼 집행을 단정하는 표현을 쓰지 않고
    공무원의 다음 행동(확인)만 제안한다. 판정은 상권 단위이며 개별 점포에 대해 말하지 않는다.
    """
    l_name = f"{left['area_name']}·{left['industry_name']}"
    r_name = f"{right['area_name']}·{right['industry_name']}"

    if left["sample_insufficient"] or right["sample_insufficient"]:
        short = l_name if left["sample_insufficient"] else r_name
        if left["sample_insufficient"] and right["sample_insufficient"]:
            short = f"{l_name}, {r_name}"
        return (
            f"{short}은(는) 표본부족 상권이라 통계 판단을 보류합니다. "
            "폐업 건수는 그대로 보여드리니 현장 확인으로 판단하시기 바랍니다."
        )

    if not distinguishable:
        return (
            "두 상권의 폐업률 차이는 표본 크기로 설명될 수 있어 어느 쪽이 더 위험하다고 "
            "말하기 어렵습니다. 아래 신뢰구간의 폭을 함께 보시기 바랍니다."
        )

    # 누적 폐업률이 없는 셀은 크기 비교 자체가 불가능하다. 예전에는 라우터가 NULL을
    # 0.0으로 바꿔 내려서 이 비교가 항상 "더 안전한 쪽"으로 기울었다. 지금은 NULL이
    # 그대로 오므로 여기서 명시적으로 막는다(None >= float 는 TypeError다).
    l_rate = left.get("cumulative_closure_rate_pct")
    r_rate = right.get("cumulative_closure_rate_pct")
    if l_rate is None or r_rate is None:
        missing = l_name if l_rate is None else r_name
        if l_rate is None and r_rate is None:
            missing = f"{l_name}, {r_name}"
        return (
            f"{missing}은(는) 최근 4분기 누적 폐업률이 아직 산출되지 않아 비교할 수 없습니다. "
            "분기가 4개 쌓이면 판정됩니다."
        )

    higher, lower = (left, right) if l_rate >= r_rate else (right, left)
    h_name = l_name if higher is left else r_name
    parts = [f"{h_name}의 현장 확인 우선순위가 높습니다"]
    if higher.get("risk_grade"):
        parts.append(f"등급 {higher['risk_grade']}")
    if higher.get("cell_type"):
        parts.append(f"유형 {higher['cell_type']}")
    if higher.get("anomaly"):
        parts.append("트렌드 이상 감지")
    tail = " · ".join(parts[1:])
    return parts[0] + (f" ({tail})." if tail else ".")
