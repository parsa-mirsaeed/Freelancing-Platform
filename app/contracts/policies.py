from __future__ import annotations

from app.contracts.models import Contract
from app.identity.models import User


def is_contract_party(user: User, contract: Contract) -> bool:
    return user.id in {contract.employer_user_id, contract.freelancer_user_id}


def can_cancel_contract(user: User, contract: Contract) -> bool:
    return user.id == contract.employer_user_id
