from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

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


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Name
    email: EmailStr
    phone_number: MobileNumber
    password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=128,
        ),
    ]

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isupper() for char in value):
            raise ValueError("Password must contain an uppercase letter")

        if not any(char.islower() for char in value):
            raise ValueError("Password must contain a lowercase letter")

        if not any(char.isdigit() for char in value):
            raise ValueError("Password must contain a number")

        if not any(not char.isalnum() for char in value):
            raise ValueError("Password must contain at least one special character")

        return value
