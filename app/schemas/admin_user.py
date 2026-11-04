from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.enums.user import UserRoleEnum

AdminUserRole = Literal["user", "admin", "super_admin"]
VerificationStatus = Literal["verified", "unverified"]
AccountStatus = Literal["active", "inactive"]


class AdminUserListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    search: str | None = Field(default=None, max_length=100)
    role: Literal["all", "user", "admin", "super_admin"] | None = "all"
    verification: Literal["all", "verified", "unverified"] | None = "all"
    status: Literal["all", "active", "inactive"] | None = "all"


class AdminUserStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_users: int = 0
    active_staff: int = 0
    verified_identities: int = 0
    pending_kyc: int = 0


class AdminUserItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    name: str
    title: str
    email: EmailStr
    phone_number: str
    role: UserRoleEnum
    verification_status: VerificationStatus
    account_status: AccountStatus
    created_at: datetime
    updated_at: datetime | None = None
    updated_by_id: UUID | None = None
    updated_by_name: str | None = None
    reference_id: str | None = None
    avatar_initials: str | None = None
    assigned_leads_count: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    stats: AdminUserStats


class CreateAdminUserRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone_number: Annotated[
        str,
        Field(
            min_length=10,
            max_length=10,
            pattern=r"^[6-9][0-9]{9}$",
            description="10-digit Indian phone number",
        ),
    ]
    role: UserRoleEnum = UserRoleEnum.ADMIN
    account_status: AccountStatus = "active"
    title: str | None = Field(default=None, max_length=100)
    temporary_password: str | None = Field(
        default=None,
        min_length=8,
        max_length=64,
        description="Optional temporary password. If omitted, one will be generated automatically.",
    )

    @field_validator("role")
    @classmethod
    def validate_assignable_role(cls, value: UserRoleEnum) -> UserRoleEnum:
        if value == UserRoleEnum.SUPER_ADMIN:
            raise ValueError(
                "Super Admin role cannot be created or assigned via the API. Use the server CLI bootstrap script."
            )
        return value


class AdminUserCreatedResponse(AdminUserItemResponse):
    temporary_password: str | None = None


class UpdateUserRoleRequest(BaseModel):
    role: UserRoleEnum

    @field_validator("role")
    @classmethod
    def validate_assignable_role(cls, value: UserRoleEnum) -> UserRoleEnum:
        if value == UserRoleEnum.SUPER_ADMIN:
            raise ValueError(
                "Users cannot be promoted to Super Admin via the API. Use the server CLI script."
            )
        return value


class UpdateAdminUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    phone_number: Annotated[
        str | None,
        Field(
            default=None,
            min_length=10,
            max_length=10,
            pattern=r"^[6-9][0-9]{9}$",
            description="10-digit Indian phone number",
        ),
    ] = None
    title: str | None = Field(default=None, max_length=100)
    role: UserRoleEnum | None = None
    account_status: AccountStatus | None = None
    is_verified: bool | None = None

    @field_validator("role")
    @classmethod
    def validate_assignable_role(cls, value: UserRoleEnum | None) -> UserRoleEnum | None:
        if value == UserRoleEnum.SUPER_ADMIN:
            raise ValueError(
                "Super Admin role cannot be created or assigned via the API. Use the server CLI bootstrap script."
            )
        return value


class VerifyAdminUserRequest(BaseModel):
    is_verified: bool = True
