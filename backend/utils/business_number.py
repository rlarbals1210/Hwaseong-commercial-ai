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
