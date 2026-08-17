from __future__ import annotations

from app.contracts.models import Contract
from app.identity.models import User


def can_fund_milestone(user: User, contract: Contract) -> bool:
    return user.id == contract.employer_user_id


def can_release_or_refund(user: User, contract: Contract) -> bool:
    return user.id == contract.employer_user_id
