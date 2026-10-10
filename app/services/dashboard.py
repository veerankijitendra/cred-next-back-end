from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.dashboard import DashboardRepository
from app.schemas.lead import (
    DashboardResponse,
    DashboardSummaryResponse,
    ReferralResponse,
)


class DashboardService:
    def __init__(
        self, *, session: AsyncSession, dashboard_repository: DashboardRepository
    ) -> None:

        self.session = session
        self.repository = dashboard_repository

    async def get_user_dashboard(self, *, current_user: User) -> DashboardResponse:

        summary = await self.repository.get_user_summary(user_id=current_user.id)

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
                referral_link=current_user.reference_id,
            ),
        )
