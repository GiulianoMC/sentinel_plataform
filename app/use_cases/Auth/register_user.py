from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.UserModel import User
from app.core.security import hash_password, create_token_pair
from app.schemas.AuthSchema import UserCreate, UserWithToken

def register_user_use_case(db: Session, user_data: UserCreate) -> UserWithToken:
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise ValueError("E-mail já cadastrado")
    
    hashed_password = hash_password(user_data.password)
    user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        role="user",
        is_active=True
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise ValueError("E-mail já cadastrado")
    
    token_pair = create_token_pair(user.id, user.role)
    
    return UserWithToken(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token
    )