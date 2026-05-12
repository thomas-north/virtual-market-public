from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.dto.portfolio import PositionDTO
from vmarket.repositories import cash as cash_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.services.valuation_service import compute_positions
from vmarket.themes.models import (
    AllocationAnalysis,
    DecisionRule,
    ETFComparison,
    EtfProfile,
    HoldingsAlignment,
    PortfolioOverlapAnalysis,
    PortfolioThemeContext,
    RecommendationDecision,
    ThematicIdea,
    ThemeAnalysisRequest,
    ThemeAnalysisResult,
    ThemeCandidate,
    ThemeDefinition,
    ThemeHolding,
)
from vmarket.themes.store import find_profile, list_themes, load_theme


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _liq_score(bucket: str) -> float:
    return {"low": 45.0, "medium": 70.0, "high": 90.0}[bucket]


def _aum_score(bucket: str) -> float:
    return {"small": 50.0, "medium": 72.0, "large": 90.0}[bucket]


def _fee_score(profile: EtfProfile) -> float:
    fee_pct = profile.facts.ter_pct or profile.facts.ocf_pct or 0.75
    return max(30.0, 100.0 - fee_pct * 80.0)


def _top_holdings(profile: EtfProfile) -> list[ThemeHolding]:
    if profile.facts.top_holdings:
        return profile.facts.top_holdings
    if profile.facts.holdings:
        return profile.facts.holdings[:10]
    return []


def _preferred_aliases(profile: EtfProfile) -> set[str]:
    aliases = {_norm(item) for item in profile.preferred_company_aliases}
    for holding in _top_holdings(profile):
        aliases.add(_norm(holding.name))
        if holding.symbol:
            aliases.add(_norm(holding.symbol))
    return {alias for alias in aliases if alias}


def _overlap_aliases(profile: EtfProfile) -> set[str]:
    aliases = {_norm(item) for item in profile.overlap_aliases}
    for holding in _top_holdings(profile):
        aliases.add(_norm(holding.name))
        if holding.symbol:
            aliases.add(_norm(holding.symbol))
    return {alias for alias in aliases if alias}


def _position_aliases(position: PositionDTO) -> set[str]:
    aliases = {_norm(position.symbol)}
    if position.name:
        aliases.add(_norm(position.name))
    return aliases


def _pick_listing(profile: EtfProfile, investor_country: str) -> tuple[str, str, float]:
    listings = profile.facts.listings
    if not listings:
        return profile.profile_id, "USD", 55.0

    country = investor_country.upper()
    if country in {"GB", "UK"}:
        for listing in listings:
            if listing.currency.upper() == "GBP":
                return listing.symbol, listing.currency.upper(), 100.0
        for listing in listings:
            if listing.exchange.upper() == "LSE":
                return listing.symbol, listing.currency.upper(), 92.0
        for listing in listings:
            if listing.currency.upper() == "EUR":
                return listing.symbol, listing.currency.upper(), 72.0
        listing = listings[0]
        return listing.symbol, listing.currency.upper(), 55.0

    listing = listings[0]
    score = 100.0 if listing.currency.upper() == "USD" else 70.0
    return listing.symbol, listing.currency.upper(), score


