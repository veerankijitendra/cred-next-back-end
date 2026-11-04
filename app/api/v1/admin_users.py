from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin, require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.repositories.admin_user import AdminUserRepository
from app.schemas.admin_user import (
    AdminUserCreatedResponse,
    AdminUserItemResponse,
    AdminUserListQuery,
    AdminUserListResponse,
    CreateAdminUserRequest,
    UpdateAdminUserRequest,
    UpdateUserRoleRequest,
    VerifyAdminUserRequest,
)
from app.services.admin_user import AdminUserService

router = APIRouter(prefix="/admin/users", tags=["Admin - Users"])


def get_admin_user_service(session: AsyncSession = Depends(get_db)) -> AdminUserService:
    return AdminUserService(
        session=session,
        repository=AdminUserRepository(session=session),
    )


@router.get("", response_model=AdminUserListResponse)
async def get_admin_users(
    query: AdminUserListQuery = Depends(),
    current_admin: User = Depends(require_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserListResponse:
    """
    Retrieve paginated user directory with multi-criteria filters and high-level KPI metrics.
    Accessible only by administrators.
    """
    return await service.get_users_directory(query=query)


@router.post("", response_model=AdminUserCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: CreateAdminUserRequest,
    current_admin: User = Depends(require_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserCreatedResponse:
    """
    Create a new staff or borrower user account.
    Accessible only by administrators.
    """
    return await service.create_user(payload=payload, actor=current_admin)


@router.patch("/{user_id}/status", response_model=AdminUserItemResponse)
async def update_admin_user_status(
    user_id: str,
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserItemResponse:
    """
    Toggle user account status between active and inactive.
    Deactivating a user automatically revokes active authentication sessions.
    Accessible strictly by Super Administrators.
    """
    return await service.toggle_user_status(identifier=user_id, actor=current_super_admin)


@router.post("/{user_id}/toggle-status", response_model=AdminUserItemResponse)
async def toggle_admin_user_status(
    user_id: str,
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserItemResponse:
    """
    Toggle user account status between active and inactive (POST alias).
    Accessible strictly by Super Administrators.
    """
    return await service.toggle_user_status(identifier=user_id, actor=current_super_admin)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    user_id: str,
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> None:
    """
    Permanently delete a user account and associated refresh sessions.
    Accessible strictly by Super Administrators.
    """
    await service.delete_user(identifier=user_id, actor=current_super_admin)


@router.patch("/{user_id}/role", response_model=AdminUserItemResponse)
async def update_admin_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserItemResponse:
    """
    Promote, demote, or change a user's role.
    Accessible strictly by Super Administrators.
    """
    return await service.update_user_role(
        identifier=user_id, new_role=payload.role, actor=current_super_admin
    )


@router.patch("/{user_id}", response_model=AdminUserItemResponse)
async def update_admin_user(
    user_id: str,
    payload: UpdateAdminUserRequest,
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserItemResponse:
    """
    Update user profile data (name, email, phone number, title, role, account status).
    Automatically logs updated_at timestamp and records the super administrator actor.
    Accessible strictly by Super Administrators.
    """
    return await service.update_user(
        identifier=user_id,
        payload=payload,
        actor=current_super_admin,
    )


@router.patch("/{user_id}/verify", response_model=AdminUserItemResponse)
async def verify_admin_user(
    user_id: str,
    payload: VerifyAdminUserRequest = VerifyAdminUserRequest(is_verified=True),
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserItemResponse:
    """
    Manually update user verification status.
    Accessible strictly by Super Administrators.
    """
    return await service.verify_user(
        identifier=user_id,
        is_verified=payload.is_verified,
        actor=current_super_admin,
    )


@router.put("/{user_id}", response_model=AdminUserItemResponse)
async def put_admin_user(
    user_id: str,
    payload: UpdateAdminUserRequest,
    current_super_admin: User = Depends(require_super_admin),
    service: AdminUserService = Depends(get_admin_user_service),
) -> AdminUserItemResponse:
    """
    Update user profile data (PUT alias).
    Accessible strictly by Super Administrators.
    """
    return await service.update_user(
        identifier=user_id,
        payload=payload,
        actor=current_super_admin,
    )


