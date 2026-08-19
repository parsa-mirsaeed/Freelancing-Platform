from __future__ import annotations

import multiprocessing
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import socketio as socketio_client

from app import create_app
from app.extensions import db, socketio
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.socket


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(database_url: str, redis_url: str, port: int) -> None:
    app = create_app(
        {
            "TESTING": False,
            "SECRET_KEY": "socket-integration-secret",
            "SQLALCHEMY_DATABASE_URI": database_url,
            "REDIS_URL": redis_url,
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "socket-unused",
            "SOCKET_CORS_ORIGINS": "http://localhost",
        }
    )
    socketio.run(
        app,
        host="127.0.0.1",
        port=port,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
        log_output=False,
    )


def _wait_http(port: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/live", timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"server on {port} did not become ready")


def _setup_database(path: Path, redis_url: str):  # type: ignore[no-untyped-def]
    database_url = f"sqlite+pysqlite:///{path}"
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "socket-integration-secret",
            "SQLALCHEMY_DATABASE_URI": database_url,
            "REDIS_URL": redis_url,
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "socket-setup-unused",
        }
    )
    with app.app_context():
        db.create_all()
    with app.test_client() as client:
        employer = register_user(client, email="socket-employer@example.com", role="employer")
        freelancer = register_user(client, email="socket-freelancer@example.com", role="freelancer")
        project = client.post(
            "/api/v1/projects",
            headers=auth_header(employer),
            json={"title": "Socket", "description": "broadcast", "skills": []},
        ).get_json()
        proposal = client.post(
            f"/api/v1/projects/{project['id']}/proposals",
            headers=auth_header(freelancer),
            json={"amount_minor": 5000, "currency": "USD", "delivery_days": 2},
        ).get_json()
        assert (
            client.post(
                f"/api/v1/proposals/{proposal['id']}/submit",
                headers=auth_header(freelancer),
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/proposals/{proposal['id']}/accept",
                headers=auth_header(employer),
            ).status_code
            == 200
        )
        contract = client.get(
            f"/api/v1/projects/{project['id']}/contract",
            headers=auth_header(employer),
        ).get_json()
        conversation = client.post(
            f"/api/v1/contracts/{contract['id']}/conversation",
            headers=auth_header(employer),
        ).get_json()
    return database_url, employer, freelancer, conversation


def _servers(database_url: str, redis_url: str):  # type: ignore[no-untyped-def]
    ports = (_free_port(), _free_port())
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_serve, args=(database_url, redis_url, port), daemon=True)
        for port in ports
    ]
    for process in processes:
        process.start()
    for port in ports:
        _wait_http(port)
    return ports, processes


def _stop_servers(processes) -> None:  # type: ignore[no-untyped-def]
    for process in processes:
        process.terminate()
    for process in processes:
        process.join(timeout=5)


def test_two_socket_servers_broadcast_via_redis(tmp_path: Path) -> None:
    redis_url = "redis://localhost:6379/14"
    database_url, employer, freelancer, conversation = _setup_database(
        tmp_path / "socket.db", redis_url
    )
    ports, processes = _servers(database_url, redis_url)
    try:
        sender = socketio_client.Client(reconnection=False)
        receiver = socketio_client.Client(reconnection=False)
        received = threading.Event()
        payloads: list[dict[str, Any]] = []

        @receiver.on("message.created")
        def on_message(payload: dict[str, Any]) -> None:
            payloads.append(payload)
            received.set()

        sender.connect(
            f"http://127.0.0.1:{ports[0]}",
            auth={"token": employer["access_token"]},
            transports=["polling"],
        )
        receiver.connect(
            f"http://127.0.0.1:{ports[1]}",
            auth={"token": freelancer["access_token"]},
            transports=["polling"],
        )
        assert sender.call("conversation.join", {"conversation_id": conversation["id"]})["ok"]
        assert receiver.call("conversation.join", {"conversation_id": conversation["id"]})["ok"]
        ack = sender.call(
            "message.send",
            {
                "conversation_id": conversation["id"],
                "client_message_id": "socket-message-1",
                "body": "persist before broadcast",
            },
        )
        assert ack["ok"] is True
        assert ack["message"]["sequence"] == 1
        assert received.wait(timeout=5)
        assert payloads[0]["id"] == ack["message"]["id"]
        sender.disconnect()
        receiver.disconnect()

        invalid = socketio_client.Client(reconnection=False)
        with pytest.raises(socketio_client.exceptions.ConnectionError):
            invalid.connect(
                f"http://127.0.0.1:{ports[0]}",
                auth={"token": "invalid"},
                transports=["polling"],
            )
    finally:
        _stop_servers(processes)


