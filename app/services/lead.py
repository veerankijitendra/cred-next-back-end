from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationType
from app.core.exceptions import ConflictError
from app.core.lead_id import generate_lead_id
from app.models.lead import Lead
from app.repositories.lead import LeadRepository
from app.repositories.user import UserRepository
from app.schemas.lead import LeadRequest


class LeadService:
    def __init__(
        self,
        session: AsyncSession,
        LeadRepository: LeadRepository,
        UserRepository: UserRepository,
    ):
        self.session = session
        self.lead_repository = LeadRepository
        self.user_repository = UserRepository

    async def create_lead(self, *, lead_request: LeadRequest):
        reference_id: UUID | None = None
        # ---------------------------------------------------------
        # 1. SELF APPLICATION
        # ---------------------------------------------------------

        if lead_request.application_type == ApplicationType.SELF:
            if lead_request.reference_id is not None:
                raise ConflictError(
                    "Reference ID is not allowed for self applications."
                )

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
