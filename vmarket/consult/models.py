from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskScoreSource = Literal["explicit", "profile", "inferred", "default"]


class UserConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraint_type: str
    value: str
    source: str
    note: str | None = None


class WeightedExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    weight: float
    source: str = "derived"


class ExposureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    headline: str
    exposures: list[WeightedExposure] = Field(default_factory=list)
    comment: str


class ConcentrationWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning_key: str
    severity: Literal["low", "medium", "high"]
    summary: str
    details: str


class PortfolioGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_key: str
    summary: str
    rationale: str
    priority: Literal["low", "medium", "high"]


class ResearchIdea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_id: str
    area: str
    summary: str
    why_now: str
    fit_for_risk: str
    main_risks: list[str] = Field(default_factory=list)
    suitable_product_types: list[str] = Field(default_factory=list)
    candidate_identifiers: list[str] = Field(default_factory=list)
    exclusions_respected: list[str] = Field(default_factory=list)
    watchlist_signal: str | None = None


class FactsheetHolding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    weight_pct: float | None = None
    sector: str | None = None
    country: str | None = None


class FactsheetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str
    fund_name: str
    ticker: str | None = None
    isin: str | None = None
    ter_pct: float | None = None
    ocf_pct: float | None = None
    aum_value: str | None = None
    holdings_count: int | None = None
    top_holdings: list[FactsheetHolding] = Field(default_factory=list)
    country_exposure: list[WeightedExposure] = Field(default_factory=list)
    sector_exposure: list[WeightedExposure] = Field(default_factory=list)
    distribution_policy: str | None = None
    replication_method: str | None = None
    domicile: str | None = None
    benchmark_index: str | None = None
    factsheet_date: date | None = None
    source_url: str
    source_type: str
    fallback_used: bool = False
    collected_at: datetime
    verification_notes: list[str] = Field(default_factory=list)


class ConsultantProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_score: int | None = Field(default=None, ge=1, le=7)
    exclusions: list[str] = Field(default_factory=list)
    product_preferences: list[str] = Field(default_factory=list)
    preference_tags: list[str] = Field(default_factory=list)
    account_wrappers: list[str] = Field(default_factory=list)
    investment_horizon: str | None = None
    amount: Decimal | None = None
    monthly_amount: Decimal | None = None
    income_preference: str | None = None
    distribution_preference: str | None = None
    country_jurisdiction: str = "UK"
    base_currency: str = "GBP"
    prefers_uk_listed: bool = True
    prefers_gbp_lines: bool = True


class PortfolioConsultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_score: int | None = Field(default=None, ge=1, le=7)
    exclusions: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    investment_horizon: str | None = None
    amount: Decimal | None = None
    monthly_amount: Decimal | None = None
    income_preference: str | None = None
    product_preferences: list[str] = Field(default_factory=list)
    distribution_preference: str | None = None
    country_jurisdiction: str | None = None
    base_currency: str | None = None
    prefers_uk_listed: bool | None = None
    prefers_gbp_lines: bool | None = None


class PortfolioDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_score: int
    risk_score_source: RiskScoreSource
    constraints_used: list[UserConstraint] = Field(default_factory=list)
    profile_used: ConsultantProfile
    base_currency: str
    invested_value: Decimal
    cash_value: Decimal
    watchlist_signal_count: int
    watchlist_signals: list[str] = Field(default_factory=list)
    exposure_summaries: list[ExposureSummary] = Field(default_factory=list)
    concentration_warnings: list[ConcentrationWarning] = Field(default_factory=list)
    gaps: list[PortfolioGap] = Field(default_factory=list)
    research_ideas: list[ResearchIdea] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    regulated_advice_boundary: str


class ConsultantRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_area: str
    summary: str
    trade_offs: list[str] = Field(default_factory=list)
    what_to_research: list[str] = Field(default_factory=list)
    product_guidance: str
    candidate_identifiers: list[str] = Field(default_factory=list)
    verified_factsheets: list[FactsheetSummary] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
