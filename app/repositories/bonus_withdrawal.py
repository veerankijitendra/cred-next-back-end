from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bonus_withdrawal import BonusWithdrawal


class BonusWithdrawalRepository:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, withdrawal: BonusWithdrawal) -> BonusWithdrawal:
        self.session.add(withdrawal)
        await self.session.flush()
        return withdrawal

    async def get_by_id(self, *, withdrawal_id: UUID) -> BonusWithdrawal | None:
        stmt = select(BonusWithdrawal).where(BonusWithdrawal.id == withdrawal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_lead_id(self, *, lead_id: UUID) -> BonusWithdrawal | None:
        stmt = select(BonusWithdrawal).where(BonusWithdrawal.lead_id == lead_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_lead_ids(
        self, *, lead_ids: list[UUID]
    ) -> dict[UUID, BonusWithdrawal]:
        if not lead_ids:
            return {}
        stmt = select(BonusWithdrawal).where(BonusWithdrawal.lead_id.in_(lead_ids))
        result = await self.session.execute(stmt)
        withdrawals = list(result.scalars().all())
        return {w.lead_id: w for w in withdrawals}

    async def get_user_withdrawals(self, *, user_id: UUID) -> list[BonusWithdrawal]:
        stmt = (
            select(BonusWithdrawal)
            .where(BonusWithdrawal.user_id == user_id)
            .order_by(BonusWithdrawal.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_withdrawals_paginated(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[BonusWithdrawal], int]:
        count_stmt = (
            select(func.count())
            .select_from(BonusWithdrawal)
            .where(BonusWithdrawal.user_id == user_id)
        )
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar_one()

        stmt = (
            select(BonusWithdrawal)
            .where(BonusWithdrawal.user_id == user_id)
            .order_by(BonusWithdrawal.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total
