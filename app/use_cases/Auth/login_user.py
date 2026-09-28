from sqlalchemy.orm import Session

from app.models.UserModel import User
from app.core.security import verify_password, create_token_pair
from app.schemas.AuthSchema import UserLogin, Token

def login_user_use_case(db: Session, credentials: UserLogin) -> Token:
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user:
        raise ValueError("Credenciais inválidas")
    
    if not verify_password(credentials.password, user.hashed_password):
        raise ValueError("Credenciais inválidas")
    
    if not user.is_active:
        raise ValueError("Usuário inativo")
    
    token_pair = create_token_pair(user.id, user.role)
    
    return Token(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token
    )