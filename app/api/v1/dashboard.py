from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.dashboard import DashboardRepository
from app.repositories.lead import LeadRepository
from app.schemas.lead import DashboardResponse, LeadListQuery
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def get_dashboard_service(session: AsyncSession = Depends(get_db)) -> DashboardService:
    return DashboardService(
        session=session,
        dashboard_repository=DashboardRepository(session=session),
        lead_repository=LeadRepository(session=session),
    )


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    query: LeadListQuery = Depends(),
    current_user: User = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardResponse:
    return await service.get_user_dashboard(
        current_user=current_user,
        page=query.page,
        page_size=query.page_size,
        search=query.search,
        status=query.status,
        loan_type=query.loan_type,
        application_type=query.application_type,
    )
