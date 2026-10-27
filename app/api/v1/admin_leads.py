from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.db.session import get_db
from app.models.user import User
from app.repositories.lead import LeadRepository
from app.repositories.lead_status_history import LeadStatusHistoryRepository
from app.schemas.admin_lead import AdminLeadListQuery, AdminLeadListResponse
from app.services.lead import LeadService

router = APIRouter(prefix="/admin/leads", tags=["Admin - Leads"])


def get_lead_service(session: AsyncSession = Depends(get_db)) -> LeadService:
    return LeadService(
        session=session,
        lead_repository=LeadRepository(session=session),
        lead_status_history_repository=LeadStatusHistoryRepository(session=session),
    )


@router.get("", response_model=AdminLeadListResponse)
async def get_admin_leads(
    query: AdminLeadListQuery = Depends(),
    current_admin: User = Depends(require_admin),
    service: LeadService = Depends(get_lead_service),
) -> AdminLeadListResponse:
    """
    Retrieve a paginated list of leads across all users with multi-criteria filters.
    Accessible only by administrators.
    """
    return await service.get_admin_leads(
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        status=query.status,
        loan_type=query.loan_type,
        start_date=query.start_date,
        end_date=query.end_date,
    )