def _build_allocation_analysis(
    amount: Decimal | None,
    invested_value: Decimal,
    visible_value: Decimal,
    allocation_currency: str,
) -> AllocationAnalysis:
    ratio: float | None = None
    size_bucket = "unspecified"
    if amount is not None and visible_value > 0:
        ratio = float(amount / visible_value)
        if ratio < 0.01:
            size_bucket = "small_satellite"
        elif ratio < 0.05:
            size_bucket = "satellite"
        elif ratio < 0.20:
            size_bucket = "meaningful_sleeve"
        else:
            size_bucket = "dominant_sleeve"

    if amount is None or invested_value == 0:
        comment = (
            "Without a fixed allocation, treat the output as provisional. "
            "Implementation quality and purity can swap places once sizing is known."
        )
    elif size_bucket == "small_satellite":
        comment = (
            "This is a very small sleeve relative to the visible portfolio, "
            "so a high-conviction implementation can be reasonable."
        )
    elif size_bucket == "satellite":
        comment = (
            "This is a satellite allocation. Purity can matter, "
            "but overlap and maintenance still deserve attention."
        )
    elif size_bucket == "meaningful_sleeve":
        comment = (
            "This is a meaningful sleeve. Diversification, simplicity, "
            "and risk control should matter alongside thematic purity."
        )
    else:
        comment = (
            "This is large relative to the visible portfolio, "
            "so implementation quality should dominate conviction purity."
        )

    return AllocationAnalysis(
        allocation_amount=amount,
        allocation_currency=allocation_currency,
        invested_portfolio_value=invested_value,
        visible_portfolio_value=visible_value,
        allocation_ratio=round(ratio, 4) if ratio is not None else None,
        size_bucket=size_bucket,
        sizing_comment=comment,
    )


def _build_portfolio_context(
    session: Session,
    theme: ThemeDefinition,
    request: ThemeAnalysisRequest,
) -> PortfolioThemeContext:
    portfolio = port_repo.get_or_create_default(session)
    positions = compute_positions(session, base_currency=portfolio.base_currency)
    cash_balances = cash_repo.get_balances_all_currencies(session, portfolio.id)

    invested_value = sum(
        (position.value_in_base for position in positions if position.value_in_base is not None),
        Decimal("0"),
    )
    position_count = len(positions)
    top_position_value = max(
        (position.value_in_base for position in positions if position.value_in_base is not None),
        default=Decimal("0"),
    )
    top_weight = float(top_position_value / invested_value) if invested_value else 0.0

    us_value = sum(
        (
            position.value_in_base
            for position in positions
            if position.value_in_base is not None and position.symbol.upper().endswith(".US")
        ),
        Decimal("0"),
    )
    us_weight = float(us_value / invested_value) if invested_value else 0.0

    currency_mix: dict[str, float] = {}
    for position in positions:
        if position.value_in_base is None or invested_value == 0:
            continue
        weight = float(position.value_in_base / invested_value)
        currency_mix[position.cost_currency] = (
            currency_mix.get(position.cost_currency, 0.0) + weight
        )

    visible_value = invested_value + sum(cash_balances.values(), Decimal("0"))

    theme_aliases: set[str] = set()
    growth_aliases: set[str] = set()
    for profile in theme.candidates:
        theme_aliases.update(_overlap_aliases(profile))
        if profile.growth_tilt >= 70:
            growth_aliases.update(_overlap_aliases(profile))
    if theme.starter_stock_basket:
        for holding in theme.starter_stock_basket.holdings:
            theme_aliases.add(_norm(holding.name))
            if holding.symbol:
                theme_aliases.add(_norm(holding.symbol))

    overlapping_current_holdings: list[str] = []
    overlap_value = Decimal("0")
    growth_overlap_value = Decimal("0")
    for position in positions:
        aliases = _position_aliases(position)
        if aliases & theme_aliases:
            overlapping_current_holdings.append(position.symbol)
            if position.value_in_base is not None:
                overlap_value += position.value_in_base
        if aliases & growth_aliases and position.value_in_base is not None:
            growth_overlap_value += position.value_in_base

    theme_overlap_ratio = float(overlap_value / invested_value) if invested_value else 0.0
    growth_overlap_ratio = float(growth_overlap_value / invested_value) if invested_value else 0.0

    allocation_analysis = _build_allocation_analysis(
        request.amount,
        invested_value,
        visible_value,
        request.allocation_currency or portfolio.base_currency,
    )
    suggested_role = (
        "core"
        if allocation_analysis.size_bucket in {"meaningful_sleeve", "dominant_sleeve"}
        else "satellite"
    )
    concentration_comment = (
        "Portfolio is already fairly concentrated in a few positions."
        if top_weight >= 0.25
        else "Portfolio concentration is moderate enough to support a focused satellite sleeve."
    )

    return PortfolioThemeContext(
        base_currency=portfolio.base_currency,
        invested_value=invested_value,
        cash_balances=cash_balances,
        position_count=position_count,
        top_position_weight=round(top_weight, 4),
        us_equity_weight=round(us_weight, 4),
        currency_mix={ccy: round(weight, 4) for ccy, weight in sorted(currency_mix.items())},
        theme_overlap_ratio=round(theme_overlap_ratio, 4),
        overlapping_current_holdings=sorted(overlapping_current_holdings),
        growth_overlap_ratio=round(growth_overlap_ratio, 4),
        suggested_role=suggested_role,
        concentration_comment=concentration_comment,
        allocation_analysis=allocation_analysis,
    )


