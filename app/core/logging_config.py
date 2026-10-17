import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Emit allow-listed structured fields without serializing arbitrary extras."""

    _fields = (
        "event",
        "http_method",
        "path",
        "status_code",
        "error_code",
        "exception_type",
        "reason",
        "user_id",
        "actor_user_id",
        "lead_id",
        "application_type",
        "old_status",
        "new_status",
        "channel",
        "validation_fields",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        for field in self._fields:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False, default=str)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": JsonFormatter}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}


def setup_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)
