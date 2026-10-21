"""Role-based access control (RBAC) and permission checks."""
ROLES_PERMISSIONS = {
    "admin": {"view_catalog", "edit_catalog", "view_orders", "refund_orders", "manage_users"},
    "manager": {"view_catalog", "edit_catalog", "view_orders"},
    "customer": {"view_catalog", "create_order", "view_own_orders"},
}

def check_user_permission(role: str, action: str) -> bool:
    """Perform role-based access control (RBAC) permission check."""
    allowed_actions = ROLES_PERMISSIONS.get(role, set())
    return action in allowed_actions

def require_role(role: str, user_role: str) -> bool:
    """Check if user role matches or exceeds required role level."""
    hierarchy = {"admin": 3, "manager": 2, "customer": 1}
    return hierarchy.get(user_role, 0) >= hierarchy.get(role, 0)
