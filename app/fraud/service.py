from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy import func, select

from app.audit.service import record_audit_event
from app.disputes.models import DisputeParty
from app.errors import ApiError
from app.extensions import db
from app.fraud.models import RiskAssessment
from app.identity.models import User
from app.messaging.models import Message
from app.payments.models import PaymentIntent
from app.proposals.models import Proposal

RISK_MODEL_VERSION = "fraud-rules-v1"
RISK_FEATURE_VERSION = "fraud-signals-v1"
_REVIEW_THRESHOLD = 6000
_OFF_PLATFORM_TERMS = (
    "telegram",
    "whatsapp",
    "contact me at",
    "pay outside",
    "outside the platform",
    "crypto payment",
)
_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)


class RiskSignals(TypedDict):
    url_count: int
    off_platform_terms: list[str]
    message_velocity_10m: int
    account_age_days: float
    failed_payment_count: int
    proposal_burst_1h: int
    dispute_count: int
    duplicate_text_prior_assessments: int


def assess_risk(*, administrator: User, subject_user_id: uuid.UUID, text: str) -> RiskAssessment:
    subject = db.session.get(User, subject_user_id)
    if subject is None:
        raise ApiError("user_not_found", "User not found", 404, "Subject user was not found")
    normalized_text = text.strip()
    if len(normalized_text) > 20_000:
        raise ApiError(
            "validation_error",
            "Text is too long",
            422,
            "Risk text is limited to 20000 characters",
        )
    now = datetime.now(UTC)
    text_hash = hashlib.sha256(normalized_text.casefold().encode()).hexdigest()
    signals = _signals(subject=subject, text=normalized_text, text_hash=text_hash, now=now)
    score, reasons = _score(signals)
    assessment = RiskAssessment(
        id=uuid.uuid4(),
        subject_user_id=subject.id,
        requested_by_user_id=administrator.id,
        model_version=RISK_MODEL_VERSION,
        feature_version=RISK_FEATURE_VERSION,
        text_hash=text_hash,
        risk_score_basis_points=score,
        reasons_json=reasons,
        signals_json=_signals_json(signals),
        review_status="PENDING" if score >= _REVIEW_THRESHOLD else "NOT_REQUIRED",
    )
    db.session.add(assessment)
    record_audit_event(
        action="risk.assessed",
        resource_type="risk_assessment",
        resource_id=str(assessment.id),
        actor_user_id=administrator.id,
        metadata={
            "subject_user_id": str(subject.id),
            "score_basis_points": score,
            "reasons": reasons,
            "review_status": assessment.review_status,
        },
    )
    db.session.commit()
    return assessment


def review_assessment(
    *, administrator: User, assessment_id: uuid.UUID, decision: str, note: str
) -> RiskAssessment:
    assessment = db.session.scalar(
        select(RiskAssessment).where(RiskAssessment.id == assessment_id).with_for_update()
    )
    if assessment is None:
        raise ApiError(
            "assessment_not_found",
            "Risk assessment not found",
            404,
            "Assessment was not found",
        )
    normalized_decision = decision.strip().upper()
    if normalized_decision not in {"CLEAR", "ESCALATE"}:
        raise ApiError(
            "validation_error",
            "Invalid review decision",
            422,
            "decision must be CLEAR or ESCALATE",
        )
    normalized_note = note.strip()
    if len(normalized_note) > 2000:
        raise ApiError(
            "validation_error",
            "Review note too long",
            422,
            "review note is limited to 2000 characters",
        )
    before_status = assessment.review_status
    assessment.review_status = "CLEARED" if normalized_decision == "CLEAR" else "ESCALATED"
    assessment.reviewer_user_id = administrator.id
    assessment.review_note = normalized_note or None
    assessment.reviewed_at = datetime.now(UTC)
    record_audit_event(
        action="risk.reviewed",
        resource_type="risk_assessment",
        resource_id=str(assessment.id),
        actor_user_id=administrator.id,
        metadata={
            "subject_user_id": str(assessment.subject_user_id),
            "before_status": before_status,
            "after_status": assessment.review_status,
            "decision": normalized_decision,
            "note": normalized_note,
        },
    )
    db.session.commit()
    return assessment


