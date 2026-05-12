from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VolatilityTolerance = Literal["low", "medium", "high"]
TimeHorizon = Literal["short", "medium", "long"]
TargetRole = Literal["core", "satellite", "auto"]
LiquidityBucket = Literal["low", "medium", "high"]
AumBucket = Literal["small", "medium", "large"]
DistributionPolicy = Literal["accumulating", "distributing", "mixed"]
ImplementationKind = Literal["etf", "stock_basket"]
ImplementationScope = Literal["etf", "basket", "both"]
SizeBucket = Literal[
    "unspecified",
    "small_satellite",
    "satellite",
    "meaningful_sleeve",
    "dominant_sleeve",
]


class ThemeHolding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    symbol: str | None = None
    weight: float | None = None
    tags: list[str] = Field(default_factory=list)


class ThemeListing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    currency: str
    exchange: str
    is_primary: bool = False


class RefreshMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date
    source_type: str
    notes: str


class EtfStoredFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_holdings: list[ThemeHolding] = Field(default_factory=list)
    holdings: list[ThemeHolding] = Field(default_factory=list)
    holdings_count: int | None = None
    ter_pct: float | None = None
    ocf_pct: float | None = None
    aum_usd_millions: float | None = None
    volatility_3y_pct: float | None = None
    methodology_summary: str | None = None
    domicile: str | None = None
    distribution_policy: DistributionPolicy | None = None
    listings: list[ThemeListing] = Field(default_factory=list)
    listing_currencies: list[str] = Field(default_factory=list)
    source_notes: str | None = None


class EtfProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    name: str
    issuer: str
    summary: str
    theme_tags: list[str] = Field(default_factory=list)
    facts: EtfStoredFacts
    liquidity_bucket: LiquidityBucket
    aum_bucket: AumBucket
    purity_score: int = Field(ge=0, le=100)
    concentration_risk: int = Field(ge=0, le=100)
    volatility_risk: int = Field(ge=0, le=100)
    growth_tilt: int = Field(ge=0, le=100)
    infrastructure_tilt: int = Field(ge=0, le=100)
    notes_purity: str
    notes_concentration: str
    preferred_company_aliases: list[str] = Field(default_factory=list)
    overlap_aliases: list[str] = Field(default_factory=list)
    status: str = "starter_reference"
    facts_last_reviewed: date


class StockBasketTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basket_id: str
    name: str
    summary: str
    holdings: list[ThemeHolding] = Field(default_factory=list)
    rebalancing_note: str


class ThemeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str
    label: str
    summary: str
    refresh: RefreshMetadata
    keywords: list[str] = Field(default_factory=list)
    candidates: list[EtfProfile] = Field(default_factory=list)
    starter_stock_basket: StockBasketTemplate | None = None


class ThemeAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    amount: Decimal | None = None
    allocation_currency: str | None = None
    investor_country: str = "GB"
    preferred_companies: list[str] = Field(default_factory=list)
    volatility_tolerance: VolatilityTolerance = "medium"
    time_horizon: TimeHorizon = "long"
    target_role: TargetRole = "auto"
    implementation_scope: ImplementationScope = "both"


class ThematicIdea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str
    theme_label: str
    summary: str
    implementation_scope: ImplementationScope
    target_role: TargetRole


class AllocationAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allocation_amount: Decimal | None = None
    allocation_currency: str
    invested_portfolio_value: Decimal
    visible_portfolio_value: Decimal
    allocation_ratio: float | None = None
    size_bucket: SizeBucket
    sizing_comment: str


class PortfolioOverlapAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overlap_score: float
    overlap_ratio: float
    overlapping_current_holdings: list[str] = Field(default_factory=list)
    comment: str


class HoldingsAlignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched_preferred_companies: list[str] = Field(default_factory=list)
    missing_preferred_companies: list[str] = Field(default_factory=list)
    alignment_score: float
    comment: str


class DecisionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_key: str
    summary: str
    effect: str


class ETFComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compared_against: str
    weaker_fit_reason: str
    stronger_fit_reason: str | None = None


class RecommendationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    why_this_fits: str
    alternatives_weaker: list[str] = Field(default_factory=list)
    main_risk: str
    what_would_change: str
    decision_rules: list[DecisionRule] = Field(default_factory=list)


class PortfolioThemeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_currency: str
    invested_value: Decimal
    cash_balances: dict[str, Decimal] = Field(default_factory=dict)
    position_count: int
    top_position_weight: float
    us_equity_weight: float
    currency_mix: dict[str, float] = Field(default_factory=dict)
    theme_overlap_ratio: float
    overlapping_current_holdings: list[str] = Field(default_factory=list)
    growth_overlap_ratio: float
    suggested_role: Literal["core", "satellite"]
    concentration_comment: str
    allocation_analysis: AllocationAnalysis


class ThemeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    implementation_kind: ImplementationKind
    profile_id: str
    name: str
    issuer: str | None = None
    listing_symbol: str | None = None
    listing_currency: str | None = None
    rationale: str
    thematic_fit_score: float
    risk_adjusted_score: float
    diversification_score: float
    simplicity_score: float
    conviction_score: float
    rebalancing_burden_score: float
    preferred_company_alignment: float
    overlap_score: float
    listing_suitability_score: float
    liquidity_score: float
    fee_score: float
    matched_preferred_companies: list[str] = Field(default_factory=list)
    overlapping_holdings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    purity_score: int
    concentration_risk: int
    volatility_risk: int
    holdings: list[ThemeHolding] = Field(default_factory=list)
    holdings_alignment: HoldingsAlignment
    portfolio_overlap: PortfolioOverlapAnalysis
    recommendation: RecommendationDecision
    weaker_fit_reason: str | None = None


class ThemeAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    theme_label: str
    theme_summary: str
    request: ThemeAnalysisRequest
    thematic_idea: ThematicIdea
    portfolio_context: PortfolioThemeContext
    best_thematic_fit: ThemeCandidate
    best_risk_adjusted_option: ThemeCandidate
    candidates: list[ThemeCandidate]
    etf_comparisons: list[ETFComparison] = Field(default_factory=list)
    portfolio_overlap_summary: str
    position_sizing_guidance: str
    implementation_warnings: list[str] = Field(default_factory=list)
    explanation_of_why_result_changed: str
    best_thematic_fit_decision: RecommendationDecision
    best_risk_adjusted_decision: RecommendationDecision
    analysis_disclaimer: str