def _resolved_role(request: ThemeAnalysisRequest, context: PortfolioThemeContext) -> str:
    if request.target_role != "auto":
        return request.target_role
    return context.suggested_role


def _alignment_from_aliases(
    aliases: set[str],
    preferred_companies: list[str],
) -> HoldingsAlignment:
    preferred = [_norm(item) for item in preferred_companies if item.strip()]
    if not preferred:
        return HoldingsAlignment(
            matched_preferred_companies=[],
            missing_preferred_companies=[],
            alignment_score=55.0,
            comment="No explicit preferred companies were provided.",
        )

    matched = [company for company in preferred_companies if _norm(company) in aliases]
    missing = [company for company in preferred_companies if _norm(company) not in aliases]
    score = 100.0 * len(matched) / len(preferred)
    comment = (
        f"Matched {len(matched)} of {len(preferred)} preferred companies."
        if matched
        else "No preferred companies were matched directly."
    )
    return HoldingsAlignment(
        matched_preferred_companies=matched,
        missing_preferred_companies=missing,
        alignment_score=round(score, 2),
        comment=comment,
    )


def _overlap_analysis(
    aliases: set[str],
    positions: list[PositionDTO],
    context: PortfolioThemeContext,
) -> PortfolioOverlapAnalysis:
    overlapping: list[str] = []
    for position in positions:
        if _position_aliases(position) & aliases:
            overlapping.append(position.symbol)
    if not positions:
        score = 0.0
    else:
        score = min(100.0, 100.0 * len(overlapping) / max(1, len(positions)))
    comment = (
        "No obvious direct overlap with current holdings."
        if not overlapping
        else f"Visible overlap already exists through {', '.join(sorted(overlapping))}."
    )
    return PortfolioOverlapAnalysis(
        overlap_score=round(score, 2),
        overlap_ratio=context.theme_overlap_ratio,
        overlapping_current_holdings=sorted(overlapping),
        comment=comment,
    )


def _size_fit_bonus(kind: str, size_bucket: str, preferred_count: int) -> tuple[float, float]:
    thematic_bonus = 0.0
    risk_bonus = 0.0
    if kind == "stock_basket":
        if size_bucket == "small_satellite":
            thematic_bonus += 10.0 + min(8.0, preferred_count * 1.5)
            risk_bonus -= 2.0
        elif size_bucket == "satellite":
            thematic_bonus += 5.0 + min(5.0, preferred_count)
            risk_bonus -= 6.0
        elif size_bucket == "meaningful_sleeve":
            thematic_bonus -= 3.0
            risk_bonus -= 12.0
        elif size_bucket == "dominant_sleeve":
            thematic_bonus -= 8.0
            risk_bonus -= 20.0
    else:
        if size_bucket == "meaningful_sleeve":
            risk_bonus += 8.0
        elif size_bucket == "dominant_sleeve":
            risk_bonus += 14.0
    return thematic_bonus, risk_bonus


