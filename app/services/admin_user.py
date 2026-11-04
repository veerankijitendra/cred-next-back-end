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
    UpdateAdminUserRequest,
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
            updated_at=user.updated_at,
            updated_by_id=user.updated_by_user_id,
            updated_by_name=user.updated_by_name,
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
        # Security Policy: Super Admin accounts can ONLY be provisioned via server CLI scripts, NEVER via API/Postman/Browser
        if payload.role == UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(
                message="Super Administrator accounts cannot be created via the API or browser. Use the server CLI bootstrap script."
            )

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

        # Prevent deactivating own account
        if user.id == actor.id and not new_status:
            raise ConflictError("You cannot deactivate your own account.")

        # Last Super Admin Safeguard: Cannot deactivate the sole remaining active Super Admin
        if user.role == UserRoleEnum.SUPER_ADMIN and user.is_active and not new_status:
            active_super_admins = await self.repository.count_active_super_admins()
            if active_super_admins <= 1:
                raise ConflictError("Cannot deactivate the sole remaining active Super Admin.")

        user.is_active = new_status
        user.updated_by_user_id = actor.id
        user.updated_by_name = actor.name
        user.updated_at = datetime.now(UTC)

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
                "User account status toggled",
                extra={
                    "event": "admin.user_status_toggled",
                    "actor_user_id": str(actor.id),
                    "target_user_id": str(user.id),
                    "new_status": "active" if new_status else "inactive",
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

        # Security Policy: Users cannot be elevated to Super Admin via API
        if new_role == UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(
                message="Users cannot be promoted to Super Administrator via the API or browser. Role elevation to Super Admin must be executed via server CLI scripts."
            )

        user = await self.repository.get_by_id_or_ref(identifier)
        if user is None:
            raise NotFoundError("User was not found.")

        # Guard: Account must be verified before role can be updated
        if not user.is_verified and new_role != user.role:
            raise ConflictError(
                "Cannot update role for an unverified account. The user must complete email and phone verification first."
            )

        if user.role == UserRoleEnum.SUPER_ADMIN and new_role != UserRoleEnum.SUPER_ADMIN:
            active_super_admins = await self.repository.count_active_super_admins()
            if active_super_admins <= 1:
                raise ConflictError("Cannot demote the sole remaining active Super Admin.")

        user.role = new_role
        user.updated_by_user_id = actor.id
        user.updated_by_name = actor.name
        user.updated_at = datetime.now(UTC)
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

    async def update_user(
        self,
        *,
        identifier: str,
        payload: UpdateAdminUserRequest,
        actor: User,
    ) -> AdminUserItemResponse:
        if actor.role != UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(message="Only super administrators can modify user profiles.")

        user = await self.repository.get_by_id_or_ref(identifier)
        if user is None:
            raise NotFoundError("User was not found.")

        # Email update validation
        if payload.email is not None and payload.email.strip().lower() != user.email.lower():
            existing_email = await self.repository.get_by_email(payload.email.strip().lower())
            if existing_email and existing_email.id != user.id:
                raise ConflictError("Email is already registered to another user.")
            user.email = payload.email.strip().lower()

        # Phone update validation
        if payload.phone_number is not None and payload.phone_number.strip() != user.phone_number:
            existing_phone = await self.repository.get_by_phone(payload.phone_number.strip())
            if existing_phone and existing_phone.id != user.id:
                raise ConflictError("Phone number is already registered to another user.")
            user.phone_number = payload.phone_number.strip()

        # Name
        if payload.name is not None and payload.name.strip():
            user.name = payload.name.strip()

        # Title
        if payload.title is not None:
            user.title = payload.title.strip() if payload.title.strip() else None

        # Verification status change (processed before role check so Super Admin can verify & elevate in one operation)
        if payload.is_verified is not None:
            user.is_verified = payload.is_verified
            if payload.is_verified and payload.account_status is None and not user.is_active:
                user.is_active = True

        # Role change
        if payload.role is not None and payload.role != user.role:
            # Guard: Account must be verified before role can be updated
            if not user.is_verified:
                raise ConflictError(
                    "Cannot update role for an unverified account. The user must complete email and phone verification first."
                )
            if payload.role == UserRoleEnum.SUPER_ADMIN:
                raise ForbiddenError("Cannot promote user to Super Admin via the API.")
            if user.role == UserRoleEnum.SUPER_ADMIN and payload.role != UserRoleEnum.SUPER_ADMIN:
                active_super_admins = await self.repository.count_active_super_admins()
                if active_super_admins <= 1:
                    raise ConflictError("Cannot demote the sole remaining active Super Admin.")
            user.role = payload.role

        # Account status change
        if payload.account_status is not None:
            new_is_active = (payload.account_status == "active")
            if new_is_active != user.is_active:
                if user.id == actor.id and not new_is_active:
                    raise ConflictError("You cannot deactivate your own account.")
                if user.role == UserRoleEnum.SUPER_ADMIN and user.is_active and not new_is_active:
                    active_super_admins = await self.repository.count_active_super_admins()
                    if active_super_admins <= 1:
                        raise ConflictError("Cannot deactivate the sole remaining active Super Admin.")
                user.is_active = new_is_active
                if not new_is_active:
                    now = datetime.now(UTC)
                    await self.session.execute(
                        update(RefreshSession)
                        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
                        .values(revoked_at=now)
                    )

        # Audit tracking
        user.updated_by_user_id = actor.id
        user.updated_by_name = actor.name
        user.updated_at = datetime.now(UTC)

        try:
            await self.session.commit()
            await self.session.refresh(user)
            logger.info(
                "User profile updated by super admin",
                extra={
                    "event": "admin.user_updated",
                    "actor_user_id": str(actor.id),
                    "target_user_id": str(user.id),
                },
            )
            return self._to_item_response(user)
        except Exception:
            await self.session.rollback()
            raise

    async def verify_user(
        self,
        *,
        identifier: str,
        is_verified: bool,
        actor: User,
    ) -> AdminUserItemResponse:
        if actor.role != UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(message="Only super administrators can manually alter verification status.")

        user = await self.repository.get_by_id_or_ref(identifier)
        if user is None:
            raise NotFoundError("User was not found.")

        user.is_verified = is_verified
        if is_verified:
            user.is_active = True
        else:
            user.is_active = False
        user.updated_by_user_id = actor.id
        user.updated_by_name = actor.name
        user.updated_at = datetime.now(UTC)

        try:
            await self.session.commit()
            await self.session.refresh(user)
            logger.info(
                "User account verification toggled by super admin",
                extra={
                    "event": "admin.user_verified",
                    "actor_user_id": str(actor.id),
                    "target_user_id": str(user.id),
                    "is_verified": is_verified,
                },
            )
            return self._to_item_response(user)
        except Exception:
            await self.session.rollback()
            raise

    async def delete_user(
        self,
        *,
        identifier: str,
        actor: User,
    ) -> None:
        if actor.role != UserRoleEnum.SUPER_ADMIN:
            raise ForbiddenError(message="Only super administrators can delete user accounts.")

        user = await self.repository.get_by_id_or_ref(identifier)
        if user is None:
            raise NotFoundError("User was not found.")

        # Self-deletion safeguard
        if user.id == actor.id:
            raise ConflictError("You cannot delete your own account.")

        # Last Super Admin safeguard
        if user.role == UserRoleEnum.SUPER_ADMIN:
            active_super_admins = await self.repository.count_active_super_admins()
            if active_super_admins <= 1:
                raise ConflictError("Cannot delete the sole remaining active Super Admin.")

        # Integrity check: loan leads ownership
        leads_count = await self.repository.count_user_leads(user.id)
        if leads_count > 0:
            raise ConflictError(
                f"Cannot delete user with {leads_count} associated loan leads. Please deactivate the user or reassign leads before deletion."
            )

        try:
            await self.repository.delete(user)
            await self.session.commit()
            logger.info(
                "User permanently deleted",
                extra={
                    "event": "admin.user_deleted",
                    "actor_user_id": str(actor.id),
                    "deleted_user_id": str(user.id),
                },
            )
        except Exception:
            await self.session.rollback()
            raise
