from __future__ import annotations

from typing import Any

from celery import Celery, Task
from celery.exceptions import Retry
from flask import Flask

from app.observability import increment_shared_counter


def create_celery_app(app: Flask) -> Celery:
    class FlaskTask(Task):  # type: ignore[misc]
        def __call__(self, *args: object, **kwargs: object) -> Any:
            task_name = str(self.name or "unknown")
            with app.app_context():
                try:
                    return self.run(*args, **kwargs)
                except Retry:
                    increment_shared_counter("celery_task_retries_total", task=task_name)
                    raise
                except Exception:
                    increment_shared_counter("celery_task_failures_total", task=task_name)
                    raise

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
            "task_routes": {
                "payments.reconcile_provider": {"queue": "reconciliation"},
                "payments.reconcile_default_provider": {"queue": "reconciliation"},
                "notifications.*": {"queue": "notifications"},
                "payments.*": {"queue": "payments"},
                "search.*": {"queue": "search_index"},
                "files.*": {"queue": "files"},
            },
            "beat_schedule": {
                "drain-search-outbox": {
                    "task": "search.drain_outbox",
                    "schedule": 5.0,
                    "args": (100,),
                },
                "drain-notification-outbox": {
                    "task": "notifications.drain_outbox",
                    "schedule": 2.0,
                    "args": (100,),
                },
                "drain-file-scan-outbox": {
                    "task": "files.drain_scan_outbox",
                    "schedule": 2.0,
                    "args": (50,),
                },
                "reconcile-default-payment-provider": {
                    "task": "payments.reconcile_default_provider",
                    "schedule": 300.0,
                },
            },
        }
    )
    celery_app.autodiscover_tasks(["app.search", "app.payments", "app.notifications", "app.files"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app
