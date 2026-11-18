from datetime import UTC, datetime, timedelta


def add_working_days(start_date: datetime, working_days: int) -> datetime:
    """Add a specified number of working days (Monday-Friday) to start_date.

    Skips Saturdays (weekday 5) and Sundays (weekday 6).
    """
    current = start_date
    added = 0
    while added < working_days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def calculate_remaining_working_days(
    target_date: datetime, current_date: datetime | None = None
) -> int:
    """Calculate remaining working days (Monday-Friday) until target_date.

    Returns 0 if current_date is at or past target_date.
    """
    now = current_date or datetime.now(UTC)
    if now >= target_date:
        return 0

    current = now.date()
    end = target_date.date()
    if current >= end:
        return 0

    remaining = 0
    step = current
    while step < end:
        step += timedelta(days=1)
        if step.weekday() < 5:
            remaining += 1
    return remaining
