from __future__ import annotations

import os

from flask import Flask

from app.extensions import socketio


def init_realtime(app: Flask) -> None:
    configured_origins = app.config.get("SOCKET_CORS_ORIGINS")
    raw_origins = str(
        configured_origins or os.getenv("SOCKET_CORS_ORIGINS", "http://localhost:3000")
    )
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    socketio.init_app(
        app,
        message_queue=str(app.config["REDIS_URL"]),
        cors_allowed_origins=origins,
        async_mode="threading",
        ping_interval=25,
        ping_timeout=20,
    )
    from app.realtime import socket as socket_handlers  # noqa: F401
