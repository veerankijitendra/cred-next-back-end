import math
import re
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationType, LeadStatus
from app.core.exceptions import ConflictError, ForbiddenError
from app.core.lead_id import generate_lead_id
from app.models.lead import Lead
from app.models.lead_status_history import LeadStatusHistory
from app.models.user import User
from app.repositories.lead import LeadRepository
from app.repositories.lead_status_history import LeadStatusHistoryRepository
from app.schemas.lead import LeadListItemResponse, LeadListResponse, LeadRequest


class LeadService:
    def __init__(
        self,
        session: AsyncSession,
        lead_repository: LeadRepository,
        lead_status_history_repository: LeadStatusHistoryRepository,
    ):
        self.session = session
        self.lead_repository = lead_repository
        self.lead_status_history_repository = lead_status_history_repository

    async def create_lead(self, *, lead_request: LeadRequest, user: User):
        def normalize_phone(value: str) -> str:
            digits = re.sub(r"\D", "", value)
            if len(digits) == 12 and digits.startswith("91"):
                return digits[-10:]
            if len(digits) == 11 and digits.startswith("0"):
                return digits[-10:]
            return digits

        is_self_application = normalize_phone(lead_request.contact_number) == normalize_phone(user.phone_number)
        if lead_request.application_type == ApplicationType.SELF and not is_self_application:
            raise ConflictError("Self applications must use the authenticated account phone number.")
        if lead_request.reference_id and lead_request.reference_id != user.reference_id:
            raise ForbiddenError(message="A referral can only be attributed to the authenticated account.")

        application_type = ApplicationType.SELF if is_self_application else ApplicationType.REFERRAL

        lead_uuid = uuid4()

        lead = Lead(
            id=lead_uuid,
            lead_id=generate_lead_id(lead_id=lead_uuid),
            created_by_user_id=user.id,
            referred_by_user_id=None if is_self_application else user.id,
            application_type=application_type,
            loan_type=lead_request.loan_type,
            full_name=lead_request.full_name,
            email=lead_request.email,
            contact_number=lead_request.contact_number,
            city=lead_request.city,
            loan_amount=lead_request.loan_amount,
            monthly_income=lead_request.monthly_income,
            credit_score=lead_request.credit_score,
        )

        try:
            await self.lead_repository.create(lead=lead)

            await self.session.commit()
            await self.session.refresh(lead)

            return lead

        except IntegrityError:
            await self.session.rollback()

            raise ConflictError("Unable to create lead because of a conflicting record")

    async def get_user_leads(
        self,
        *,
        page: int,
        page_size: int,
        user_id: UUID,
        search: str | None = None,
        status: LeadStatus | None = None,
        application_type: ApplicationType | None = None,
    ) -> LeadListResponse:

        leads, total = await self.lead_repository.get_user_leads_paginated(
            user_id=user_id,
            search=search,
            status=status,
            application_type=application_type,
            page_size=page_size,
            page=page,
        )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return LeadListResponse(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
            items=[LeadListItemResponse.model_validate(lead) for lead in leads],
        )

    async def update_lead_status(
        self,
        *,
        lead: Lead,
        new_status: LeadStatus,
        changed_by_user: User,
        reason: str | None = None,
    ) -> Lead:

        if lead.status == new_status:
            raise ConflictError("Lead is already in this status")

        old_status = lead.status

        history: LeadStatusHistory = LeadStatusHistory(
            new_status=new_status,
            old_status=old_status,
            lead_id=lead.id,
            changed_by_user_id=changed_by_user.id,
            reason=reason,
        )

        try:
            # 1.Update the current status
            lead.status = new_status

            await self.lead_repository.update_status(lead=lead, status=new_status)

            # 2. Create history record
            await self.lead_status_history_repository.create(history=history)

            # 3. Commit BOTH operations together

            await self.session.commit()

            await self.session.refresh(lead)

            return lead
        except Exception:
            await self.session.rollback()

            raise
