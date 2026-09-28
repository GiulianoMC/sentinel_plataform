import pytest
from sqlalchemy.orm import Session
from app.use_cases.Auth.register_user import register_user_use_case
from app.use_cases.Auth.login_user import login_user_use_case
from app.use_cases.Auth.refresh_token import refresh_token_use_case
from app.use_cases.Auth.logout_user import logout_user_use_case
from app.schemas.AuthSchema import UserCreate, UserLogin, TokenRefresh
from app.models.UserModel import User, RevokedToken
from app.core.security import create_refresh_token, decode_token
from datetime import datetime, timezone


def test_register_user_use_case(db_session):
    user_data = UserCreate(email="new@example.com", password="senha123")
    result = register_user_use_case(db_session, user_data)
    
    assert result.email == "new@example.com"
    assert result.role == "user"
    assert result.is_active is True
    assert result.access_token is not None
    assert result.refresh_token is not None


def test_register_user_use_case_duplicate(db_session):
    user_data = UserCreate(email="dup@example.com", password="senha123")
    register_user_use_case(db_session, user_data)
    
    with pytest.raises(ValueError, match="já cadastrado"):
        register_user_use_case(db_session, user_data)


def test_login_user_use_case(db_session, test_user):
    credentials = UserLogin(email="test@example.com", password="senha123")
    result = login_user_use_case(db_session, credentials)
    
    assert result.access_token is not None
    assert result.refresh_token is not None


def test_login_user_use_case_wrong_password(db_session, test_user):
    credentials = UserLogin(email="test@example.com", password="wrong")
    with pytest.raises(ValueError, match="Credenciais inválidas"):
        login_user_use_case(db_session, credentials)


def test_login_user_use_case_inactive(db_session, test_user):
    test_user.is_active = False
    db_session.commit()
    
    credentials = UserLogin(email="test@example.com", password="senha123")
    with pytest.raises(ValueError, match="Usuário inativo"):
        login_user_use_case(db_session, credentials)


def test_refresh_token_use_case(db_session, test_user):
    # Create a valid refresh token
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "user"})
    
    token_data = TokenRefresh(refresh_token=refresh_token)
    result = refresh_token_use_case(db_session, token_data)
    
    assert result.access_token is not None
    assert result.refresh_token is not None
    # Old token should be revoked
    old_payload = decode_token(refresh_token)
    revoked = db_session.query(RevokedToken).filter(RevokedToken.jti == old_payload.jti).first()
    assert revoked is not None


def test_refresh_token_use_case_revoked(db_session, test_user):
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "user"})
    payload = decode_token(refresh_token)
    
    revoked = RevokedToken(jti=payload.jti, expires_at=datetime.fromtimestamp(payload.exp, tz=timezone.utc))
    db_session.add(revoked)
    db_session.commit()
    
    token_data = TokenRefresh(refresh_token=refresh_token)
    with pytest.raises(ValueError, match="revogado"):
        refresh_token_use_case(db_session, token_data)


def test_refresh_token_use_case_invalid(db_session):
    token_data = TokenRefresh(refresh_token="invalid.token")
    with pytest.raises(ValueError, match="inválido"):
        refresh_token_use_case(db_session, token_data)


def test_logout_user_use_case(db_session, test_user):
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "user"})
    
    logout_user_use_case(db_session, test_user.id, refresh_token)
    
    payload = decode_token(refresh_token)
    revoked = db_session.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
    assert revoked is not None


def test_logout_user_use_case_wrong_user(db_session, test_user, other_user):
    refresh_token = create_refresh_token({"sub": str(other_user.id), "role": "user"})
    
    # Should not raise, just silently return
    logout_user_use_case(db_session, test_user.id, refresh_token)
    
    # Token should not be revoked since sub doesn't match
    payload = decode_token(refresh_token)
    revoked = db_session.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
    assert revoked is None