def serialize_assessment(assessment: RiskAssessment) -> dict[str, Any]:
    return {
        "id": str(assessment.id),
        "subject_user_id": str(assessment.subject_user_id),
        "model_version": assessment.model_version,
        "feature_version": assessment.feature_version,
        "risk_score": round(assessment.risk_score_basis_points / 10000, 4),
        "risk_score_basis_points": assessment.risk_score_basis_points,
        "reasons": assessment.reasons_json,
        "signals": assessment.signals_json,
        "review_status": assessment.review_status,
        "reviewer_user_id": (
            str(assessment.reviewer_user_id) if assessment.reviewer_user_id else None
        ),
        "review_note": assessment.review_note,
        "created_at": assessment.created_at.isoformat(),
        "reviewed_at": assessment.reviewed_at.isoformat() if assessment.reviewed_at else None,
        "automatic_action": None,
    }


def _signals(*, subject: User, text: str, text_hash: str, now: datetime) -> RiskSignals:
    created_at = subject.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    account_age_days = max(0.0, (now - created_at).total_seconds() / 86400)
    url_count = len(_URL_PATTERN.findall(text))
    lowered = text.casefold()
    off_platform_hits = [term for term in _OFF_PLATFORM_TERMS if term in lowered]
    message_velocity = int(
        db.session.scalar(
            select(func.count(Message.id)).where(
                Message.sender_user_id == subject.id,
                Message.created_at >= now - timedelta(minutes=10),
            )
        )
        or 0
    )
    proposal_burst = int(
        db.session.scalar(
            select(func.count(Proposal.id)).where(
                Proposal.freelancer_user_id == subject.id,
                Proposal.created_at >= now - timedelta(hours=1),
            )
        )
        or 0
    )
    failed_payments = int(
        db.session.scalar(
            select(func.count(PaymentIntent.id)).where(
                PaymentIntent.employer_user_id == subject.id,
                PaymentIntent.status == "FAILED",
            )
        )
        or 0
    )
    dispute_count = int(
        db.session.scalar(
            select(func.count(DisputeParty.dispute_id)).where(DisputeParty.user_id == subject.id)
        )
        or 0
    )
    duplicate_text_count = int(
        db.session.scalar(
            select(func.count(RiskAssessment.id)).where(
                RiskAssessment.subject_user_id == subject.id,
                RiskAssessment.text_hash == text_hash,
            )
        )
        or 0
    )
    return {
        "url_count": url_count,
        "off_platform_terms": off_platform_hits,
        "message_velocity_10m": message_velocity,
        "account_age_days": round(account_age_days, 2),
        "failed_payment_count": failed_payments,
        "proposal_burst_1h": proposal_burst,
        "dispute_count": dispute_count,
        "duplicate_text_prior_assessments": duplicate_text_count,
    }


def _signals_json(signals: RiskSignals) -> dict[str, object]:
    return {
        "url_count": signals["url_count"],
        "off_platform_terms": signals["off_platform_terms"],
        "message_velocity_10m": signals["message_velocity_10m"],
        "account_age_days": signals["account_age_days"],
        "failed_payment_count": signals["failed_payment_count"],
        "proposal_burst_1h": signals["proposal_burst_1h"],
        "dispute_count": signals["dispute_count"],
        "duplicate_text_prior_assessments": signals["duplicate_text_prior_assessments"],
    }


def _score(signals: RiskSignals) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    url_count = signals["url_count"]
    if url_count >= 3:
        score += min(2400, url_count * 800)
        reasons.append("url_spam")
    if signals["off_platform_terms"]:
        score += 2000
        reasons.append("off_platform_contact")
    velocity = signals["message_velocity_10m"]
    if velocity >= 20:
        score += 1500
        reasons.append("high_message_velocity")
    elif velocity >= 10:
        score += 800
        reasons.append("elevated_message_velocity")
    account_age_days = signals["account_age_days"]
    if account_age_days < 1:
        score += 1200
        reasons.append("new_account")
    elif account_age_days < 7:
        score += 600
        reasons.append("young_account")
    failed_payments = signals["failed_payment_count"]
    if failed_payments:
        score += min(1500, failed_payments * 500)
        reasons.append("payment_failures")
    proposal_burst = signals["proposal_burst_1h"]
    if proposal_burst >= 10:
        score += 1500
        reasons.append("proposal_burst")
    elif proposal_burst >= 5:
        score += 800
        reasons.append("elevated_proposal_rate")
    if signals["dispute_count"] >= 3:
        score += 1000
        reasons.append("repeated_disputes")
    if signals["duplicate_text_prior_assessments"] >= 2:
        score += 1000
        reasons.append("duplicate_text")
    return min(10000, score), reasons
