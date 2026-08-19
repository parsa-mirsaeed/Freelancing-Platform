from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from flask import Flask, g, request

from app.calls.api import calls_bp
from app.config import Settings
from app.contracts.api import contracts_bp
from app.disputes.api import disputes_bp
from app.errors import register_error_handlers
from app.extensions import db, elasticsearch_extension, redis_extension
from app.files.api import files_bp
from app.fraud.api import fraud_bp
from app.freelancers.api import freelancers_bp
from app.gigs.api import gigs_bp
from app.health import health_bp
from app.identity.api import identity_bp
from app.ledger.api import ledger_bp
from app.messaging.api import messaging_bp
from app.milestones.api import milestones_bp
from app.notifications.api import notifications_bp
from app.payments.api import payments_bp
from app.payouts.api import payouts_bp
from app.portfolios.api import portfolios_bp
from app.projects.api import projects_bp
from app.proposals.api import proposals_bp
from app.realtime.service import init_realtime
from app.recommendations.api import recommendations_bp
from app.reviews.api import reviews_bp
from app.search.api import search_bp


def create_app(config_overrides: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(Settings.from_env().flask_mapping())
    if config_overrides:
        app.config.from_mapping(config_overrides)

    db.init_app(app)
    redis_extension.init_app(app)
    elasticsearch_extension.init_app(app)
    _register_models()
    init_realtime(app)
    app.register_blueprint(health_bp)
    app.register_blueprint(identity_bp)
    app.register_blueprint(freelancers_bp)
    app.register_blueprint(portfolios_bp)
    app.register_blueprint(gigs_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(proposals_bp)
    app.register_blueprint(contracts_bp)
    app.register_blueprint(milestones_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(ledger_bp)
    app.register_blueprint(payouts_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(messaging_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(disputes_bp)
    app.register_blueprint(calls_bp)
    app.register_blueprint(recommendations_bp)
    app.register_blueprint(fraud_bp)
    register_error_handlers(app)
    _register_request_context(app)
    return app


def _register_models() -> None:
    from app.audit import models as audit_models  # noqa: F401
    from app.calls import models as call_models  # noqa: F401
    from app.common import models as common_models  # noqa: F401
    from app.contracts import models as contract_models  # noqa: F401
    from app.disputes import models as dispute_models  # noqa: F401
    from app.files import models as file_models  # noqa: F401
    from app.fraud import models as fraud_models  # noqa: F401
    from app.freelancers import models as freelancer_models  # noqa: F401
    from app.gigs import models as gig_models  # noqa: F401
    from app.identity import models as identity_models  # noqa: F401
    from app.ledger import models as ledger_models  # noqa: F401
    from app.messaging import models as messaging_models  # noqa: F401
    from app.milestones import models as milestone_models  # noqa: F401
    from app.notifications import models as notification_models  # noqa: F401
    from app.payments import models as payment_models  # noqa: F401
    from app.payouts import models as payout_models  # noqa: F401
    from app.portfolios import models as portfolio_models  # noqa: F401
    from app.projects import models as project_models  # noqa: F401
    from app.proposals import models as proposal_models  # noqa: F401
    from app.recommendations import models as recommendation_models  # noqa: F401
    from app.reviews import models as review_models  # noqa: F401


def _register_request_context(app: Flask) -> None:
    @app.before_request
    def assign_request_id() -> None:
        incoming = request.headers.get("X-Request-ID")
        g.request_id = incoming[:64] if incoming else str(uuid.uuid4())

    @app.after_request
    def attach_request_id(response):  # type: ignore[no-untyped-def]
        response.headers["X-Request-ID"] = g.request_id
        return response
