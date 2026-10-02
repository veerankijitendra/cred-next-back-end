import re
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationError,
    field_validator,
)


class LeadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str

    @classmethod
    @field_validator("full_name")
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValidationError("Full name cannot be empty.")

        if not re.fullmatch(r"[A-Z]+(?: [A-Z]+)*", value):
            raise ValidationError(
                "Full name must contain uppercase alphabets and spaces only"
            )

        return value

    contact_number: Annotated[
        str,
        Field(
            min_length=10,
            max_length=10,
            pattern=r"^[6-9][0-9]{9}$",
            description="10-digit Indian phone number",
        ),
    ]

    email: EmailStr

    city: Annotated[
        str,
        Field(
            min_length=2,
            max_length=200,
            pattern=r"^[A-Za-z]+(?: [A-Za-z]+)*$",
            description="City name with alphabets and spaces only",
        ),
    ]

    loan_amount: Annotated[
        float,
        Field(
            gt=0,
            description="Loan amount in INR",
        ),
    ]

    monthly_income: float | None = Field(
        gt=0,
        description="Monthly income in INR",
    )

    credit_score: Annotated[
        int | None,
        Field(
            ge=300,
            le=900,
            description="Credit score between 300 and 900",
        ),
    ]
