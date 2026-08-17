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


def test_two_socket_servers_broadcast_via_redis(tmp_path: Path) -> None:
    redis_url = "redis://localhost:6379/14"
    database_url, employer, freelancer, conversation = _setup_database(
        tmp_path / "socket.db", redis_url
    )
    ports = (_free_port(), _free_port())
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_serve, args=(database_url, redis_url, port), daemon=True)
        for port in ports
    ]
    for process in processes:
        process.start()
    try:
        for port in ports:
            _wait_http(port)

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
        for process in processes:
            process.terminate()
        for process in processes:
            process.join(timeout=5)
