import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import LoanType, WithdrawalStatus


class BonusBreakdownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lead_id: str
    loan_type: LoanType
    loan_type_label: str
    disbursed_amount: Decimal
    disbursed_at: datetime
    commission_rate: Decimal
    commission_percent_label: str
    gross_bonus: Decimal
    tds_rate: Decimal
    tds_percent_label: str
    tds_amount: Decimal
    net_bonus: Decimal
    cooling_period_working_days: int
    cooling_period_end_date: datetime
    remaining_working_days: int
    is_withdrawal_eligible: bool
    withdrawal_status: str
    withdrawal_id: UUID | None = None


class WithdrawRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lead_id: str = Field(min_length=5, max_length=50)
    upi_id: str = Field(
        min_length=3,
        max_length=100,
        description="Virtual Payment Address (e.g. customer@okhdfcbank, 9876543210@upi)",
    )
    account_holder_name: str = Field(min_length=2, max_length=150)
    payout_method: str = Field(default="upi")
    account_number: str | None = None
    ifsc_code: str | None = None

    @field_validator("upi_id")
    @classmethod
    def validate_upi_id(cls, value: str) -> str:
        clean = value.strip().lower()
        if not re.fullmatch(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$", clean):
            raise ValueError(
                "Invalid UPI ID format. Expected e.g. mobile@upi, name@okhdfcbank"
            )
        return clean

    @field_validator("account_holder_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Account holder name cannot be empty.")
        return clean


class WithdrawalItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_id: str
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
    created_at: datetime
    transaction_reference: str | None = None
    rejection_reason: str | None = None
    processed_at: datetime | None = None


class UserWithdrawalsSummaryResponse(BaseModel):
    total_earned_bonus: Decimal
    total_tds_deducted: Decimal
    total_withdrawn: Decimal
    pending_cooling_bonus: Decimal
    available_for_withdrawal: Decimal
    eligible_leads_count: int


class DisbursedLeadBonusItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lead_id: str
    borrower_name: str
    loan_type: LoanType
    disbursed_amount: Decimal
    disbursed_at: datetime
    bonus: BonusBreakdownResponse
