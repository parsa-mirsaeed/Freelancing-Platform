from __future__ import annotations

from app.freelancers.models import FreelancerProfile
from app.gigs.models import Gig
from app.identity.models import User


def can_edit_gig(user: User, gig: Gig, profile: FreelancerProfile | None) -> bool:
    return (
        profile is not None
        and profile.user_id == user.id
        and gig.freelancer_profile_id == profile.id
    )
