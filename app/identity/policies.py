from __future__ import annotations

from app.identity.models import User


def has_role(user: User, role: str) -> bool:
    return any(assignment.role == role for assignment in user.roles)


def can_access_user_resource(actor: User, resource_owner_id: object) -> bool:
    return actor.id == resource_owner_id or has_role(actor, "admin")
