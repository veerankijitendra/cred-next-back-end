from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import BaseModelMixin


class AcquisitionSourceModel(Base, BaseModelMixin):
    __tablename__ = "acquisition_sources"

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        normalized_key: str,
        description: str | None = None,
        is_system: bool = False,
        created_by_user_id: UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id
        self.name = name
        self.normalized_key = normalized_key
        self.description = description
        self.is_system = is_system
        self.created_by_user_id = created_by_user_id
        if created_at is not None:
            self.created_at = created_at
        if updated_at is not None:
            self.updated_at = updated_at

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    normalized_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AcquisitionSourceModel(id={self.id}, name={self.name!r})>"