def _basket_holdings(
    theme: ThemeDefinition,
    request: ThemeAnalysisRequest,
) -> tuple[list[ThemeHolding], str]:
    if request.preferred_companies:
        holdings = [
            ThemeHolding(
                name=company,
                weight=round(100 / len(request.preferred_companies), 2),
                tags=["preferred-company"],
            )
            for company in request.preferred_companies
        ]
        return holdings, "Built from the user’s preferred companies."

    if theme.starter_stock_basket and theme.starter_stock_basket.holdings:
        return theme.starter_stock_basket.holdings, theme.starter_stock_basket.rebalancing_note

    return [], "No starter stock basket is available for this theme."


def _basket_aliases(holdings: list[ThemeHolding]) -> set[str]:
    aliases: set[str] = set()
    for holding in holdings:
        aliases.add(_norm(holding.name))
        if holding.symbol:
            aliases.add(_norm(holding.symbol))
    return {alias for alias in aliases if alias}


def _candidate_decision(
    *,
    name: str,
    why_this_fits: str,
    main_risk: str,
    what_would_change: str,
    rules: list[DecisionRule],
) -> RecommendationDecision:
    return RecommendationDecision(
        why_this_fits=why_this_fits,
        alternatives_weaker=[],
        main_risk=main_risk,
        what_would_change=what_would_change,
        decision_rules=rules,
    )


def _etf_decision_rules(
    profile: EtfProfile,
    role: str,
    context: PortfolioThemeContext,
) -> list[DecisionRule]:
    rules = [
        DecisionRule(
            rule_key="purity",
            summary=profile.notes_purity,
            effect="supports thematic-fit scoring",
        ),
        DecisionRule(
            rule_key="concentration",
            summary=profile.notes_concentration,
            effect="affects risk-adjusted scoring",
        ),
    ]
    if role == "core":
        rules.append(
            DecisionRule(
                rule_key="role",
                summary=(
                    "Core-sized allocations put more weight on breadth "
                    "and implementation quality."
                ),
                effect="supports broader implementations",
            )
        )
    if context.theme_overlap_ratio > 0:
        rules.append(
            DecisionRule(
                rule_key="overlap",
                summary=(
                    "Existing theme overlap reduces the case for adding "
                    "another concentrated sleeve."
                ),
                effect="penalises overlap-heavy implementations",
            )
        )
    return rules


def _basket_decision_rules(
    size_bucket: str,
    preferred_companies: list[str],
) -> list[DecisionRule]:
    rules = [
        DecisionRule(
            rule_key="conviction",
            summary="An equal-weight basket expresses the theme through direct company conviction.",
            effect="supports thematic-fit scoring",
        ),
        DecisionRule(
            rule_key="maintenance",
            summary="Direct baskets require manual rebalancing and more monitoring than ETFs.",
            effect="reduces risk-adjusted scoring",
        ),
    ]
    if preferred_companies:
        rules.append(
            DecisionRule(
                rule_key="preferences",
                summary=(
                    "Preferred companies can make a direct basket a cleaner "
                    "expression than a blended ETF."
                ),
                effect="supports thematic-fit scoring",
            )
        )
    if size_bucket in {"meaningful_sleeve", "dominant_sleeve"}:
        rules.append(
            DecisionRule(
                rule_key="size",
                summary="Large allocations penalise concentrated baskets more heavily.",
                effect="reduces risk-adjusted scoring",
            )
        )
    return rules


