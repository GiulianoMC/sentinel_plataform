from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_active_user
from app.core.rate_limiter import limiter
from app.use_cases.Auth.register_user import register_user_use_case
from app.use_cases.Auth.login_user import login_user_use_case
from app.use_cases.Auth.refresh_token import refresh_token_use_case
from app.use_cases.Auth.logout_user import logout_user_use_case
from app.schemas.AuthSchema import UserCreate, UserLogin, TokenRefresh, Token, UserWithToken, UserResponse
from app.models.UserModel import User

router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.post("/register", response_model=UserWithToken, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    try:
        return register_user_use_case(db, user_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, credentials: UserLogin, db: Session = Depends(get_db)):
    try:
        return login_user_use_case(db, credentials)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
def refresh(request: Request, token_data: TokenRefresh, db: Session = Depends(get_db)):
    try:
        return refresh_token_use_case(db, token_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def logout(request: Request, token_data: TokenRefresh, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    logout_user_use_case(db, current_user.id, token_data.refresh_token)

@router.get("/me", response_model=UserResponse)
@limiter.limit("60/minute")
def me(request: Request, current_user: User = Depends(get_current_active_user)):
    return current_user