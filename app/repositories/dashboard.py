from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import LeadStatus
from app.models.lead import Lead


class DashboardRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def get_user_summary(self, *, user_id: UUID) -> dict[str, int]:

        statement: Select = select(
            func.count(Lead.id).label("total_leads"),
            func.count(Lead.id)
            .filter(Lead.status == LeadStatus.LEAD_SUBMITTED)
            .label("lead_submitted"),
            func.count(Lead.id)
            .filter(Lead.status == LeadStatus.DOCUMENTS)
            .label("documents"),
            func.count(Lead.id)
            .filter(Lead.status == LeadStatus.CUSTOMER_EVALUATION)
            .label("customer_evaluation"),
            func.count(Lead.id)
            .filter(Lead.status == LeadStatus.DISBURSED)
            .label("disbursed"),
            func.count(Lead.id)
            .filter(Lead.status == LeadStatus.REJECTED)
            .label("rejected"),
            func.count(Lead.id)
            .filter(Lead.status == LeadStatus.BANK_PROCESS)
            .label("bank_process"),
        ).where(Lead.id == user_id)

        result = await self.session.execute(statement)

        row = result.one()

        return {
            "lead_submitted": row.lead_submitted,
            "total_leads": row.total_leads,
            "documents": row.documents,
            "customer_evaluation": row.customer_evaluation,
            "disbursed": row.disbursed,
            "rejected": row.rejected,
            "bank_process": row.bank_process,
        }