def _score_etf_candidate(
    profile: EtfProfile,
    request: ThemeAnalysisRequest,
    context: PortfolioThemeContext,
    positions: list[PositionDTO],
) -> ThemeCandidate:
    role = _resolved_role(request, context)
    listing_symbol, listing_currency, listing_suitability = _pick_listing(
        profile, request.investor_country
    )
    aliases = _preferred_aliases(profile)
    alignment = _alignment_from_aliases(aliases, request.preferred_companies)
    overlap = _overlap_analysis(_overlap_aliases(profile), positions, context)
    liquidity_score = _liq_score(profile.liquidity_bucket)
    fee_score = _fee_score(profile)
    aum_score = _aum_score(profile.aum_bucket)
    diversification_score = max(
        35.0,
        min(
            92.0,
            (100 - profile.concentration_risk) * 0.70
            + min(22.0, (profile.facts.holdings_count or len(_top_holdings(profile))) * 0.6),
        ),
    )
    simplicity_score = 92.0
    conviction_score = float(profile.purity_score)
    rebalancing_burden_score = 96.0

    thematic_bonus, risk_bonus = _size_fit_bonus(
        "etf",
        context.allocation_analysis.size_bucket,
        len(request.preferred_companies),
    )
    thematic_fit_score = (
        profile.purity_score * 0.26
        + alignment.alignment_score * 0.22
        + conviction_score * 0.10
        + diversification_score * (0.12 if role == "core" else 0.06)
        + listing_suitability * 0.08
        + liquidity_score * 0.08
        + fee_score * 0.08
        + simplicity_score * 0.05
        - overlap.overlap_score * 0.16
        + thematic_bonus
    )
    risk_adjusted_score = (
        diversification_score * 0.20
        + simplicity_score * 0.18
        + rebalancing_burden_score * 0.10
        + liquidity_score * 0.12
        + aum_score * 0.10
        + fee_score * 0.08
        + listing_suitability * 0.08
        + (100 - profile.volatility_risk) * 0.10
        + (100 - profile.concentration_risk) * 0.10
        - overlap.overlap_score * 0.12
        + risk_bonus
    )
    warnings = []
    if context.theme_overlap_ratio >= 0.20:
        warnings.append("Existing holdings already create meaningful overlap with this theme.")
    if request.volatility_tolerance == "low" and profile.volatility_risk >= 70:
        warnings.append("This ETF is aggressive relative to the stated volatility tolerance.")
    if request.investor_country.upper() in {"GB", "UK"} and listing_currency != "GBP":
        warnings.append("This ETF does not have a GBP-first listing in the starter reference set.")

    why_this_fits = (
        f"{profile.profile_id} fits because it combines {profile.notes_purity.lower()} "
        f"with {profile.notes_concentration.lower()}"
    )
    main_risk = (
        "The main risk is that the fund is still concentrated and theme-sensitive."
        if profile.concentration_risk >= 55 or profile.volatility_risk >= 65
        else "The main risk is lower thematic purity versus a more focused implementation."
    )
    what_would_change = (
        "A smaller, higher-conviction sleeve or stronger company preferences "
        "would improve the case "
        "for a concentrated implementation."
    )
    recommendation = _candidate_decision(
        name=profile.profile_id,
        why_this_fits=why_this_fits,
        main_risk=main_risk,
        what_would_change=what_would_change,
        rules=_etf_decision_rules(profile, role, context),
    )

    return ThemeCandidate(
        implementation_kind="etf",
        profile_id=profile.profile_id,
        name=profile.name,
        issuer=profile.issuer,
        listing_symbol=listing_symbol,
        listing_currency=listing_currency,
        rationale=profile.summary,
        thematic_fit_score=round(thematic_fit_score, 2),
        risk_adjusted_score=round(risk_adjusted_score, 2),
        diversification_score=round(diversification_score, 2),
        simplicity_score=round(simplicity_score, 2),
        conviction_score=round(conviction_score, 2),
        rebalancing_burden_score=round(rebalancing_burden_score, 2),
        preferred_company_alignment=alignment.alignment_score,
        overlap_score=overlap.overlap_score,
        listing_suitability_score=round(listing_suitability, 2),
        liquidity_score=round(liquidity_score, 2),
        fee_score=round(fee_score, 2),
        matched_preferred_companies=alignment.matched_preferred_companies,
        overlapping_holdings=overlap.overlapping_current_holdings,
        warnings=warnings,
        purity_score=profile.purity_score,
        concentration_risk=profile.concentration_risk,
        volatility_risk=profile.volatility_risk,
        holdings=_top_holdings(profile),
        holdings_alignment=alignment,
        portfolio_overlap=overlap,
        recommendation=recommendation,
    )


