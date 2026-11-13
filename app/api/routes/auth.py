from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.database.session import get_database_session
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    session: Session = Depends(get_database_session),
) -> LoginResponse:
    user = session.query(User).filter(User.username == request.username).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return LoginResponse(
        access_token=create_access_token(user.username, user.role),
        username=user.username,
        role=user.role,
    )
