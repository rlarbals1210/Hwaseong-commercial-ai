import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.security import create_access_token
from ..database import get_db
from ..models import Official
from ..schemas import OfficialLoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


# 시민(사업자등록번호) 로그인은 2026-08-18 설계 결정으로 제거했다.
# 검증 로직 자체(backend/utils/business_number.py)와 테스트는 "검토 후 의도적 제외"의
# 근거로 리포에 보존한다 — 상세 사유는 CLAUDE.md '설계 결정' 절 참조.
@router.post("/official/login", response_model=TokenResponse)
def official_login(body: OfficialLoginRequest, db: Session = Depends(get_db)):
    official = db.query(Official).filter(Official.username == body.username).first()
    if not official or not bcrypt.checkpw(
        body.password.encode("utf-8"), official.password_hash.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    token = create_access_token({"sub": str(official.id), "role": "official", "username": official.username})
    return TokenResponse(access_token=token, role="official", verification_type="credential")
