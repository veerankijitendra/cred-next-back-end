import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    ValidationError,
    field_validator,
)

from app.core.constants import ApplicationType, LeadStatus, LoanType


class LeadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str = Field(
        min_length=2,
        max_length=150,
    )
    application_type: ApplicationType
    loan_type: LoanType

    reference_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=45,
    )

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

    loan_amount: Decimal = Field(
        gt=0,
        max_digits=15,
        decimal_places=2,
    )

    monthly_income: Decimal = Field(
        gt=0,
        max_digits=15,
        decimal_places=2,
    )

    credit_score: Annotated[
        int | None,
        Field(
            ge=300,
            le=900,
            description="Credit score between 300 and 900",
        ),
    ]

    @field_validator("contact_number")
    @classmethod
    def validate_contact_number(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Contact number must contain only digits")

        if value[0] not in "6789":
            raise ValueError("Contact number must start with 6, 7, 8, or 9")

        return value

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        value = value.strip()

        if not value.replace(" ", "").isalpha():
            raise ValueError("City must contain only alphabets and spaces")

        return value

    @field_validator("reference_id")
    @classmethod
    def normalize_reference_id(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return value.strip().upper()

    class LeadResponse(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        id: UUID
        lead_id: str

        application_type: ApplicationType
        loan_type: LoanType

        full_name: str
        contact_number: str
        email: EmailStr
        city: str

        loan_amount: Decimal
        monthly_income: Decimal
        credit_score: int | None

        status: LeadStatus

        created_by_user_id: UUID
        referred_by_user_id: UUID | None

        created_at: datetime
        updated_at: datetime


class LeadStatusItem(BaseModel):
    status: LeadStatus
    label: str
    completed: bool
    current: bool


class LeadStatusBoardResponse(BaseModel):
    lead_id: str
    current_status: LeadStatus
    status_board: list[LeadStatusItem]
    updated_at: datetime
