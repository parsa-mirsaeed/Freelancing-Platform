from __future__ import annotations

from app.freelancers.models import FreelancerProfile
from app.identity.models import User


def can_edit_profile(user: User, profile: FreelancerProfile) -> bool:
    return user.id == profile.user_id and any(role.role == "freelancer" for role in user.roles)
