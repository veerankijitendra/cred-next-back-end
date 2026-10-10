from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.lead import LeadRepository
from app.repositories.lead_status_history import LeadStatusHistoryRepository
from app.schemas.lead import LeadRequest, LeadResponse
from app.services.lead import LeadService

router = APIRouter(prefix="/lead", tags=["Leads"])


def get_lead_service(session: AsyncSession = Depends(get_db)) -> LeadService:
    return LeadService(
        session=session,
        lead_repository=LeadRepository(session=session),
        lead_status_history_repository=LeadStatusHistoryRepository(session=session),
    )


@router.post("")
async def create_lead(
    request: LeadRequest,
    current_user: User = Depends(get_current_user),
    service: LeadService = Depends(get_lead_service),
) -> LeadResponse:
    lead = await service.create_lead(lead_request=request, user=current_user)

    return LeadResponse.model_validate(lead)
