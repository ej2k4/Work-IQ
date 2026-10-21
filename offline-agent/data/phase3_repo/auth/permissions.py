"""Role-based access checks requiring authenticated token."""
from auth.tokens import verify_session_token

def check_permission(session_token: str, required_role: str) -> bool:
    """Verify session token and check if user has required role."""
    user = verify_session_token(session_token)
    if not user:
        return False
    return user.get("role") == required_role or required_role == "public"
