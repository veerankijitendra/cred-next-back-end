from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import LeadStatus
from app.db.base import Base
from app.db.mixins import BaseModelMixin
from app.models.lead import Lead
from app.models.user import User

"""
lead_id
old_status
new_status
changed_by_user_id
reason
lead
changed_by

"""


class LeadStatusHistory(Base, BaseModelMixin):
    def __init__(
        self,
        *,
        lead_id: UUID,
        changed_by_user_id: UUID,
        old_status: LeadStatus | None = None,
        new_status: LeadStatus = LeadStatus.LEAD_SUBMITTED,
        reason: str | None = None,
    ):
        self.lead_id = lead_id
        self.changed_by_user_id = changed_by_user_id

        self.old_status = old_status
        self.new_status = new_status

        self.reason = reason

    __tablename__ = "lead_status_history"

    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    old_status: Mapped[LeadStatus | None] = mapped_column(
        String(50), default=None, nullable=True
    )
    new_status: Mapped[LeadStatus] = mapped_column(
        String(50), default=LeadStatus.LEAD_SUBMITTED, nullable=False
    )
    changed_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    lead: Mapped[Lead] = relationship("Lead", foreign_keys=[lead_id])

    changed_by: Mapped[User] = relationship("User", foreign_keys=[changed_by_user_id])
