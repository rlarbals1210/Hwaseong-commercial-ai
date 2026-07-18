from ..utils.business_number import validate_business_number, normalize_business_number

# 아래 번호들은 실제 등록된 사업자번호가 아니라, 공개된 체크섬 알고리즘으로
# 직접 계산해 검증한 값(수기 계산 확인 완료)이다.
VALID_NUMBERS = ["1234567891", "0000000000", "2222222227"]
INVALID_CHECK_DIGIT = ["1234567892", "0000000001", "2222222220"]


def test_valid_numbers_pass():
    for n in VALID_NUMBERS:
        assert validate_business_number(n) is True


def test_wrong_check_digit_fails():
    for n in INVALID_CHECK_DIGIT:
        assert validate_business_number(n) is False


def test_wrong_length_fails():
    assert validate_business_number("123456789") is False
    assert validate_business_number("12345678901") is False
    assert validate_business_number("") is False


def test_dash_formatted_input_normalizes_and_validates():
    assert validate_business_number("123-45-67891") is True
    assert normalize_business_number("123-45-67891") == "1234567891"


def test_non_digit_characters_are_stripped_before_length_check():
    assert validate_business_number("abc-de-fghij") is False
