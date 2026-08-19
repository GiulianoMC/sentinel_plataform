import pytest
from fastapi import HTTPException
from app.dependencies import get_current_user, get_optional_user, require_admin
from app.models.UserModel import User
from app.core.security import create_access_token, create_refresh_token
from fastapi.security import HTTPAuthorizationCredentials


def test_get_current_user_valid(db_session, test_user):
    access_token = create_access_token({"sub": str(test_user.id), "role": "user"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
    
    user = get_current_user(credentials, db_session)
    assert user.id == test_user.id
    assert user.email == test_user.email


def test_get_current_user_invalid_token(db_session):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token")
    
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials, db_session)
    assert exc.value.status_code == 401


def test_get_current_user_nonexistent(db_session):
    access_token = create_access_token({"sub": "999", "role": "user"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
    
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials, db_session)
    assert exc.value.status_code == 401


def test_get_current_user_inactive(db_session, test_user):
    test_user.is_active = False
    db_session.commit()
    
    access_token = create_access_token({"sub": str(test_user.id), "role": "user"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
    
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials, db_session)
    assert exc.value.status_code == 403


def test_get_current_user_refresh_token(db_session, test_user):
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "user"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=refresh_token)
    
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials, db_session)
    assert exc.value.status_code == 401


def test_get_optional_user_valid(db_session, test_user):
    access_token = create_access_token({"sub": str(test_user.id), "role": "user"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)
    
    user = get_optional_user(credentials, db_session)
    assert user is not None
    assert user.id == test_user.id


def test_get_optional_user_none(db_session):
    user = get_optional_user(None, db_session)
    assert user is None


def test_get_optional_user_invalid_token(db_session):
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token")
    user = get_optional_user(credentials, db_session)
    assert user is None


def test_require_admin_success(db_session, admin_user):
    user = require_admin(admin_user)
    assert user.role == "admin"


def test_require_admin_forbidden(db_session, test_user):
    with pytest.raises(HTTPException) as exc:
        require_admin(test_user)
    assert exc.value.status_code == 403