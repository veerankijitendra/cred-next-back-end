from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import WithdrawalStatus
from app.models.bonus_withdrawal import BonusWithdrawal
from app.models.lead import Lead
from app.models.user import User


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

    async def get_by_id_with_relations(
        self, *, withdrawal_id: UUID
    ) -> BonusWithdrawal | None:
        stmt = (
            select(BonusWithdrawal)
            .options(
                selectinload(BonusWithdrawal.lead),
                selectinload(BonusWithdrawal.user),
                selectinload(BonusWithdrawal.processed_by),
            )
            .where(BonusWithdrawal.id == withdrawal_id)
        )
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

    async def get_admin_withdrawals_paginated(
        self,
        *,
        page: int,
        page_size: int,
        status: WithdrawalStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[BonusWithdrawal], int]:
        filters = []
        if status:
            filters.append(BonusWithdrawal.status == status)

        if search:
            search_term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Lead.lead_id.ilike(search_term),
                    Lead.full_name.ilike(search_term),
                    User.name.ilike(search_term),
                    User.phone_number.ilike(search_term),
                    BonusWithdrawal.upi_id.ilike(search_term),
                    BonusWithdrawal.account_holder_name.ilike(search_term),
                    BonusWithdrawal.transaction_reference.ilike(search_term),
                )
            )

        count_stmt = (
            select(func.count(BonusWithdrawal.id))
            .join(Lead, BonusWithdrawal.lead_id == Lead.id)
            .join(User, BonusWithdrawal.user_id == User.id)
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar_one()

        stmt = (
            select(BonusWithdrawal)
            .join(Lead, BonusWithdrawal.lead_id == Lead.id)
            .join(User, BonusWithdrawal.user_id == User.id)
            .options(
                selectinload(BonusWithdrawal.lead),
                selectinload(BonusWithdrawal.user),
                selectinload(BonusWithdrawal.processed_by),
            )
            .order_by(BonusWithdrawal.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await self.session.execute(stmt)
        withdrawals = list(result.scalars().all())
        return withdrawals, total

    async def get_admin_withdrawal_stats(self) -> dict:
        stmt = select(
            BonusWithdrawal.status,
            func.count(BonusWithdrawal.id),
            func.coalesce(func.sum(BonusWithdrawal.net_bonus), 0),
            func.coalesce(func.sum(BonusWithdrawal.tds_amount), 0),
        ).group_by(BonusWithdrawal.status)
        result = await self.session.execute(stmt)
        rows = result.all()

        pending_count = 0
        pending_amount = Decimal("0.00")
        processed_count = 0
        processed_amount = Decimal("0.00")
        rejected_count = 0
        rejected_amount = Decimal("0.00")
        total_tds = Decimal("0.00")

        for status_val, count, net_sum, tds_sum in rows:
            net_dec = Decimal(str(net_sum))
            tds_dec = Decimal(str(tds_sum))
            total_tds += tds_dec
            if status_val == WithdrawalStatus.PENDING:
                pending_count = count
                pending_amount = net_dec
            elif status_val == WithdrawalStatus.PROCESSED:
                processed_count = count
                processed_amount = net_dec
            elif status_val == WithdrawalStatus.REJECTED:
                rejected_count = count
                rejected_amount = net_dec

        return {
            "pending_count": pending_count,
            "pending_amount": pending_amount,
            "processed_count": processed_count,
            "processed_amount": processed_amount,
            "rejected_count": rejected_count,
            "rejected_amount": rejected_amount,
            "total_tds_withheld": total_tds,
        }
