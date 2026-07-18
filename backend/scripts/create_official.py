"""공무원 계정 최초 생성용 1회성 CLI 스크립트.

사용법: python -m backend.scripts.create_official <username> <password> [name]
"""

import argparse
import sys

import bcrypt

from ..database import SessionLocal
from ..models import Official


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("name", nargs="?", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if db.query(Official).filter(Official.username == args.username).first():
            print(f"이미 존재하는 계정입니다: {args.username}")
            sys.exit(1)

        password_hash = bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.add(Official(username=args.username, password_hash=password_hash, name=args.name))
        db.commit()
        print(f"계정 생성 완료: {args.username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
