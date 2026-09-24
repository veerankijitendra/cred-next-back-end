from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BaseModelMixin
from app.enums.user import UserRoleEnum


class User(BaseModelMixin, Base):
    __tablename__ = "users"

    def __init__(
        self,
        *,
        name: str,
        email: str,
        phone_number: str,
        password_hash: str | None = None,
        role: UserRoleEnum = UserRoleEnum.USER,
        refresh_token: str | None = None,
    ):
        self.name = name
        self.email = email
        self.phone_number = phone_number
        self.password_hash = password_hash
        self.role = role
        self.refresh_token = refresh_token

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    phone_number: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(300), nullable=True, default=None
    )
    role: Mapped[UserRoleEnum] = mapped_column(
        Enum(
            UserRoleEnum,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=UserRoleEnum.USER,
    )
    refresh_token: Mapped[str | None] = mapped_column(
        String(300), default=None, nullable=True
    )
