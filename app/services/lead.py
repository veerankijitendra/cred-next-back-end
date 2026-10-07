import math
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationType, LeadStatus
from app.core.exceptions import ConflictError
from app.core.lead_id import generate_lead_id
from app.models.lead import Lead
from app.models.lead_status_history import LeadStatusHistory
from app.models.user import User
from app.repositories.lead import LeadRepository
from app.repositories.lead_status_history import LeadStatusHistoryRepository
from app.repositories.user import UserRepository
from app.schemas.lead import LeadListItemResponse, LeadListResponse, LeadRequest


class LeadService:
    def __init__(
        self,
        session: AsyncSession,
        lead_repository: LeadRepository,
        user_repository: UserRepository,
        lead_status_history_repository: LeadStatusHistoryRepository,
    ):
        self.session = session
        self.lead_repository = lead_repository
        self.user_repository = user_repository
        self.lead_status_history_repository = lead_status_history_repository

    async def create_lead(self, *, lead_request: LeadRequest, user: User):
        reference_id: UUID | None = None
        # ---------------------------------------------------------
        # 1. SELF APPLICATION
        # ---------------------------------------------------------

        if (
            lead_request.application_type == ApplicationType.SELF
            and lead_request.reference_id is not None
        ):
            raise ConflictError("Reference ID is not allowed for self applications.")

        # ---------------------------------------------------------
        # 2. REFERRAL APPLICATION
        # ---------------------------------------------------------

        if lead_request.application_type == ApplicationType.REFERRAL:
            if lead_request.reference_id is None:
                raise ConflictError(
                    "Reference ID is required for referral applications."
                )

            referrer = await self.user_repository.get_by_reference_id(
                reference_id=lead_request.reference_id
            )

            if referrer is None:
                raise ConflictError("Invalid referral reference ID")

            if referrer.reference_id == lead_request.reference_id:
                raise ConflictError("You cannot refer yourself.")

            reference_id = referrer.id

        lead_uuid = uuid4()

        lead = Lead(
            id=lead_uuid,
            lead_id=generate_lead_id(lead_id=lead_uuid),
            created_by_user_id=reference_id if reference_id else lead_uuid,
            referred_by_user_id=reference_id,
            application_type=lead_request.application_type,
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
