from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.UserModel import User, RevokedToken
from app.core.security import decode_token, create_token_pair, TokenData
from app.schemas.AuthSchema import TokenRefresh, Token

def refresh_token_use_case(db: Session, token_data: TokenRefresh) -> Token:
    try:
        payload: TokenData = decode_token(token_data.refresh_token)
    except ValueError:
        raise ValueError("Refresh token inválido ou expirado")
    
    if payload.type != "refresh":
        raise ValueError("Tipo de token inválido")
    
    if payload.jti:
        revoked = db.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
        if revoked:
            raise ValueError("Refresh token revogado")
    
    user = db.query(User).filter(User.id == int(payload.sub)).first()
    if not user:
        raise ValueError("Usuário não encontrado")
    
    if not user.is_active:
        raise ValueError("Usuário inativo")
    
    if payload.jti:
        expires_at = datetime.fromtimestamp(payload.exp, tz=timezone.utc)
        revoked_token = RevokedToken(jti=payload.jti, expires_at=expires_at)
        db.add(revoked_token)
    
    new_token_pair = create_token_pair(user.id, user.role)
    
    try:
        db.commit()
    except IntegrityError:
        # Corrida: outro request já revogou este refresh token
        db.rollback()
        raise ValueError("Refresh token revogado")
    
    return Token(
        access_token=new_token_pair.access_token,
        refresh_token=new_token_pair.refresh_token
    )