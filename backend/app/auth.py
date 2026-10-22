from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def token_for(user):
    return jwt.encode(
        {
            "sub": user.id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=settings().token_minutes),
            "iss": "orderflow",
            "aud": "orderflow-api",
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db, scope="function"),
):
    try:
        if credentials is None:
            raise ValueError()
        claims = jwt.decode(
            credentials.credentials,
            settings().jwt_secret,
            algorithms=["HS256"],
            issuer="orderflow",
            audience="orderflow-api",
        )
        user = db.get(User, claims["sub"])
        if user is None:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})


def merchant(user=Depends(current_user)):
    if user.role not in {"admin", "staff"}:
        raise HTTPException(403, "Merchant permission required")
    return user


def admin(user=Depends(merchant)):
    if user.role != "admin":
        raise HTTPException(403, "Admin permission required")
    return user
