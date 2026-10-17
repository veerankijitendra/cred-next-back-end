from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from app.core.config import settings
from app.core.constants import ApplicationType, LeadStatus, LoanType
from app.models.user import User
from app.repositories.dashboard import DashboardRepository
from app.repositories.lead import LeadRepository
from app.schemas.lead import (
    DashboardResponse,
    DashboardSummaryResponse,
    LeadListItemResponse,
    LeadListResponse,
    ReferralResponse,
)


class DashboardService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        dashboard_repository: DashboardRepository,
        lead_repository: LeadRepository,
    ) -> None:

        self.session = session
        self.repository = dashboard_repository
        self.lead_repository = lead_repository

    async def get_user_dashboard(
        self,
        *,
        current_user: User,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        status: LeadStatus | None = None,
        loan_type: LoanType | None = None,
        application_type: ApplicationType | None = None,
    ) -> DashboardResponse:

        summary = await self.repository.get_user_summary(user_id=current_user.id)
        leads, total = await self.lead_repository.get_user_leads_paginated(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            loan_type=loan_type,
            application_type=application_type,
        )
        total_pages = (total + page_size - 1) // page_size if total else 0
        referral_link = (
            f"{settings.frontend_base_url}/register?"
            f"{urlencode({'ref': current_user.reference_id})}"
        )

        return DashboardResponse(
            summary=DashboardSummaryResponse(
                bank_process=summary.get("bank_process", 0),
                customer_evaluation=summary.get("customer_evaluation", 0),
                disbursed=summary.get("disbursed", 0),
                lead_submitted=summary.get("lead_submitted", 0),
                documents=summary.get("documents", 0),
                rejected=summary.get("rejected", 0),
                total_leads=summary.get("total_leads", 0),
            ),
            referral=ReferralResponse(
                reference_id=current_user.reference_id,
                referral_link=referral_link,
            ),
            leads=LeadListResponse(
                items=[LeadListItemResponse.model_validate(lead) for lead in leads],
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )
