from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import LeadStatus
from app.models.lead import Lead


class LeadRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, lead_id: UUID) -> Lead | None:
        query = select(Lead).where(Lead.id == lead_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_lead_id(self, lead_id: str) -> Lead | None:
        query = select(Lead).where(Lead.lead_id == lead_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_leads_by_status(self, status: LeadStatus) -> list[Lead]:
        query = select(Lead).where(Lead.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, lead: Lead) -> Lead:
        self.session.add(lead)

        await self.session.flush()
        return lead

    async def get_user_leads(self, user_id: UUID) -> list[Lead]:
        query = (
            select(Lead)
            .where(Lead.created_by_user_id == user_id)
            .order_by(Lead.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_referral_leads(self, user_id: UUID) -> list[Lead]:
        query = (
            select(Lead)
            .where(Lead.referred_by_user_id == user_id)
            .order_by(Lead.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, lead: Lead, status: LeadStatus) -> Lead:
        lead.status = status
        await self.session.flush()
        return lead

    async def delete(
        self,
        lead: Lead,
    ) -> None:

        await self.session.delete(lead)

        await self.session.flush()
