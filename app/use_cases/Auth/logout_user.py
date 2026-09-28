from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.UserModel import RevokedToken
from app.core.security import decode_token, TokenData

def logout_user_use_case(db: Session, user_id: int, refresh_token: str) -> None:
    try:
        payload: TokenData = decode_token(refresh_token)
    except ValueError:
        return
    
    if payload.type != "refresh":
        return
    
    if int(payload.sub) != user_id:
        return
    
    if payload.jti:
        existing = db.query(RevokedToken).filter(RevokedToken.jti == payload.jti).first()
        if not existing:
            expires_at = datetime.fromtimestamp(payload.exp, tz=timezone.utc)
            revoked_token = RevokedToken(jti=payload.jti, expires_at=expires_at)
            db.add(revoked_token)
            try:
                db.commit()
            except IntegrityError:
                # Corrida: outro request já revogou este token
                db.rollback()