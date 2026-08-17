from __future__ import annotations

from typing import Any

from celery import Celery, Task
from flask import Flask


def create_celery_app(app: Flask) -> Celery:
    class FlaskTask(Task):  # type: ignore[misc]
        def __call__(self, *args: object, **kwargs: object) -> Any:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.import_name, task_cls=FlaskTask)
    celery_app.config_from_object(
        {
            "broker_url": app.config["REDIS_URL"],
            "result_backend": app.config["REDIS_URL"],
            "task_track_started": True,
            "task_acks_late": True,
            "task_reject_on_worker_lost": True,
            "worker_prefetch_multiplier": 1,
            "task_default_queue": "default",
            "beat_schedule": {
                "drain-search-outbox": {
                    "task": "search.drain_outbox",
                    "schedule": 5.0,
                    "args": (100,),
                }
            },
        }
    )
    celery_app.autodiscover_tasks(["app.search", "app.payments"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app
