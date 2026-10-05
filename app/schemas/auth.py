from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from app.core.constants import OTPChannel

MobileNumber = Annotated[
    str,
    Field(
        pattern=r"^[6-9]\d{9}$",
        min_length=10,
        max_length=10,
    ),
]

Name = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z]+(?:[ '-][A-Za-z]+)*$",
    ),
]

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Name
    email: EmailStr
    phone_number: MobileNumber
    password: Annotated[
        str,
        Field(
            min_length=PASSWORD_MIN_LENGTH,
            max_length=PASSWORD_MAX_LENGTH,
        ),
    ]

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isupper() for char in value):
            raise ValidationError("Password must contain an uppercase letter")

        if not any(char.islower() for char in value):
            raise ValidationError("Password must contain a lowercase letter")

        if not any(char.isdigit() for char in value):
            raise ValidationError("Password must contain a number")

        if not any(not char.isalnum() for char in value):
            raise ValidationError(
                "Password must contain at least one special character"
            )

        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone_number: str
    role: str


class RegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    reference_id: str
    verification_required: bool
    verification_channel: OTPChannel


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr

    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )


class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class VerifyOTPRequest(BaseModel):
    user_id: UUID
    channel: OTPChannel
    otp: Annotated[str, Field(min_length=6, max_length=6, pattern=r"^\d{6}$")]


class ResendOTPRequest(BaseModel):
    user_id: UUID
    channel: OTPChannel
