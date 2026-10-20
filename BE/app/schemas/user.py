import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import UserRole
from app.schemas.common import ORMModel


def _validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not any(ch.isdigit() for ch in value) or not any(ch.isalpha() for ch in value):
        raise ValueError("Password must contain both letters and numbers.")
    return value


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=160)


class UserRegister(UserBase):
    password: str = Field(max_length=128)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserCreate(UserRegister):
    role: UserRole = UserRole.ANALYST


class UserUpdateMe(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=160)


class UserAdminUpdate(UserUpdateMe):
    role: UserRole | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class UserRead(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    job_title: str | None
    organization: str | None
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserBrief(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
