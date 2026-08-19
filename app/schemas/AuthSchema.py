from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from pydantic.config import ConfigDict

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

class UserLogin(BaseModel):
    email: EmailStr
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