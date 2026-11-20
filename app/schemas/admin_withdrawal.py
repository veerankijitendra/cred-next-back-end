from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import WithdrawalStatus
from app.schemas.admin_lead import LeadUserInfo


class AdminWithdrawalQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: WithdrawalStatus | None = None
    search: str | None = Field(default=None, max_length=100)


class AdminWithdrawalItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: str
    borrower_name: str
    loan_type: str
    disbursed_amount: Decimal
    commission_rate: Decimal
    gross_bonus: Decimal
    tds_rate: Decimal
    tds_amount: Decimal
    net_bonus: Decimal
    status: WithdrawalStatus
    payout_method: str
    upi_id: str | None = None
    account_number: str | None = None
    ifsc_code: str | None = None
    account_holder_name: str
    cooling_period_end_date: datetime
    is_cooling_period_passed: bool
    created_at: datetime

    # Recipient user / partner information
    user: LeadUserInfo

    # Audit & Payout Processing information
    transaction_reference: str | None = None
    rejection_reason: str | None = None
    notes: str | None = None
    processed_at: datetime | None = None
    processed_by_admin_id: UUID | None = None
    processed_by_name: str | None = None


class AdminWithdrawalStats(BaseModel):
    pending_count: int = 0
    pending_amount: Decimal = Decimal("0.00")
    processed_count: int = 0
    processed_amount: Decimal = Decimal("0.00")
    rejected_count: int = 0
    rejected_amount: Decimal = Decimal("0.00")
    total_tds_withheld: Decimal = Decimal("0.00")


class AdminProcessWithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(
        pattern="^(process|reject)$",
        description="'process' to confirm payout, 'reject' to decline request",
    )
    transaction_reference: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Mandatory when action is 'process' (e.g. UPI UTR number)",
    )
    rejection_reason: str | None = Field(
        default=None,
        min_length=3,
        max_length=255,
        description="Mandatory when action is 'reject'",
    )
    notes: str | None = Field(default=None, max_length=255)


class AdminWithdrawalListResponse(BaseModel):
    items: list[AdminWithdrawalItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool
    stats: AdminWithdrawalStats | None = None
