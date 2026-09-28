import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "A variável de ambiente 'SECRET_KEY' não foi definida. "
        "Defina-a no .env (ex: SECRET_KEY=<chave aleatória de 32+ bytes>) "
        "antes de iniciar a aplicação."
    )
ALGORITHM = os.environ.get("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
BCRYPT_ROUNDS = 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=BCRYPT_ROUNDS)

class TokenData(BaseModel):
    sub: str
    role: str
    jti: Optional[str] = None
    type: str
    exp: int
    iat: int

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp()), "type": "access", "iat": int(now.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid4())
    to_encode.update({"exp": int(expire.timestamp()), "type": "refresh", "jti": jti, "iat": int(now.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(**payload)
    except JWTError as e:
        raise ValueError(f"Token inválido: {str(e)}")

def create_token_pair(user_id: int, role: str) -> TokenPair:
    access_data = {"sub": str(user_id), "role": role}
    refresh_data = {"sub": str(user_id), "role": role}
    access_token = create_access_token(access_data)
    refresh_token = create_refresh_token(refresh_data)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)