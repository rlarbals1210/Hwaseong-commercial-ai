import jwt

from backend.auth.security import JWT_ALGORITHM, JWT_SECRET_KEY, create_access_token


def test_access_token_uses_configured_nonempty_secret():
    assert JWT_SECRET_KEY
    token = create_access_token({"sub": "test", "role": "official"})
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

    assert payload["sub"] == "test"
    assert payload["role"] == "official"