def _score_basket_candidate(
    theme: ThemeDefinition,
    request: ThemeAnalysisRequest,
    context: PortfolioThemeContext,
    positions: list[PositionDTO],
) -> ThemeCandidate | None:
    holdings, note = _basket_holdings(theme, request)
    if not holdings:
        return None

    aliases = _basket_aliases(holdings)
    alignment = _alignment_from_aliases(aliases, request.preferred_companies)
    overlap = _overlap_analysis(aliases, positions, context)
    name = (
        "Preferred-company equal-weight basket"
        if request.preferred_companies
        else (
            theme.starter_stock_basket.name
            if theme.starter_stock_basket
            else "Starter equal-weight basket"
        )
    )
    holdings_count = len(holdings)
    diversity_from_count = min(78.0, 22.0 + holdings_count * 8.0)
    concentration_risk = max(42, 92 - holdings_count * 8)
    volatility_risk = min(
        88,
        max(52, 74 - holdings_count * 2 + (0 if request.preferred_companies else 6)),
    )
    diversification_score = round(100 - concentration_risk * 0.65 + diversity_from_count * 0.35, 2)
    simplicity_score = max(28.0, 62.0 - holdings_count * 4.0)
    conviction_score = 95.0 if request.preferred_companies else 84.0
    rebalancing_burden_score = max(20.0, 60.0 - holdings_count * 4.0)
    liquidity_score = 72.0
    listing_suitability = 84.0
    fee_score = 98.0
    purity_score = 94 if request.preferred_companies else 88

    thematic_bonus, risk_bonus = _size_fit_bonus(
        "stock_basket",
        context.allocation_analysis.size_bucket,
        len(request.preferred_companies),
    )
    thematic_fit_score = (
        purity_score * 0.24
        + alignment.alignment_score * 0.24
        + conviction_score * 0.18
        + fee_score * 0.08
        + diversification_score * 0.08
        + simplicity_score * 0.04
        - overlap.overlap_score * 0.18
        + thematic_bonus
    )
    risk_adjusted_score = (
        diversification_score * 0.16
        + simplicity_score * 0.12
        + rebalancing_burden_score * 0.14
        + liquidity_score * 0.08
        + fee_score * 0.10
        + listing_suitability * 0.06
        + (100 - volatility_risk) * 0.14
        + (100 - concentration_risk) * 0.12
        - overlap.overlap_score * 0.14
        + risk_bonus
    )
    why_this_fits = (
        "The basket fits when direct conviction in a handful of companies "
        "matters more than fund simplicity."
    )
    main_risk = (
        "The main risk is concentration plus the ongoing burden of "
        "monitoring and rebalancing."
    )
    what_would_change = (
        "A larger allocation, lower tolerance for maintenance, or a desire "
        "for broader diversification "
        "would strengthen the case for an ETF."
    )
    recommendation = _candidate_decision(
        name=name,
        why_this_fits=why_this_fits,
        main_risk=main_risk,
        what_would_change=what_would_change,
        rules=_basket_decision_rules(
            context.allocation_analysis.size_bucket,
            request.preferred_companies,
        ),
    )

    return ThemeCandidate(
        implementation_kind="stock_basket",
        profile_id=f"{theme.theme_id}-basket",
        name=name,
        issuer="Direct basket",
        listing_symbol=None,
        listing_currency=request.allocation_currency or context.base_currency,
        rationale=note,
        thematic_fit_score=round(thematic_fit_score, 2),
        risk_adjusted_score=round(risk_adjusted_score, 2),
        diversification_score=round(diversification_score, 2),
        simplicity_score=round(simplicity_score, 2),
        conviction_score=round(conviction_score, 2),
        rebalancing_burden_score=round(rebalancing_burden_score, 2),
        preferred_company_alignment=alignment.alignment_score,
        overlap_score=overlap.overlap_score,
        listing_suitability_score=round(listing_suitability, 2),
        liquidity_score=round(liquidity_score, 2),
        fee_score=round(fee_score, 2),
        matched_preferred_companies=alignment.matched_preferred_companies,
        overlapping_holdings=overlap.overlapping_current_holdings,
        warnings=["Direct stock baskets require manual rebalancing and trade execution."],
        purity_score=purity_score,
        concentration_risk=concentration_risk,
        volatility_risk=volatility_risk,
        holdings=holdings,
        holdings_alignment=alignment,
        portfolio_overlap=overlap,
        recommendation=recommendation,
    )


