from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.freelancers.models import FreelancerProfile
from app.freelancers.service import get_profile_by_user_id, touch_search_projection
from app.identity.models import User
from app.portfolios.models import PortfolioItem


def list_portfolio(user_id: uuid.UUID) -> list[PortfolioItem]:
    profile = get_profile_by_user_id(user_id)
    return list(
        db.session.scalars(
            select(PortfolioItem)
            .options(selectinload(PortfolioItem.files))
            .where(PortfolioItem.freelancer_profile_id == profile.id)
            .order_by(PortfolioItem.created_at.desc())
        )
    )


def create_portfolio_item(
    *, user: User, title: str, description: str, external_url: str | None
) -> PortfolioItem:
    profile = get_profile_by_user_id(user.id)
    item = PortfolioItem(
        freelancer_profile_id=profile.id,
        title=title,
        description=description,
        external_url=external_url,
    )
    db.session.add(item)
    db.session.flush()
    touch_search_projection(profile)
    record_audit_event(
        action="portfolio.item_created",
        resource_type="portfolio_item",
        resource_id=str(item.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return item


def delete_portfolio_item(*, user: User, item_id: uuid.UUID) -> None:
    item = db.session.scalar(select(PortfolioItem).where(PortfolioItem.id == item_id))
    if item is None:
        raise ApiError(
            "portfolio_item_not_found",
            "Portfolio item not found",
            404,
            "Item not found",
        )
    profile = db.session.get(FreelancerProfile, item.freelancer_profile_id)
    if profile is None or profile.user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "Portfolio item cannot be deleted")
    db.session.delete(item)
    touch_search_projection(profile)
    record_audit_event(
        action="portfolio.item_deleted",
        resource_type="portfolio_item",
        resource_id=str(item.id),
        actor_user_id=user.id,
    )
    db.session.commit()
