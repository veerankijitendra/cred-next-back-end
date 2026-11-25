from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin, require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.repositories.acquisition_source import AcquisitionSourceRepository
from app.schemas.acquisition_source import (
    AcquisitionSourceItemResponse,
    AcquisitionSourceListResponse,
    CreateAcquisitionSourceRequest,
)
from app.services.acquisition_source import AcquisitionSourceService

router = APIRouter(prefix="/super-admin/sources", tags=["Super Admin - Sources"])
admin_sources_router = APIRouter(prefix="/admin/sources", tags=["Admin - Leads"])


def get_acquisition_source_service(
    session: AsyncSession = Depends(get_db),
) -> AcquisitionSourceService:
    return AcquisitionSourceService(
        session=session,
        repository=AcquisitionSourceRepository(session=session),
    )


@admin_sources_router.get("", response_model=AcquisitionSourceListResponse)
async def list_sources_for_admin(
    current_admin: User = Depends(require_admin),
    service: AcquisitionSourceService = Depends(get_acquisition_source_service),
) -> AcquisitionSourceListResponse:
    """
    List all configured acquisition sources for admin filtering dropdowns.
    Accessible by Admin and Super Admin.
    """
    return await service.list_sources()


@router.get("", response_model=AcquisitionSourceListResponse)
async def list_super_admin_sources(
    current_super_admin: User = Depends(require_super_admin),
    service: AcquisitionSourceService = Depends(get_acquisition_source_service),
) -> AcquisitionSourceListResponse:
    """
    List all acquisition sources with target QR URLs and live lead/user counts.
    Accessible strictly by Super Administrators.
    """
    return await service.list_sources()


@router.post(
    "",
    response_model=AcquisitionSourceItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_super_admin_source(
    payload: CreateAcquisitionSourceRequest,
    current_super_admin: User = Depends(require_super_admin),
    service: AcquisitionSourceService = Depends(get_acquisition_source_service),
) -> AcquisitionSourceItemResponse:
    """
    Add a new acquisition source for marketing QR tracking.
    Accessible strictly by Super Administrators.
    """
    return await service.create_source(payload=payload, actor=current_super_admin)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_super_admin_source(
    source_id: UUID,
    current_super_admin: User = Depends(require_super_admin),
    service: AcquisitionSourceService = Depends(get_acquisition_source_service),
) -> None:
    """
    Remove an acquisition source from active tracking.
    Historical leads and users retain their attributed source label.
    Accessible strictly by Super Administrators.
    """
    await service.delete_source(source_id=source_id, actor=current_super_admin)


@router.get("/{source_id}/qr")
async def download_source_qr_code(
    source_id: UUID,
    format: Literal["png", "svg"] = Query(default="png"),
    page: Literal["apply", "register"] = Query(default="apply"),
    ref: str | None = Query(default=None, max_length=45),
    current_super_admin: User = Depends(require_super_admin),
    service: AcquisitionSourceService = Depends(get_acquisition_source_service),
) -> Response:
    """
    Generate and download a high-resolution QR code file (PNG or SVG)
    for the specified acquisition source.
    Accessible strictly by Super Administrators.
    """
    content, media_type, filename = await service.generate_qr_file(
        source_id=source_id,
        file_format=format,
        page=page,
        ref=ref,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
