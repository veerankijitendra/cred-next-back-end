from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import WithdrawalStatus
from app.db.base import Base
from app.db.mixins import BaseModelMixin
from app.models.lead import Lead
from app.models.user import User


class BonusWithdrawal(Base, BaseModelMixin):
    __tablename__ = "bonus_withdrawals"

    def __init__(
        self,
        *,
        id: UUID,
        lead_id: UUID,
        user_id: UUID,
        loan_type: str,
        disbursed_amount: Decimal,
        commission_rate: Decimal,
        gross_bonus: Decimal,
        tds_rate: Decimal,
        tds_amount: Decimal,
        net_bonus: Decimal,
        cooling_period_end_date: datetime,
        account_holder_name: str,
        payout_method: str = "upi",
        upi_id: str | None = None,
        account_number: str | None = None,
        ifsc_code: str | None = None,
        status: WithdrawalStatus = WithdrawalStatus.PENDING,
        transaction_reference: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id
        self.lead_id = lead_id
        self.user_id = user_id
        self.loan_type = loan_type
        self.disbursed_amount = disbursed_amount
        self.commission_rate = commission_rate
        self.gross_bonus = gross_bonus
        self.tds_rate = tds_rate
        self.tds_amount = tds_amount
        self.net_bonus = net_bonus
        self.cooling_period_end_date = cooling_period_end_date
        self.account_holder_name = account_holder_name
        self.payout_method = payout_method
        self.upi_id = upi_id
        self.account_number = account_number
        self.ifsc_code = ifsc_code
        self.status = status
        self.transaction_reference = transaction_reference
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    loan_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    disbursed_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=6, scale=4), nullable=False
    )

    gross_bonus: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    tds_rate: Mapped[Decimal] = mapped_column(
        Numeric(precision=6, scale=4), nullable=False
    )

    tds_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    net_bonus: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    cooling_period_end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    status: Mapped[WithdrawalStatus] = mapped_column(
        String(50),
        nullable=False,
        default=WithdrawalStatus.PENDING,
    )

    payout_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="upi",
    )

    upi_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )

    account_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )

    ifsc_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )

    account_holder_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    transaction_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )

    lead: Mapped[Lead] = relationship("Lead", foreign_keys=[lead_id])
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
