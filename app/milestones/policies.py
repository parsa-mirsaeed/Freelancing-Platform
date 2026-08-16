from __future__ import annotations

from app.contracts.models import Contract
from app.identity.models import User


def can_work_on_milestone(user: User, contract: Contract) -> bool:
    return user.id == contract.freelancer_user_id


def can_review_milestone(user: User, contract: Contract) -> bool:
    return user.id == contract.employer_user_id


def can_view_milestone(user: User, contract: Contract) -> bool:
    return user.id in {contract.employer_user_id, contract.freelancer_user_id}
