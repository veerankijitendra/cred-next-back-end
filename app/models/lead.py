from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ApplicationType, LeadStatus, LoanType
from app.db.base import Base
from app.db.mixins import BaseModelMixin
from app.models.user import User


class Lead(Base, BaseModelMixin):
    __tablename__ = "leads"

    def __init__(
        self,
        *,
        id: UUID,
        lead_id: str,
        created_by_user_id: UUID,
        referred_by_user_id: UUID | None,
        application_type: ApplicationType,
        loan_type: LoanType,
        full_name: str,
        email: str,
        contact_number: str,
        city: str,
        loan_amount: Decimal,
        monthly_income: Decimal,
        credit_score: int | None = None,
        status: LeadStatus = LeadStatus.LEAD_SUBMITTED,
    ):
        self.id = id
        self.lead_id = lead_id
        self.created_by_user_id = created_by_user_id
        self.referred_by_user_id = referred_by_user_id
        self.application_type = application_type
        self.loan_type = loan_type
        self.full_name = full_name
        self.email = email
        self.contact_number = contact_number
        self.city = city
        self.loan_amount = loan_amount
        self.monthly_income = monthly_income
        self.credit_score = credit_score
        self.status = status

    def __repr__(self):
        return f"<Lead(id={self.id})>"

    lead_id: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)

    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    referred_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    application_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    loan_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(String(250), nullable=False)

    email: Mapped[str] = mapped_column(String(100), nullable=False)

    contact_number: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    city: Mapped[str] = mapped_column(String(100), nullable=False)

    loan_amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    monthly_income: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=2), nullable=False
    )

    credit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[LeadStatus] = mapped_column(
        String(100),
        nullable=False,
        default=LeadStatus.LEAD_SUBMITTED,
    )

    created_by: Mapped[User] = relationship("User", foreign_keys=[created_by_user_id])

    referred_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[referred_by_user_id]
    )
