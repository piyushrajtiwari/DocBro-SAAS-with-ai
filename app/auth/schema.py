import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

PHONE_REGEX = r"^\+?[0-9]{10,15}$"


class UserIN(BaseModel):
    """Public registration payload. The role is never client-chosen: new accounts are patients."""

    name: Annotated[str, Field(min_length=1, max_length=255, description="Enter the name")]
    email: Annotated[EmailStr | None, Field(description="Enter the email")] = None
    password: Annotated[str, Field(min_length=8, max_length=128, description="Enter the password")]
    phone: Annotated[str | None, Field(description="Enter the phone number")] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.lower() if value else value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = re.sub(r"[\s-]", "", value)
        if not re.match(PHONE_REGEX, value):
            raise ValueError("Phone must be 10-15 digits, optionally starting with +.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not (
            re.search(r"[A-Z]", value)
            and re.search(r"[a-z]", value)
            and re.search(r"\d", value)
            and re.search(r"[^A-Za-z0-9]", value)
        ):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, one number, and one special character."
            )
        return value


class UserOUT(BaseModel):
    id: Annotated[UUID, Field(description="User ID")]
    name: Annotated[str, Field(max_length=255)]
    email: EmailStr | None = None
    phone: str | None = None
    role: Literal["doctor", "medical", "patient", "docbro"]
    is_admin: bool
    is_verified: bool

    model_config = {"from_attributes": True}


class TokenOUT(BaseModel):
    access_token: str
    token_type: str = "bearer"