def _position_sizing_guidance(context: PortfolioThemeContext) -> str:
    return context.allocation_analysis.sizing_comment


def _overlap_summary(context: PortfolioThemeContext, theme: ThemeDefinition) -> str:
    if not context.overlapping_current_holdings:
        return f"No current holdings were matched to the starter {theme.label} reference basket."
    symbols = ", ".join(context.overlapping_current_holdings)
    return (
        f"Current {theme.label} adjacency is already present through {symbols}. "
        "That raises the importance of overlap control and role clarity."
    )


def _why_changed(
    best_fit: ThemeCandidate,
    best_risk: ThemeCandidate,
    context: PortfolioThemeContext,
) -> str:
    if best_fit.profile_id == best_risk.profile_id:
        return (
            f"{best_fit.profile_id} leads on both thematic fit and risk-adjusted implementation, "
            "so the visible inputs do not create a major trade-off."
        )

    return (
        "The recommendation changes because the strongest expression of the theme is not always "
        "the cleanest implementation for the visible portfolio size, overlap, "
        "and maintenance burden."
    )


def _alternative_reason(best: ThemeCandidate, other: ThemeCandidate) -> str:
    if other.implementation_kind == "stock_basket":
        return (
            f"{other.name} is a weaker fit here because it demands more monitoring "
            "and carries more "
            "single-name concentration than the chosen implementation."
        )
    if best.purity_score > other.purity_score and best.implementation_kind == "etf":
        return (
            f"{other.profile_id} is a weaker fit because it is less aligned with the stated theme "
            "or the preferred companies."
        )
    return (
        f"{other.profile_id} is a weaker fit because it trades away too much simplicity, purity, "
        "or diversification for this portfolio context."
    )


def _with_decision_tradeoffs(
    winner: ThemeCandidate,
    ordered_candidates: list[ThemeCandidate],
) -> ThemeCandidate:
    alternatives = [
        _alternative_reason(winner, candidate)
        for candidate in ordered_candidates
        if candidate.profile_id != winner.profile_id
    ][:3]
    return winner.model_copy(
        update={
            "recommendation": winner.recommendation.model_copy(
                update={"alternatives_weaker": alternatives}
            )
        }
    )


def _etf_comparisons(candidates: list[ThemeCandidate]) -> list[ETFComparison]:
    etf_candidates = [
        candidate for candidate in candidates if candidate.implementation_kind == "etf"
    ]
    if not etf_candidates:
        return []
    best_etf = max(etf_candidates, key=lambda candidate: candidate.thematic_fit_score)
    comparisons: list[ETFComparison] = []
    for candidate in etf_candidates:
        if candidate.profile_id == best_etf.profile_id:
            continue
        weaker = _alternative_reason(best_etf, candidate)
        stronger = (
            f"{candidate.profile_id} still offers a useful alternative if you want "
            "more breadth, lower volatility, or simpler implementation trade-offs."
        )
        comparisons.append(
            ETFComparison(
                compared_against=candidate.profile_id,
                weaker_fit_reason=weaker,
                stronger_fit_reason=stronger,
            )
        )
    return comparisons


