from datetime import UTC, datetime
import logging
import math
import secrets
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.reference_id import generate_reference_id
from app.core.security import hash_password
from app.enums.user import UserRoleEnum
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.repositories.admin_user import AdminUserRepository
from app.schemas.admin_user import (
    AdminUserCreatedResponse,
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
    ) -> AdminUserCreatedResponse:
        # Privilege Escalation Guard: Only SUPER_ADMIN can create another SUPER_ADMIN
        if payload.role == UserRoleEnum.SUPER_ADMIN and actor.role != UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(message="Only super administrators can create or assign super admin roles.")

        existing_email = await self.repository.get_by_email(payload.email)
        if existing_email:
            raise ConflictError("Email is already registered.")

        existing_phone = await self.repository.get_by_phone(payload.phone_number)
        if existing_phone:
            raise ConflictError("Phone number is already registered.")

        user_id = uuid4()
        temp_password = payload.temporary_password or secrets.token_urlsafe(9)
        password_hash = hash_password(password=temp_password)

        # Internal staff created by administrative team are pre-verified so they can log in immediately
        is_staff = payload.role in {UserRoleEnum.ADMIN, UserRoleEnum.SUPER_ADMIN}
        is_verified = True if is_staff else False

        user = User(
            id=user_id,
            name=payload.name.strip(),
            email=payload.email.strip().lower(),
            phone_number=payload.phone_number.strip(),
            reference_id=generate_reference_id(user_id=user_id),
            password_hash=password_hash,
            role=payload.role,
            is_verified=is_verified,
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
            base_item = self._to_item_response(user, assigned_leads_count=0)
            return AdminUserCreatedResponse(
                **base_item.model_dump(),
                temporary_password=temp_password,
            )
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

        # Guard: Regular ADMIN cannot alter or deactivate a SUPER_ADMIN
        if user.role == UserRoleEnum.SUPER_ADMIN and actor.role != UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(message="Only super administrators can alter super admin accounts.")

        new_status = not user.is_active

        # Last Super Admin Safeguard: Cannot deactivate the sole remaining active Super Admin
        if user.role == UserRoleEnum.SUPER_ADMIN and user.is_active and not new_status:
            active_super_admins = await self.repository.count_active_super_admins()
            if active_super_admins <= 1:
                raise ConflictError("Cannot deactivate the sole remaining active Super Admin.")

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

    async def update_user_role(
        self,
        *,
        identifier: str,
        new_role: UserRoleEnum,
        actor: User,
    ) -> AdminUserItemResponse:
        if actor.role != UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(message="Only super administrators can change user roles.")

        user = await self.repository.get_by_id_or_ref(identifier)
        if user is None:
            raise NotFoundError("User was not found.")

        if user.role == UserRoleEnum.SUPER_ADMIN and new_role != UserRoleEnum.SUPER_ADMIN:
            active_super_admins = await self.repository.count_active_super_admins()
            if active_super_admins <= 1:
                raise ConflictError("Cannot demote the sole remaining active Super Admin.")

        user.role = new_role
        try:
            await self.repository.update_role(user, new_role)
            await self.session.commit()
            await self.session.refresh(user)
            logger.info(
                "User role updated",
                extra={
                    "event": "admin.user_role_updated",
                    "actor_user_id": str(actor.id),
                    "target_user_id": str(user.id),
                    "new_role": new_role.value,
                },
            )
            return self._to_item_response(user)
        except Exception:
            await self.session.rollback()
            raise
