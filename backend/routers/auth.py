import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.security import create_access_token
from ..database import get_db
from ..models import Official
from ..schemas import CitizenLoginRequest, OfficialLoginRequest, TokenResponse
from ..utils.business_number import normalize_business_number, validate_business_number

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/official/login", response_model=TokenResponse)
def official_login(body: OfficialLoginRequest, db: Session = Depends(get_db)):
    official = db.query(Official).filter(Official.username == body.username).first()
    if not official or not bcrypt.checkpw(
        body.password.encode("utf-8"), official.password_hash.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    token = create_access_token({"sub": str(official.id), "role": "official", "username": official.username})
    return TokenResponse(access_token=token, role="official", verification_type="credential")


@router.post("/citizen/login", response_model=TokenResponse)
def citizen_login(body: CitizenLoginRequest):
    if not validate_business_number(body.business_number):
        raise HTTPException(status_code=400, detail="사업자등록번호 형식이 올바르지 않습니다")

    normalized = normalize_business_number(body.business_number)
    token = create_access_token({"sub": normalized, "role": "citizen"})
    return TokenResponse(access_token=token, role="citizen", verification_type="format_check_only")
