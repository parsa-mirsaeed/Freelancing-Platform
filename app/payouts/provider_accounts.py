from __future__ import annotations

import uuid

from sqlalchemy import select

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.payments.providers.registry import get_provider
from app.payouts.models import PayoutProviderAccount


def configure_payout_provider_account(
    *,
    administrator: User,
    freelancer_user_id: uuid.UUID,
    provider_name: str,
    external_account_reference: str,
) -> dict[str, object]:
    freelancer = db.session.get(User, freelancer_user_id)
    if freelancer is None or "freelancer" not in {assignment.role for assignment in freelancer.roles}:
        raise ApiError(
            "freelancer_not_found",
            "Freelancer not found",
            404,
            "Payout provider accounts can only be configured for freelancer users",
        )

    provider = get_provider(provider_name)
    verified_reference = provider.validate_payout_destination(
        reference=external_account_reference.strip()
    )

    conflicting = db.session.scalar(
        select(PayoutProviderAccount).where(
            PayoutProviderAccount.provider == provider.name,
            PayoutProviderAccount.external_account_reference == verified_reference,
            PayoutProviderAccount.freelancer_user_id != freelancer_user_id,
        )
    )
    if conflicting is not None:
        raise ApiError(
            "payout_destination_conflict",
            "Payout destination conflict",
            409,
            "This provider account is already assigned to another freelancer",
        )

    account = db.session.scalar(
        select(PayoutProviderAccount)
        .where(
            PayoutProviderAccount.freelancer_user_id == freelancer_user_id,
            PayoutProviderAccount.provider == provider.name,
        )
        .with_for_update()
    )
    if account is None:
        account = PayoutProviderAccount(
            freelancer_user_id=freelancer_user_id,
            provider=provider.name,
            external_account_reference=verified_reference,
            status="ACTIVE",
        )
        db.session.add(account)
    else:
        account.external_account_reference = verified_reference
        account.status = "ACTIVE"
    db.session.flush()

    record_audit_event(
        action="payout_provider_account.configured",
        resource_type="payout_provider_account",
        resource_id=str(account.id),
        actor_user_id=administrator.id,
        metadata={
            "freelancer_user_id": str(freelancer_user_id),
            "provider": provider.name,
            "reference_tail": verified_reference[-6:],
        },
    )
    db.session.commit()
    return _serialize(account)


def disable_payout_provider_account(
    *, administrator: User, freelancer_user_id: uuid.UUID, provider_name: str
) -> dict[str, object]:
    provider_name = provider_name.strip().lower()
    account = db.session.scalar(
        select(PayoutProviderAccount)
        .where(
            PayoutProviderAccount.freelancer_user_id == freelancer_user_id,
            PayoutProviderAccount.provider == provider_name,
        )
        .with_for_update()
    )
    if account is None:
        raise ApiError(
            "payout_provider_account_not_found",
            "Payout provider account not found",
            404,
            "Payout provider account was not found",
        )
    account.status = "DISABLED"
    record_audit_event(
        action="payout_provider_account.disabled",
        resource_type="payout_provider_account",
        resource_id=str(account.id),
        actor_user_id=administrator.id,
        metadata={
            "freelancer_user_id": str(freelancer_user_id),
            "provider": account.provider,
        },
    )
    db.session.commit()
    return _serialize(account)


def resolve_payout_destination(*, freelancer_user_id: uuid.UUID, provider_name: str) -> str:
    provider_name = provider_name.strip().lower()
    if provider_name == "sandbox":
        return str(freelancer_user_id)
    account = db.session.scalar(
        select(PayoutProviderAccount).where(
            PayoutProviderAccount.freelancer_user_id == freelancer_user_id,
            PayoutProviderAccount.provider == provider_name,
            PayoutProviderAccount.status == "ACTIVE",
        )
    )
    if account is None:
        raise ApiError(
            "payout_destination_not_configured",
            "Payout destination not configured",
            409,
            "Configure and verify a payout provider account before requesting this payout",
        )
    return account.external_account_reference


def _serialize(account: PayoutProviderAccount) -> dict[str, object]:
    return {
        "id": str(account.id),
        "freelancer_user_id": str(account.freelancer_user_id),
        "provider": account.provider,
        "external_account_reference": account.external_account_reference,
        "status": account.status,
    }
