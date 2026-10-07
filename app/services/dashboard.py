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

        summery = await self.repository.get_user_summary(user_id=current_user.id)

        return DashboardResponse(
            summary=DashboardSummaryResponse(
                bank_process=summery.get("bank_process", 0),
                customer_evaluation=summery.get("bank_process", 0),
                disbursed=summery.get("bank_process", 0),
                lead_submitted=summery.get("bank_process", 0),
                documents=summery.get("bank_process", 0),
                rejected=summery.get("bank_process", 0),
                total_leads=summery.get("bank_process", 0),
            ),
            referral=ReferralResponse(
                reference_id=current_user.reference_id,
                referral_link=current_user.reference_id,
            ),
        )
