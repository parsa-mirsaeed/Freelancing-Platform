from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.audit.service import audit_state_hash, record_audit_event
from app.extensions import db

pytestmark = pytest.mark.unit


def test_audit_state_hash_is_canonical() -> None:
    state_a = {"status": "ACTIVE", "amount_minor": 1200, "nested": {"b": 2, "a": 1}}
    state_b = {"nested": {"a": 1, "b": 2}, "amount_minor": 1200, "status": "ACTIVE"}
    assert audit_state_hash(state_a) == audit_state_hash(state_b)
    assert audit_state_hash(state_a) != audit_state_hash({**state_a, "status": "CANCELLED"})


def test_audit_state_hash_normalizes_supported_types() -> None:
    timestamp = datetime(2026, 8, 28, 12, 30, tzinfo=UTC)
    first = audit_state_hash({"timestamp": timestamp})
    second = audit_state_hash({"timestamp": timestamp.isoformat()})
    assert first == second


def test_record_audit_event_persists_explicit_state_hashes(app) -> None:  # type: ignore[no-untyped-def]
    before = {"status": "PENDING"}
    after = {"status": "ACTIVE"}
    with app.app_context():
        event = record_audit_event(
            action="test.transitioned",
            resource_type="unit",
            previous_state=before,
            new_state=after,
        )
        db.session.commit()
        assert event.previous_state_hash == audit_state_hash(before)
        assert event.new_state_hash == audit_state_hash(after)
        assert event.previous_state_hash != event.new_state_hash


def test_record_audit_event_hashes_existing_before_after_metadata(app) -> None:  # type: ignore[no-untyped-def]
    before = {"status": "UNDER_REVIEW"}
    after = {"status": "RESOLVED", "outcome": "REFUND_CLIENT"}
    with app.app_context():
        event = record_audit_event(
            action="dispute.resolved",
            resource_type="dispute",
            metadata={"before": before, "after": after, "why": "evidence reviewed"},
        )
        db.session.commit()
        assert event.previous_state_hash == audit_state_hash(before)
        assert event.new_state_hash == audit_state_hash(after)


def test_high_risk_audit_action_requires_both_states(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context(), pytest.raises(ValueError, match="requires previous and new state"):
        record_audit_event(
            action="milestone.released",
            resource_type="milestone",
            previous_state={"status": "APPROVED"},
        )


def test_low_risk_audit_action_may_omit_state_hashes(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        event = record_audit_event(
            action="identity.session_refreshed",
            resource_type="session",
        )
        db.session.commit()
        assert event.previous_state_hash is None
        assert event.new_state_hash is None


def test_audit_event_is_immutable(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        event = AuditEvent(action="test", resource_type="unit", metadata_json={})
        db.session.add(event)
        db.session.commit()
        stored = db.session.scalar(select(AuditEvent))
        assert stored is not None
        stored.action = "changed"
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()


def test_audit_event_cannot_be_deleted(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        event = AuditEvent(action="test", resource_type="unit", metadata_json={})
        db.session.add(event)
        db.session.commit()
        db.session.delete(event)
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()