def _build_candidates(
    theme: ThemeDefinition,
    request: ThemeAnalysisRequest,
    context: PortfolioThemeContext,
    positions: list[PositionDTO],
) -> list[ThemeCandidate]:
    candidates: list[ThemeCandidate] = []
    if request.implementation_scope in {"etf", "both"}:
        candidates.extend(
            _score_etf_candidate(profile, request, context, positions)
            for profile in theme.candidates
        )
    if request.implementation_scope in {"basket", "both"}:
        basket = _score_basket_candidate(theme, request, context, positions)
        if basket is not None:
            candidates.append(basket)
    return candidates


def analyze_theme(session: Session, request: ThemeAnalysisRequest) -> ThemeAnalysisResult:
    theme = load_theme(request.theme)
    if theme is None:
        raise ValueError(f"Unsupported theme: {request.theme}")

    portfolio = port_repo.get_or_create_default(session)
    if request.allocation_currency is None:
        request = request.model_copy(update={"allocation_currency": portfolio.base_currency})

    positions = compute_positions(session, base_currency=portfolio.base_currency)
    context = _build_portfolio_context(session, theme, request)
    candidates = _build_candidates(theme, request, context, positions)
    if not candidates:
        raise ValueError(
            f"No implementation candidates are available for theme {theme.theme_id} "
            f"with scope {request.implementation_scope}."
        )

    ranked_fit = sorted(
        candidates,
        key=lambda candidate: candidate.thematic_fit_score,
        reverse=True,
    )
    ranked_risk = sorted(
        candidates,
        key=lambda candidate: candidate.risk_adjusted_score,
        reverse=True,
    )
    best_fit = _with_decision_tradeoffs(ranked_fit[0], ranked_fit)
    best_risk = _with_decision_tradeoffs(ranked_risk[0], ranked_risk)

    warnings = [
        "Uses curated starter metadata rather than live ETF factsheet ingestion.",
        "This is decision support for a simulated portfolio, not regulated financial advice.",
    ]
    for candidate in candidates:
        for warning in candidate.warnings:
            if warning not in warnings:
                warnings.append(warning)

    thematic_idea = ThematicIdea(
        theme_id=theme.theme_id,
        theme_label=theme.label,
        summary=theme.summary,
        implementation_scope=request.implementation_scope,
        target_role=request.target_role,
    )

    return ThemeAnalysisResult(
        theme=theme.theme_id,
        theme_label=theme.label,
        theme_summary=theme.summary,
        request=request,
        thematic_idea=thematic_idea,
        portfolio_context=context,
        best_thematic_fit=best_fit,
        best_risk_adjusted_option=best_risk,
        candidates=ranked_fit,
        etf_comparisons=_etf_comparisons(candidates),
        portfolio_overlap_summary=_overlap_summary(context, theme),
        position_sizing_guidance=_position_sizing_guidance(context),
        implementation_warnings=warnings,
        explanation_of_why_result_changed=_why_changed(best_fit, best_risk, context),
        best_thematic_fit_decision=best_fit.recommendation,
        best_risk_adjusted_decision=best_risk.recommendation,
        analysis_disclaimer=(
            f"Reference set last reviewed {theme.refresh.as_of}. "
            f"{theme.refresh.notes}"
        ),
    )


def discuss_theme(session: Session, request: ThemeAnalysisRequest) -> ThemeAnalysisResult:
    return analyze_theme(session, request)


def compare_etfs(identifiers: list[str]) -> list[tuple[ThemeDefinition, EtfProfile]]:
    matches: list[tuple[ThemeDefinition, EtfProfile]] = []
    seen: set[str] = set()
    for identifier in identifiers:
        match = find_profile(identifier)
        if match is None:
            raise ValueError(f"Unknown ETF profile: {identifier}")
        theme, profile = match
        if profile.profile_id in seen:
            continue
        seen.add(profile.profile_id)
        matches.append((theme, profile))
    return matches


def compare_ideas(session: Session, request: ThemeAnalysisRequest) -> ThemeAnalysisResult:
    return analyze_theme(session, request)


def list_supported_themes() -> list[ThemeDefinition]:
    return list_themes()