def test_webrtc_signaling_crosses_socket_servers_via_redis(tmp_path: Path) -> None:
    redis_url = "redis://localhost:6379/13"
    database_url, employer, freelancer, conversation = _setup_database(
        tmp_path / "webrtc.db", redis_url
    )
    ports, processes = _servers(database_url, redis_url)
    try:
        caller = socketio_client.Client(reconnection=False)
        callee = socketio_client.Client(reconnection=False)
        invited = threading.Event()
        accepted = threading.Event()
        offer_received = threading.Event()
        answer_received = threading.Event()
        ice_received = threading.Event()
        ended = threading.Event()
        events: dict[str, dict[str, Any]] = {}

        @callee.on("call.invite")
        def on_invite(payload: dict[str, Any]) -> None:
            events["invite"] = payload
            invited.set()

        @caller.on("call.accept")
        def on_accept(payload: dict[str, Any]) -> None:
            events["accept"] = payload
            accepted.set()

        @callee.on("webrtc.offer")
        def on_offer(payload: dict[str, Any]) -> None:
            events["offer"] = payload
            offer_received.set()

        @caller.on("webrtc.answer")
        def on_answer(payload: dict[str, Any]) -> None:
            events["answer"] = payload
            answer_received.set()

        @caller.on("webrtc.ice_candidate")
        def on_ice(payload: dict[str, Any]) -> None:
            events["ice"] = payload
            ice_received.set()

        @caller.on("call.end")
        def on_end(payload: dict[str, Any]) -> None:
            events["end"] = payload
            ended.set()

        caller.connect(
            f"http://127.0.0.1:{ports[0]}",
            auth={"token": employer["access_token"]},
            transports=["polling"],
        )
        callee.connect(
            f"http://127.0.0.1:{ports[1]}",
            auth={"token": freelancer["access_token"]},
            transports=["polling"],
        )
        invite_ack = caller.call(
            "call.invite",
            {
                "conversation_id": conversation["id"],
                "client_call_id": "webrtc-call-1",
                "call_type": "VIDEO",
            },
        )
        assert invite_ack["ok"] is True
        call_id = invite_ack["call"]["id"]
        assert invited.wait(timeout=5)
        assert events["invite"]["call"]["id"] == call_id

        premature = caller.call(
            "webrtc.offer",
            {
                "call_id": call_id,
                "description": {"type": "offer", "sdp": "v=0\r\n"},
            },
        )
        assert premature["ok"] is False
        assert premature["error"]["status"] == 409

        accept_ack = callee.call("call.accept", {"call_id": call_id})
        assert accept_ack["ok"] is True
        assert accept_ack["call"]["status"] == "ACTIVE"
        assert accepted.wait(timeout=5)
        assert events["accept"]["call"]["id"] == call_id

        assert caller.call(
            "webrtc.offer",
            {
                "call_id": call_id,
                "description": {"type": "offer", "sdp": "v=0\r\no=caller\r\n"},
            },
        )["ok"]
        assert offer_received.wait(timeout=5)
        assert events["offer"]["description"]["type"] == "offer"

        assert callee.call(
            "webrtc.answer",
            {
                "call_id": call_id,
                "description": {"type": "answer", "sdp": "v=0\r\no=callee\r\n"},
            },
        )["ok"]
        assert answer_received.wait(timeout=5)
        assert events["answer"]["description"]["type"] == "answer"

        assert callee.call(
            "webrtc.ice_candidate",
            {
                "call_id": call_id,
                "candidate": {
                    "candidate": "candidate:1 1 UDP 2122260223 192.0.2.1 54400 typ host",
                    "sdpMid": "0",
                    "sdpMLineIndex": 0,
                },
            },
        )["ok"]
        assert ice_received.wait(timeout=5)
        assert events["ice"]["call_id"] == call_id

        end_ack = callee.call(
            "call.end",
            {"call_id": call_id, "reason": "finished"},
        )
        assert end_ack["ok"] is True
        assert end_ack["call"]["status"] == "ENDED"
        assert ended.wait(timeout=5)
        assert events["end"]["call"]["id"] == call_id
        caller.disconnect()
        callee.disconnect()
    finally:
        _stop_servers(processes)
