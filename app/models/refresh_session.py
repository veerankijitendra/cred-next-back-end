from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import BaseModelMixin


class RefreshSession(Base, BaseModelMixin):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credentials: Mapped[list["RefreshCredential"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class RefreshCredential(Base, BaseModelMixin):
    __tablename__ = "refresh_credentials"
    __table_args__ = (Index("ix_refresh_credentials_session_created", "session_id", "created_at"),)

    session_id: Mapped[UUID] = mapped_column(ForeignKey("refresh_sessions.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[RefreshSession] = relationship(back_populates="credentials")
