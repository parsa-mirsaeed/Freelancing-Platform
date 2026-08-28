from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, cast

from elasticsearch import Elasticsearch
from sqlalchemy import func, select

from app.extensions import db, elasticsearch_extension
from app.freelancers.models import FreelancerProfile
from app.freelancers.service import normalize_skill_slug
from app.observability import observe_histogram
from app.portfolios.models import PortfolioItem
from app.projects.models import Project
from app.proposals.models import Proposal
from app.reviews.models import Review

INDEX_SUFFIX = "freelancers-v1"
ALIAS_SUFFIX = "freelancers"


def ensure_freelancer_index(client: Elasticsearch | None = None) -> str:
    started = time.perf_counter()
    outcome = "success"
    try:
        client = client or elasticsearch_extension.get_client()
        concrete = _concrete_index()
        alias = _alias_name()
        if not bool(client.indices.exists(index=concrete)):
            client.indices.create(
                index=concrete,
                mappings={
                    "dynamic": "strict",
                    "properties": {
                        "freelancer_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "bio": {"type": "text"},
                        "skills": {"type": "keyword"},
                        "rating": {"type": "float"},
                        "completed_jobs": {"type": "integer"},
                        "hourly_rate_minor": {"type": "long"},
                        "currency": {"type": "keyword"},
                        "availability": {"type": "boolean"},
                        "languages": {"type": "keyword"},
                        "portfolio_text": {"type": "text"},
                        "projection_version": {"type": "long"},
                        "updated_at": {"type": "date"},
                    },
                },
            )
        aliases = client.indices.get_alias(index=concrete)
        alias_map = cast(dict[str, Any], aliases.body if hasattr(aliases, "body") else aliases)
        if alias not in cast(dict[str, Any], alias_map.get(concrete, {})).get("aliases", {}):
            client.indices.put_alias(index=concrete, name=alias)
        return alias
    except Exception:
        outcome = "failure"
        raise
    finally:
        observe_histogram(
            "elasticsearch_operation_duration_seconds",
            max(0.0, time.perf_counter() - started),
            operation="ensure_index",
            outcome=outcome,
        )


def index_freelancer(profile: FreelancerProfile, *, refresh: bool = False) -> None:
    client = elasticsearch_extension.get_client()
    alias = ensure_freelancer_index(client)
    document = build_freelancer_document(profile)
    started = time.perf_counter()
    outcome = "success"
    try:
        client.index(
            index=alias,
            id=str(profile.user_id),
            document=document,
            version=profile.projection_version,
            version_type="external_gte",
            refresh="wait_for" if refresh else False,
        )
    except Exception:
        outcome = "failure"
        raise
    finally:
        observe_histogram(
            "elasticsearch_operation_duration_seconds",
            max(0.0, time.perf_counter() - started),
            operation="index",
            outcome=outcome,
        )


def build_freelancer_document(profile: FreelancerProfile) -> dict[str, object]:
    reviews = list(
        db.session.scalars(
            select(Review.rating).where(Review.freelancer_user_id == profile.user_id)
        )
    )
    rating = round(sum(reviews) / len(reviews), 2) if reviews else None
    completed_jobs = db.session.scalar(
        select(func.count(Project.id))
        .join(Proposal, Proposal.project_id == Project.id)
        .where(
            Proposal.freelancer_user_id == profile.user_id,
            Proposal.status == "ACCEPTED",
            Project.status == "CLOSED",
        )
    )
    portfolio_items = list(
        db.session.scalars(
            select(PortfolioItem).where(PortfolioItem.freelancer_profile_id == profile.id)
        )
    )
    portfolio_text = " ".join(
        part for item in portfolio_items for part in (item.title, item.description) if part.strip()
    )
    return {
        "freelancer_id": str(profile.user_id),
        "title": profile.title,
        "bio": profile.bio,
        "skills": [link.skill.slug for link in profile.skill_links],
        "rating": rating,
        "completed_jobs": int(completed_jobs or 0),
        "hourly_rate_minor": profile.hourly_rate_minor,
        "currency": profile.currency,
        "availability": profile.accepting_work,
        "languages": list(profile.languages),
        "portfolio_text": portfolio_text,
        "projection_version": profile.projection_version,
        "updated_at": _as_utc(profile.updated_at).isoformat(),
    }


def search_freelancers(
    *, query: str | None, skills: list[str], available: bool | None, limit: int
) -> list[dict[str, object]]:
    client = elasticsearch_extension.get_client()
    alias = ensure_freelancer_index(client)
    filters: list[dict[str, object]] = []
    if skills:
        filters.append({"terms": {"skills": [normalize_skill_slug(skill) for skill in skills]}})
    if available is not None:
        filters.append({"term": {"availability": available}})
    must: list[dict[str, object]] = []
    if query:
        must.append(
            {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "bio", "portfolio_text", "skills^2"],
                }
            }
        )
    started = time.perf_counter()
    outcome = "success"
    try:
        response = client.search(
            index=alias,
            size=limit,
            query={"bool": {"must": must or [{"match_all": {}}], "filter": filters}},
            sort=[{"_score": "desc"}, {"rating": {"order": "desc", "missing": "_last"}}],
        )
    except Exception:
        outcome = "failure"
        raise
    finally:
        observe_histogram(
            "elasticsearch_operation_duration_seconds",
            max(0.0, time.perf_counter() - started),
            operation="search",
            outcome=outcome,
        )
    body = cast(dict[str, Any], response.body if hasattr(response, "body") else response)
    hits = cast(list[dict[str, Any]], body.get("hits", {}).get("hits", []))
    return [cast(dict[str, object], hit.get("_source", {})) for hit in hits]


def _concrete_index() -> str:
    prefix = elasticsearch_extension.index_prefix()
    return f"{prefix}-{INDEX_SUFFIX}"


def _alias_name() -> str:
    prefix = elasticsearch_extension.index_prefix()
    return f"{prefix}-{ALIAS_SUFFIX}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
