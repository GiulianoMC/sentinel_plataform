from datetime import datetime
import re
from typing_extensions import Annotated
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict
from pydantic.functional_validators import AfterValidator
from email_validator import validate_email, EmailNotValidError

_EMAIL_SIMPLES = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _email_valido(v: str) -> str:
    """Valida o email permitindo domínios de uso especial (.local, .test, etc.).

    O EmailStr padrão do Pydantic (email-validator) rejeita domínios
    reservados como 'sentinela.local' — usado no admin padrão — e não há
    opção para liberá-los na versão 2.x. Para esses casos, cai numa
    validação sintática leve.
    """
    try:
        info = validate_email(v, test_environment=True)
        return info.normalized
    except EmailNotValidError as e:
        if "special-use or reserved" not in str(e):
            raise
    if not _EMAIL_SIMPLES.fullmatch(v):
        raise ValueError("email inválido")
    return v.strip().lower()

EmailLocal = Annotated[str, AfterValidator(_email_valido)]

class UserCreate(BaseModel):
    email: EmailLocal
    password: str = Field(min_length=8, max_length=72)

class UserLogin(BaseModel):
    email: EmailLocal
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefresh(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class UserWithToken(UserResponse):
    access_token: str
    refresh_token: str

__all__ = [
    "UserCreate",
    "UserLogin",
    "Token",
    "TokenRefresh",
    "UserResponse",
    "UserWithToken",
]