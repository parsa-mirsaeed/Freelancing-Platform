from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify

from app.calls.ice import issue_ice_servers
from app.calls.queries import get_live_call_for_conversation
from app.calls.service import get_call_for_user, serialize_call
from app.identity.auth import require_access_token
from app.identity.models import User

calls_bp = Blueprint("calls", __name__)


@calls_bp.get("/api/v1/calls/ice-servers")
@require_access_token
def ice_servers():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    session_id: uuid.UUID = g.current_session_id
    return jsonify(issue_ice_servers(user_id=user.id, session_id=session_id))


@calls_bp.get("/api/v1/conversations/<uuid:conversation_id>/call")
@require_access_token
def get_live_conversation_call(conversation_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    call = get_live_call_for_conversation(user=user, conversation_id=conversation_id)
    return jsonify({"call": serialize_call(call) if call is not None else None})


@calls_bp.get("/api/v1/calls/<uuid:call_id>")
@require_access_token
def get_call(call_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(serialize_call(get_call_for_user(user=user, call_id=call_id)))
