from datetime import datetime
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


SAFE_SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,48}[A-Za-z0-9]$")


class CreateAcquisitionSourceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(
        min_length=2,
        max_length=50,
        description="Display name for the acquisition source (e.g. GoldGym, Metro-Mall, Diwali2026)",
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        description="Optional campaign description",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        clean = re.sub(r"\s+", " ", value.strip())
        if not SAFE_SOURCE_NAME_PATTERN.match(clean):
            raise ValueError(
                "Source name must be 2-50 characters and contain only letters, numbers, spaces, hyphens, or underscores."
            )
        return clean

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None


class AcquisitionSourceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    is_system: bool = False
    target_url: str
    leads_count: int = 0
    users_count: int = 0
    created_at: datetime


class AcquisitionSourceListResponse(BaseModel):
    items: list[AcquisitionSourceItemResponse]
    total: int
