from __future__ import annotations

from flask import Blueprint, g, jsonify

from app.identity.auth import require_roles
from app.identity.models import User
from app.ledger.service import wallet_balances

ledger_bp = Blueprint("ledger", __name__, url_prefix="/api/v1")


@ledger_bp.get("/wallet")
@require_roles("freelancer")
def get_wallet():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    balances = wallet_balances(user.id)
    return jsonify(
        {
            "user_id": str(user.id),
            "balances": [
                {"currency": currency, "available_minor": amount}
                for currency, amount in sorted(balances.items())
            ],
        }
    )
