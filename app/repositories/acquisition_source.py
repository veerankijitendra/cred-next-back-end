import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AcquisitionSource
from app.models.acquisition_source import AcquisitionSourceModel
from app.models.lead import Lead
from app.models.user import User


def normalize_source_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def compact_source_key(name: str) -> str:
    return re.sub(r"[\s_-]+", "", name.strip().lower())


class AcquisitionSourceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, *, source: AcquisitionSourceModel) -> AcquisitionSourceModel:
        self.session.add(source)
        return source

    async def delete(self, *, source: AcquisitionSourceModel) -> None:
        await self.session.delete(source)

    async def get_by_id(self, *, source_id: UUID) -> AcquisitionSourceModel | None:
        stmt = select(AcquisitionSourceModel).where(AcquisitionSourceModel.id == source_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_key_or_compact(self, *, name: str) -> AcquisitionSourceModel | None:
        clean_key = normalize_source_key(name)
        compact = compact_source_key(name)
        stmt = select(AcquisitionSourceModel).where(
            or_(
                AcquisitionSourceModel.normalized_key == clean_key,
                func.replace(
                    func.replace(
                        func.replace(AcquisitionSourceModel.normalized_key, "-", ""),
                        "_",
                        "",
                    ),
                    " ",
                    "",
                )
                == compact,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all_with_counts(
        self,
    ) -> list[tuple[AcquisitionSourceModel, int, int]]:
        sources_stmt = select(AcquisitionSourceModel).order_by(
            AcquisitionSourceModel.is_system.desc(),
            AcquisitionSourceModel.created_at.asc(),
        )
        sources_result = await self.session.execute(sources_stmt)
        sources = list(sources_result.scalars().all())

        lead_counts_stmt = select(Lead.source, func.count(Lead.id)).group_by(Lead.source)
        lead_counts_res = await self.session.execute(lead_counts_stmt)
        lead_counts = {str(src): int(cnt) for src, cnt in lead_counts_res.all()}

        user_counts_stmt = select(User.source, func.count(User.id)).group_by(User.source)
        user_counts_res = await self.session.execute(user_counts_stmt)
        user_counts = {str(src): int(cnt) for src, cnt in user_counts_res.all()}

        return [
            (
                src,
                lead_counts.get(src.name, 0),
                user_counts.get(src.name, 0),
            )
            for src in sources
        ]

    async def resolve_source_name(self, *, raw_source: str | None) -> str:
        if not raw_source or not str(raw_source).strip():
            return AcquisitionSource.BROWSER.value

        matched = await self.get_by_key_or_compact(name=str(raw_source))
        if matched is not None:
            return matched.name

        return AcquisitionSource.BROWSER.value
