from datetime import UTC, datetime
import logging
import math
import secrets
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.reference_id import generate_reference_id
from app.core.security import hash_password
from app.enums.user import UserRoleEnum
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.repositories.admin_user import AdminUserRepository
from app.schemas.admin_user import (
    AdminUserItemResponse,
    AdminUserListQuery,
    AdminUserListResponse,
    AdminUserStats,
    CreateAdminUserRequest,
)

logger = logging.getLogger(__name__)


class AdminUserService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: AdminUserRepository,
    ) -> None:
        self.session = session
        self.repository = repository

    @staticmethod
    def _get_initials(name: str) -> str:
        parts = [p for p in name.strip().split() if p]
        if len(parts) > 1:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        if parts:
            return parts[0][:2].upper()
        return "US"

    @staticmethod
    def _get_default_title(role: UserRoleEnum, custom_title: str | None) -> str:
        if custom_title and custom_title.strip():
            return custom_title.strip()
        if role == UserRoleEnum.SUPER_ADMIN:
            return "System Administrator"
        if role == UserRoleEnum.ADMIN:
            return "Operations Officer"
        return "Portal Borrower"

    @staticmethod
    def _format_user_id(user: User) -> str:
        ref = user.reference_id.replace("CNX-REF-", "").replace("CNX-", "").strip()
        suffix = ref[:6].upper() if len(ref) >= 6 else user.id.hex[:6].upper()
        return f"#USR-{suffix}"

    def _to_item_response(self, user: User, assigned_leads_count: int = 0) -> AdminUserItemResponse:
        return AdminUserItemResponse(
            id=user.id,
            user_id=self._format_user_id(user),
            name=user.name,
            title=self._get_default_title(user.role, user.title),
            email=user.email,
            phone_number=user.phone_number,
            role=user.role,
            verification_status="verified" if user.is_verified else "unverified",
            account_status="active" if user.is_active else "inactive",
            created_at=user.created_at or datetime.now(UTC),
            reference_id=user.reference_id,
            avatar_initials=self._get_initials(user.name),
            assigned_leads_count=assigned_leads_count,
        )

    async def get_users_directory(self, query: AdminUserListQuery) -> AdminUserListResponse:
        rows, total = await self.repository.get_users_paginated(
            page=query.page,
            page_size=query.page_size,
            search=query.search,
            role=query.role,
            verification=query.verification,
            status=query.status,
        )

        stats_dict = await self.repository.get_stats()
        total_pages = math.ceil(total / query.page_size) if total > 0 else 0

        items = [self._to_item_response(user, assigned_count) for user, assigned_count in rows]

        return AdminUserListResponse(
            items=items,
            page=query.page,
            page_size=query.page_size,
            total=total,
            total_pages=total_pages,
            stats=AdminUserStats.model_validate(stats_dict),
        )

    async def create_user(
        self,
        *,
        payload: CreateAdminUserRequest,
        actor: User,
    ) -> AdminUserItemResponse:
        existing_email = await self.repository.get_by_email(payload.email)
        if existing_email:
            raise ConflictError("Email is already registered.")

        existing_phone = await self.repository.get_by_phone(payload.phone_number)
        if existing_phone:
            raise ConflictError("Phone number is already registered.")

        user_id = uuid4()
        temp_secret = secrets.token_urlsafe(24)
        password_hash = hash_password(password=temp_secret)

        user = User(
            id=user_id,
            name=payload.name.strip(),
            email=payload.email.strip().lower(),
            phone_number=payload.phone_number.strip(),
            reference_id=generate_reference_id(user_id=user_id),
            password_hash=password_hash,
            role=payload.role,
            is_verified=False,
            is_active=(payload.account_status == "active"),
            title=payload.title.strip() if payload.title else None,
        )

        try:
            await self.repository.create(user)
            await self.session.commit()
            await self.session.refresh(user)

            logger.info(
                "Admin user created",
                extra={
                    "event": "admin.user_created",
                    "actor_user_id": str(actor.id),
                    "created_user_id": str(user.id),
                    "role": user.role.value,
                },
            )
            return self._to_item_response(user, assigned_leads_count=0)
        except Exception:
            await self.session.rollback()
            raise

    async def toggle_user_status(
        self,
        *,
        identifier: str,
        actor: User,
    ) -> AdminUserItemResponse:
        user = await self.repository.get_by_id_or_ref(identifier)
        if user is None:
            raise NotFoundError("User was not found.")

        new_status = not user.is_active
        user.is_active = new_status

        # If deactivated, revoke active sessions immediately
        if not new_status:
            now = datetime.now(UTC)
            await self.session.execute(
                update(RefreshSession)
                .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )

        try:
            await self.session.commit()
            await self.session.refresh(user)

            logger.info(
                "Admin user status updated",
                extra={
                    "event": "admin.user_status_toggled",
                    "actor_user_id": str(actor.id),
                    "target_user_id": str(user.id),
                    "new_status": "active" if user.is_active else "inactive",
                },
            )
            return self._to_item_response(user)
        except Exception:
            await self.session.rollback()
            raise
