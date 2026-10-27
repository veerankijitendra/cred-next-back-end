from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import ApplicationType, LeadStatus, LoanType


class AdminLeadListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    search: str | None = Field(default=None, max_length=100)
    status: LeadStatus | None = None
    loan_type: LoanType | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "AdminLeadListQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")
        return self


class LeadUserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone_number: str
    reference_id: str


class AdminLeadItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: str
    application_type: ApplicationType
    loan_type: LoanType
    full_name: str
    contact_number: str
    email: str
    city: str
    loan_amount: Decimal
    monthly_income: Decimal
    credit_score: int | None
    status: LeadStatus
    created_by: LeadUserInfo
    referred_by: LeadUserInfo | None = None
    created_at: datetime
    updated_at: datetime


class AdminLeadListResponse(BaseModel):
    items: list[AdminLeadItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool

