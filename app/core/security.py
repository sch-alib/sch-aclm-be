from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_context.verify(password, password_hash)


def create_access_token(username: str, role: str) -> str:
    expiration = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_minutes
    )
    payload = {
        "sub": username,
        "role": role,
        "exp": expiration,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
