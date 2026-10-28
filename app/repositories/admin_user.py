from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.user import UserRoleEnum
from app.models.lead import Lead
from app.models.user import User


class AdminUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_users_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
        role: str | None = None,
        verification: str | None = None,
        status: str | None = None,
    ) -> tuple[list[tuple[User, int]], int]:
        filters = []

        if search and search.strip():
            s = f"%{search.strip()}%"
            filters.append(
                or_(
                    User.name.ilike(s),
                    User.email.ilike(s),
                    User.phone_number.ilike(s),
                    User.reference_id.ilike(s),
                    User.title.ilike(s),
                )
            )

        if role and role != "all":
            filters.append(User.role == role)

        if verification == "verified":
            filters.append(User.is_verified.is_(True))
        elif verification == "unverified":
            filters.append(User.is_verified.is_(False))

        if status == "active":
            filters.append(User.is_active.is_(True))
        elif status == "inactive":
            filters.append(User.is_active.is_(False))

        count_statement = select(func.count(User.id))
        if filters:
            count_statement = count_statement.where(*filters)
        count_result = await self.session.execute(count_statement)
        total = count_result.scalar_one()

        leads_count_subquery = (
            select(func.count(Lead.id))
            .where(or_(Lead.created_by_user_id == User.id, Lead.referred_by_user_id == User.id))
            .scalar_subquery()
        )

        offset = (page - 1) * page_size
        statement = (
            select(User, leads_count_subquery.label("assigned_leads_count"))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        if filters:
            statement = statement.where(*filters)

        result = await self.session.execute(statement)
        rows = [(row[0], row[1] or 0) for row in result.all()]

        return rows, total

    async def get_stats(self) -> dict[str, int]:
        stmt = select(
            func.count(User.id).label("total_users"),
            func.count(User.id)
            .filter(
                User.role.in_([UserRoleEnum.ADMIN, UserRoleEnum.SUPER_ADMIN]),
                User.is_active.is_(True),
            )
            .label("active_staff"),
            func.count(User.id).filter(User.is_verified.is_(True)).label("verified_identities"),
            func.count(User.id)
            .filter(or_(User.is_verified.is_(False), User.is_active.is_(False)))
            .label("pending_kyc"),
        )
        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "total_users": row.total_users or 0,
            "active_staff": row.active_staff or 0,
            "verified_identities": row.verified_identities or 0,
            "pending_kyc": row.pending_kyc or 0,
        }

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_ref(self, identifier: str) -> User | None:
        try:
            user_uuid = UUID(identifier)
            user = await self.get_by_id(user_uuid)
            if user:
                return user
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = select(User).where(
            or_(
                User.reference_id == identifier,
                User.reference_id.ilike(f"%{identifier.replace('#', '').strip()}%"),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone_number: str) -> User | None:
        stmt = select(User).where(User.phone_number == phone_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_status(self, user: User, is_active: bool) -> User:
        user.is_active = is_active
        await self.session.flush()
        return user

