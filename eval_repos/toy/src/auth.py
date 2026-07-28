"""Authentication helpers for the toy repository."""


def authenticate_user(username: str, password: str) -> bool:
    """Handle authentication for sign-in requests."""

    return bool(username and password)

