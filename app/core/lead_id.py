from datetime import UTC, datetime
from uuid import UUID


def generate_lead_id(*, lead_id: UUID, created_at: datetime | None = None) -> str:

    created_at = created_at or datetime.now(UTC)

    return f"CNX-{created_at:%Y%m%d}-{lead_id.hex[:12].upper()}"
