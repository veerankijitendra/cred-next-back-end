from uuid import UUID


def generate_reference_id(user_id: UUID) -> str:
    """
    Generate a public reference ID from the user's UUID.

    Example:
    CNX-REF-550e8400e29b41d4a716446655440000
    """
    return f"CNX-REF-{user_id.hex}"
