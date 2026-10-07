from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_status_history import LeadStatusHistory


class LeadStatusHistoryRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, history: LeadStatusHistory) -> LeadStatusHistory:
        self.session.add(history)

        await self.session.flush()

        return history

    async def get_by_lead_id(self, *, lead_id: UUID) -> list[LeadStatusHistory]:

        statement: Select = (
            select(LeadStatusHistory)
            .where(LeadStatusHistory.lead_id == lead_id)
            .order_by(LeadStatusHistory.created_at.asc())
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())
