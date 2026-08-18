"""사업자등록번호 체크섬 검증 (국세청 공개 알고리즘).

2026-08-18 설계 결정으로 시민(소상공인) 직접조회 기능을 제외하면서 현재 파이프라인에서는
호출되지 않는다. 삭제하지 않고 보존하는 이유는 "시민 인증 수단을 검토했고, 주민등록번호가
아닌 사업자등록번호 형식검증 방식까지 구현한 뒤 의도적으로 제외했다"는 판단 근거를
결과보고서에서 인용하기 위함이다. 테스트(backend/tests/test_business_number.py)도 함께 유지한다.
"""

import re


def normalize_business_number(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def validate_business_number(raw: str) -> bool:
    digits = normalize_business_number(raw)
    if len(digits) != 10:
        return False

    d = [int(c) for c in digits]
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(d[i] * weights[i] for i in range(9)) + (d[8] * 5) // 10
    check_digit = (10 - total % 10) % 10
    return check_digit == d[9]
