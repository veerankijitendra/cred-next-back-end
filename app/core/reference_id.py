from uuid import UUID


def generate_reference_id(user_id: UUID) -> str:
    """
    Generate an uppercase, human-friendly 16-character reference ID.

    Example:
    CNX-REF-93AC44FA
    """
    return f"CNX-REF-{user_id.hex[:8].upper()}"
