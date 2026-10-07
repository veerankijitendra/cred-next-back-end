from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApplicationType, LeadStatus
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

    async def get_user_leads_paginated(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        search: str | None = None,
        status: LeadStatus | None = None,
        application_type: ApplicationType | None = None,
    ) -> tuple[list[Lead], int]:
        filters = [Lead.created_by_user_id == user_id]

        if search:
            search_term = f"%{search.strip()}%"

            filters.append(
                or_(
                    Lead.email.ilike(search_term),
                    Lead.contact_number.ilike(search_term),
                    Lead.full_name.ilike(search_term),
                    Lead.city.ilike(search_term),
                )
            )

        if status:
            filters.append(Lead.status == status)

        if application_type:
            filters.append(Lead.application_type == application_type)

        count_statement = select(func.count(Lead.id)).where(*filters)

        count_result = await self.session.execute(count_statement)

        total = count_result.scalar_one()

        offset = (page - 1) * page_size

        statement = select(Lead).where(*filters).offset(offset).limit(page_size)

        result = await self.session.execute(statement)

        leads = list(result.scalars().all())

        return leads, total

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
