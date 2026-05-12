from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.consult.models import ConsultantProfile, PortfolioConsultRequest
from vmarket.repositories import consultant_profile as profile_repo


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value in {None, ""}:
        return None
    return Decimal(value)


def get_profile(session: Session) -> ConsultantProfile:
    record = profile_repo.get_default(session)
    if record is None:
        return ConsultantProfile()
    return ConsultantProfile(
        risk_score=record.risk_score,
        exclusions=json.loads(record.exclusions_json or "[]"),
        product_preferences=json.loads(record.product_preferences_json or "[]"),
        preference_tags=json.loads(record.preference_tags_json or "[]"),
        account_wrappers=json.loads(record.account_wrappers_json or "[]"),
        investment_horizon=record.investment_horizon,
        amount=_decimal_or_none(record.amount),
        monthly_amount=_decimal_or_none(record.monthly_amount),
        income_preference=record.income_preference,
        distribution_preference=record.distribution_preference,
        country_jurisdiction=record.country_jurisdiction or "UK",
        base_currency=record.base_currency or "GBP",
        prefers_uk_listed=record.prefers_uk_listed,
        prefers_gbp_lines=record.prefers_gbp_lines,
    )


def save_profile(session: Session, profile: ConsultantProfile) -> ConsultantProfile:
    record = profile_repo.get_or_create_default(session)
    record.risk_score = profile.risk_score
    record.exclusions_json = json.dumps(profile.exclusions)
    record.product_preferences_json = json.dumps(profile.product_preferences)
    record.preference_tags_json = json.dumps(profile.preference_tags)
    record.account_wrappers_json = json.dumps(profile.account_wrappers)
    record.investment_horizon = profile.investment_horizon
    record.amount = str(profile.amount) if profile.amount is not None else None
    record.monthly_amount = (
        str(profile.monthly_amount) if profile.monthly_amount is not None else None
    )
    record.income_preference = profile.income_preference
    record.distribution_preference = profile.distribution_preference
    record.country_jurisdiction = profile.country_jurisdiction
    record.base_currency = profile.base_currency
    record.prefers_uk_listed = profile.prefers_uk_listed
    record.prefers_gbp_lines = profile.prefers_gbp_lines
    session.flush()
    return get_profile(session)


def clear_profile(session: Session) -> None:
    profile_repo.delete_default(session)


def merge_request_with_profile(
    profile: ConsultantProfile,
    request: PortfolioConsultRequest,
) -> ConsultantProfile:
    merged = profile.model_copy(deep=True)
    if request.risk_score is not None:
        merged.risk_score = request.risk_score
    if request.exclusions:
        merged.exclusions = sorted({*merged.exclusions, *request.exclusions})
    if request.preferences:
        merged.preference_tags = sorted({*merged.preference_tags, *request.preferences})
    if request.investment_horizon is not None:
        merged.investment_horizon = request.investment_horizon
    if request.amount is not None:
        merged.amount = request.amount
    if request.monthly_amount is not None:
        merged.monthly_amount = request.monthly_amount
    if request.income_preference is not None:
        merged.income_preference = request.income_preference
    if request.product_preferences:
        merged.product_preferences = request.product_preferences
    if request.distribution_preference is not None:
        merged.distribution_preference = request.distribution_preference
    if request.country_jurisdiction is not None:
        merged.country_jurisdiction = request.country_jurisdiction
    if request.base_currency is not None:
        merged.base_currency = request.base_currency.upper()
    if request.prefers_uk_listed is not None:
        merged.prefers_uk_listed = request.prefers_uk_listed
    if request.prefers_gbp_lines is not None:
        merged.prefers_gbp_lines = request.prefers_gbp_lines
    return merged
