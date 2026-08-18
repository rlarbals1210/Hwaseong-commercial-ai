import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv


# auth 모듈은 database 모듈보다 먼저 import될 수 있으므로 여기서 직접 .env를 로드한다.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY 환경변수가 설정되지 않았습니다")


def create_access_token(claims: dict) -> str:
    payload = {
        **claims,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
