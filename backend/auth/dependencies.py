import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .security import JWT_ALGORITHM, JWT_SECRET_KEY

_bearer = HTTPBearer()


def decode_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="인증 정보가 유효하지 않습니다")


def require_role(role: str):
    def _checker(payload: dict = Depends(decode_token)) -> dict:
        if payload.get("role") != role:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다")
        return payload

    return _checker


get_current_official = require_role("official")
get_current_citizen = require_role("citizen")
