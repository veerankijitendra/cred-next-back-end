import logging
import re
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.acquisition_source import AcquisitionSourceModel
from app.models.user import User
from app.repositories.acquisition_source import (
    AcquisitionSourceRepository,
    normalize_source_key,
)
from app.schemas.acquisition_source import (
    AcquisitionSourceItemResponse,
    AcquisitionSourceListResponse,
    CreateAcquisitionSourceRequest,
)
from app.services.qr_code import QRCodeService

logger = logging.getLogger(__name__)


class AcquisitionSourceService:
    def __init__(
        self,
        session: AsyncSession,
        repository: AcquisitionSourceRepository | None = None,
    ):
        self.session = session
        self.repository = repository or AcquisitionSourceRepository(session=session)

    async def list_sources(self) -> AcquisitionSourceListResponse:
        rows = await self.repository.list_all_with_counts()
        items = [
            AcquisitionSourceItemResponse(
                id=src.id,
                name=src.name,
                description=src.description,
                is_system=src.is_system,
                target_url=QRCodeService.build_target_url(source_name=src.name),
                leads_count=leads_count,
                users_count=users_count,
                created_at=src.created_at,
            )
            for src, leads_count, users_count in rows
        ]
        return AcquisitionSourceListResponse(items=items, total=len(items))

    async def create_source(
        self,
        *,
        payload: CreateAcquisitionSourceRequest,
        actor: User,
    ) -> AcquisitionSourceItemResponse:
        existing = await self.repository.get_by_key_or_compact(name=payload.name)
        if existing is not None:
            raise ConflictError(
                f"Acquisition source '{existing.name}' already exists."
            )

        source = AcquisitionSourceModel(
            id=uuid4(),
            name=payload.name,
            normalized_key=normalize_source_key(payload.name),
            description=payload.description,
            is_system=False,
            created_by_user_id=actor.id,
        )

        await self.repository.create(source=source)
        await self.session.commit()
        await self.session.refresh(source)

        logger.info(
            "Acquisition source created",
            extra={
                "event": "acquisition_source.created",
                "actor_user_id": str(actor.id),
                "source_id": str(source.id),
                "source_name": source.name,
            },
        )

        return AcquisitionSourceItemResponse(
            id=source.id,
            name=source.name,
            description=source.description,
            is_system=source.is_system,
            target_url=QRCodeService.build_target_url(source_name=source.name),
            leads_count=0,
            users_count=0,
            created_at=source.created_at,
        )

    async def delete_source(self, *, source_id: UUID, actor: User) -> None:
        source = await self.repository.get_by_id(source_id=source_id)
        if source is None:
            raise NotFoundError("Acquisition source was not found.")

        if source.is_system:
            raise ConflictError(
                f"System default source '{source.name}' cannot be removed."
            )

        source_name = source.name
        await self.repository.delete(source=source)
        await self.session.commit()

        logger.info(
            "Acquisition source removed",
            extra={
                "event": "acquisition_source.deleted",
                "actor_user_id": str(actor.id),
                "source_id": str(source_id),
                "source_name": source_name,
            },
        )

    async def generate_qr_file(
        self,
        *,
        source_id: UUID,
        file_format: Literal["png", "svg"] = "png",
        page: Literal["apply", "register"] = "apply",
        ref: str | None = None,
    ) -> tuple[bytes, str, str]:
        source = await self.repository.get_by_id(source_id=source_id)
        if source is None:
            raise NotFoundError("Acquisition source was not found.")

        target_url = QRCodeService.build_target_url(
            source_name=source.name,
            page=page,
            ref=ref,
        )
        safe_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", source.name).strip("-") or "source"

        if file_format == "svg":
            content = QRCodeService.generate_svg(url=target_url)
            return content, "image/svg+xml", f"qr-{safe_slug}.svg"

        content = QRCodeService.generate_png(url=target_url)
        return content, "image/png", f"qr-{safe_slug}.png"
