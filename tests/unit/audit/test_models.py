import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.extensions import db

pytestmark = pytest.mark.unit


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
