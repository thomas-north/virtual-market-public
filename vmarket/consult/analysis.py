from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from vmarket.consult.factsheets import locate_factsheet
from vmarket.consult.models import (
    ConcentrationWarning,
    ConsultantProfile,
    ConsultantRecommendation,
    ExposureSummary,
    FactsheetSummary,
    PortfolioConsultRequest,
    PortfolioDiagnosis,
    PortfolioGap,
    ResearchIdea,
    UserConstraint,
    WeightedExposure,
)
from vmarket.consult.profile import get_profile, merge_request_with_profile
from vmarket.consult.store import load_classifications, load_research_areas
from vmarket.repositories import cash as cash_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.services.valuation_service import compute_positions
from vmarket.services.watchlist_service import list_watchlist

RISK_LABELS = {
    1: "capital preservation",
    2: "cautious",
    3: "balanced cautious",
    4: "balanced/moderate",
    5: "growth-oriented",
    6: "adventurous",
    7: "speculative/high concentration tolerance",
}


def _clean_label(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def _classifications(reference_root: Path | None = None) -> dict:
    return load_classifications(reference_root=reference_root)


def _find_symbol_entry(symbol: str, reference_root: Path | None = None) -> dict | None:
    data = _classifications(reference_root=reference_root)
    return data.get("symbols", {}).get(symbol.upper())


def _keyword_entry(text: str, reference_root: Path | None = None) -> dict | None:
    data = _classifications(reference_root=reference_root)
    lowered = text.lower()
    for entry in data.get("watchlist_keywords", []):
        if any(keyword.lower() in lowered for keyword in entry.get("keywords", [])):
            return entry
    return None


def _infer_profile(
    session: Session, explicit_risk: int | None, reference_root: Path | None = None
) -> tuple[int, str]:
    if explicit_risk is not None:
        return explicit_risk, "explicit"

    profile = get_profile(session)
    if profile.risk_score is not None:
        return profile.risk_score, "profile"

    watchlist = list_watchlist(session)
    score = 4
    for item in watchlist:
        signal = _keyword_entry(
            item.instrument.name or item.instrument.symbol, reference_root=reference_root
        )
        if signal and signal.get("risk_hint"):
            score = max(score, int(signal["risk_hint"]))

    positions = compute_positions(session, base_currency=profile.base_currency)
    top_tech = 0
    for position in positions:
        entry = _find_symbol_entry(position.symbol, reference_root=reference_root)
        sectors = entry.get("sectors", []) if entry else []
        if "technology" in sectors and position.value_in_base is not None:
            top_tech += 1
    if top_tech >= 3:
        score = max(score, 5)
    return score, "inferred"


def _effective_profile(
    session: Session,
    request: PortfolioConsultRequest,
    reference_root: Path | None = None,
) -> tuple[ConsultantProfile, str]:
    profile = merge_request_with_profile(get_profile(session), request)
    inferred_score, source = _infer_profile(
        session, request.risk_score, reference_root=reference_root
    )
    if profile.risk_score is None:
        profile.risk_score = inferred_score
        return profile, source
    if request.risk_score is not None:
        return profile, "explicit"
    return profile, "profile"


def _instrument_dimensions(
    symbol: str, name: str | None, asset_type: str | None, reference_root: Path | None = None
) -> dict[str, list[str]]:
    entry = _find_symbol_entry(symbol, reference_root=reference_root)
    if entry:
        return {
            "geography": entry.get("geographies", []),
            "sector": entry.get("sectors", []),
            "style": entry.get("styles", []),
            "asset_type": [entry.get("asset_type")] if entry.get("asset_type") else [],
            "themes": entry.get("themes", []),
        }

    clean_name = (name or symbol).lower()
    geographies = (
        ["UK"]
        if symbol.upper().endswith(".L") or len(symbol) == 7
        else ["US"]
        if symbol.upper().endswith(".US")
        else ["Global"]
    )
    sectors = (
        ["technology"]
        if any(
            term in clean_name
            for term in [
                "apple",
                "alphabet",
                "cloudflare",
                "broadcom",
                "meta",
                "crowdstrike",
                "palo alto",
            ]
        )
        else []
    )
    styles = ["growth"] if "technology" in sectors else []
    inferred_asset = asset_type or ("stock" if symbol.upper().endswith(".US") else "fund")
    return {
        "geography": geographies,
        "sector": sectors or ["unclassified"],
        "style": styles or ["core"],
        "asset_type": [inferred_asset],
        "themes": [],
    }


def _weighted_exposure(items: list[tuple[list[str], Decimal]]) -> list[WeightedExposure]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    portfolio_total = sum((value for _, value in items), Decimal("0"))
    if portfolio_total <= 0:
        return []
    for labels, value in items:
        if not labels:
            continue
        share = value / Decimal(len(labels))
        for label in labels:
            totals[label] += share
    return [
        WeightedExposure(label=label, weight=round(float(value / portfolio_total), 4))
        for label, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def _watchlist_signals(
    session: Session, reference_root: Path | None = None
) -> tuple[list[str], Counter[str]]:
    items = list_watchlist(session)
    signals: list[str] = []
    counts: Counter[str] = Counter()
    for item in items:
        text = f"{item.instrument.symbol} {item.instrument.name or ''}"
        keyword = _keyword_entry(text, reference_root=reference_root)
        if keyword is None:
            continue
        label = keyword["label"]
        counts[label] += 1
    for label, count in counts.most_common():
        signals.append(f"Watchlist repeatedly points toward {label} ({count} items).")
    return signals, counts


def _constraints(profile: ConsultantProfile) -> list[UserConstraint]:
    constraints: list[UserConstraint] = []
    for exclusion in profile.exclusions:
        constraints.append(
            UserConstraint(constraint_type="exclusion", value=exclusion, source="profile")
        )
    if profile.distribution_preference:
        constraints.append(
            UserConstraint(
                constraint_type="distribution_preference",
                value=profile.distribution_preference,
                source="profile",
            )
        )
    if profile.prefers_uk_listed:
        constraints.append(
            UserConstraint(
                constraint_type="listing_preference", value="UK-listed lines", source="profile"
            )
        )
    if profile.prefers_gbp_lines:
        constraints.append(
            UserConstraint(
                constraint_type="currency_preference", value="GBP trading lines", source="profile"
            )
        )
    return constraints


def _make_exposure_summaries(
    positions,
    base_currency: str,
    reference_root: Path | None = None,
) -> tuple[list[ExposureSummary], dict[str, list[WeightedExposure]], Decimal]:
    grouped: dict[str, list[tuple[list[str], Decimal]]] = defaultdict(list)
    invested = Decimal("0")
    for position in positions:
        if position.value_in_base is None:
            continue
        invested += position.value_in_base
        dims = _instrument_dimensions(
            position.symbol, position.name, "stock", reference_root=reference_root
        )
        grouped["geography"].append((dims["geography"], position.value_in_base))
        grouped["sector"].append((dims["sector"], position.value_in_base))
        grouped["style"].append((dims["style"], position.value_in_base))
        grouped["asset_type"].append((dims["asset_type"], position.value_in_base))
        grouped["currency"].append(([position.cost_currency], position.value_in_base))
    summaries: list[ExposureSummary] = []
    computed: dict[str, list[WeightedExposure]] = {}
    for dimension, items in grouped.items():
        exposures = _weighted_exposure(items)
        computed[dimension] = exposures
        headline = (
            ", ".join(f"{item.label} {item.weight:.0%}" for item in exposures[:3]) or "No data"
        )
        comment = f"Top {dimension} exposures are {headline.lower()}."
        if dimension == "currency" and exposures and exposures[0].weight >= 0.6:
            comment = (
                f"{exposures[0].label} is the dominant currency exposure "
                f"relative to {base_currency}."
            )
        summaries.append(
            ExposureSummary(
                dimension=dimension,
                headline=headline,
                exposures=exposures[:5],
                comment=comment,
            )
        )
    return summaries, computed, invested


def _top_weight(positions) -> tuple[str | None, float]:
    total = sum((position.value_in_base or Decimal("0") for position in positions), Decimal("0"))
    if total <= 0:
        return None, 0.0
    top = max(positions, key=lambda position: position.value_in_base or Decimal("0"), default=None)
    if top is None or top.value_in_base is None:
        return None, 0.0
    return top.symbol, float(top.value_in_base / total)


def _concentration_warnings(
    positions,
    exposures: dict[str, list[WeightedExposure]],
    watchlist_counts: Counter[str],
) -> list[ConcentrationWarning]:
    warnings: list[ConcentrationWarning] = []
    top_symbol, top_weight = _top_weight(positions)
    total = sum((position.value_in_base or Decimal("0") for position in positions), Decimal("0"))
    top_five = sorted(
        [position.value_in_base or Decimal("0") for position in positions],
        reverse=True,
    )[:5]
    top_five_weight = float(sum(top_five, Decimal("0")) / total) if total > 0 else 0.0
    if top_symbol and top_weight >= 0.25:
        warnings.append(
            ConcentrationWarning(
                warning_key="single-holding",
                severity="high",
                summary=f"{top_symbol} is a very large single-position risk.",
                details=f"The largest holding is roughly {top_weight:.0%} of invested assets.",
            )
        )
    if top_five_weight >= 0.65:
        warnings.append(
            ConcentrationWarning(
                warning_key="top-five",
                severity="medium",
                summary="The top five positions dominate the portfolio.",
                details=f"Top five holdings are about {top_five_weight:.0%} of invested assets.",
            )
        )
    sector_top = exposures.get("sector", [])
    if sector_top and sector_top[0].label == "technology" and sector_top[0].weight >= 0.4:
        warnings.append(
            ConcentrationWarning(
                warning_key="technology-tilt",
                severity="high",
                summary="Technology is already a large return driver.",
                details=(
                    "Adding another software, AI, or semiconductor idea may deepen "
                    "the same concentration."
                ),
            )
        )
    geo_top = exposures.get("geography", [])
    if geo_top and geo_top[0].label == "US" and geo_top[0].weight >= 0.55:
        warnings.append(
            ConcentrationWarning(
                warning_key="us-tilt",
                severity="medium",
                summary="The portfolio is heavily tilted toward the U.S.",
                details=(
                    "Diversification ideas should be judged against the current U.S. mega-cap bias."
                ),
            )
        )
    if watchlist_counts.get("cybersecurity", 0) >= 2 and any(
        warning.warning_key == "technology-tilt" for warning in warnings
    ):
        warnings.append(
            ConcentrationWarning(
                warning_key="watchlist-duplicates",
                severity="medium",
                summary="The watchlist reinforces themes already dominant in the portfolio.",
                details=(
                    "Treat watchlist enthusiasm as user intent, but flag that it "
                    "may duplicate current exposure."
                ),
            )
        )
    return warnings


def _gap_and_idea_scores(
    profile: ConsultantProfile,
    exposures: dict[str, list[WeightedExposure]],
    warnings: list[ConcentrationWarning],
    watchlist_counts: Counter[str],
    reference_root: Path | None = None,
) -> tuple[list[PortfolioGap], list[ResearchIdea]]:
    ideas: list[ResearchIdea] = []
    gaps: list[PortfolioGap] = []
    sector_weights = {item.label: item.weight for item in exposures.get("sector", [])}
    geo_weights = {item.label: item.weight for item in exposures.get("geography", [])}
    style_weights = {item.label: item.weight for item in exposures.get("style", [])}
    templates = load_research_areas(reference_root=reference_root)
    for template in templates:
        min_risk = int(template.get("min_risk", 1))
        max_risk = int(template.get("max_risk", 7))
        if profile.risk_score is None or not (min_risk <= profile.risk_score <= max_risk):
            continue
        if any(
            _clean_label(exclusion) in template.get("excluded_by", [])
            for exclusion in profile.exclusions
        ):
            continue
        score = 0
        if template["area_id"] == "uk-mid-caps":
            if geo_weights.get("UK", 0.0) < 0.12:
                score += 3
                gaps.append(
                    PortfolioGap(
                        gap_key="low-uk-equity",
                        summary="UK growth exposure looks light.",
                        rationale=(
                            "The portfolio has limited direct UK equity exposure "
                            "relative to its current growth bias."
                        ),
                        priority="medium",
                    )
                )
            if watchlist_counts.get("uk equities", 0):
                score += 2
        if template["area_id"] == "healthcare-diversifier":
            if (
                sector_weights.get("healthcare", 0.0) < 0.08
                and sector_weights.get("technology", 0.0) >= 0.30
            ):
                score += 4
                gaps.append(
                    PortfolioGap(
                        gap_key="low-healthcare",
                        summary="Healthcare is underrepresented relative to technology.",
                        rationale=(
                            "Healthcare can diversify software and semiconductor-heavy "
                            "return drivers."
                        ),
                        priority="high",
                    )
                )
        if template["area_id"] == "global-value-income":
            if style_weights.get("growth", 0.0) >= 0.35 and profile.risk_score <= 5:
                score += 3
        if template["area_id"] == "short-duration-bonds":
            if profile.risk_score <= 3:
                score += 4
        if template["area_id"] == "emerging-markets":
            if geo_weights.get("Emerging Markets", 0.0) < 0.05 and profile.risk_score >= 5:
                score += 2
        if template["area_id"] == "global-small-caps":
            if style_weights.get("large-cap", 0.0) >= 0.4 and profile.risk_score >= 5:
                score += 2
        if any(warning.warning_key in template.get("trigger_warnings", []) for warning in warnings):
            score += 2
        if score <= 0:
            continue
        ideas.append(
            ResearchIdea(
                area_id=template["area_id"],
                area=template["label"],
                summary=template["summary"],
                why_now=template["why_now"],
                fit_for_risk=(
                    f"Best aligned with risk scores {min_risk}–{max_risk}. "
                    f"Current profile maps to {RISK_LABELS.get(profile.risk_score or 4)}."
                ),
                main_risks=template.get("main_risks", []),
                suitable_product_types=template.get("product_types", []),
                candidate_identifiers=template.get("candidate_identifiers", []),
                exclusions_respected=[
                    exclusion
                    for exclusion in profile.exclusions
                    if _clean_label(exclusion) in template.get("respects", [])
                ],
                watchlist_signal=template.get("watchlist_signal")
                if watchlist_counts.get(template.get("watchlist_key", ""), 0)
                else None,
            )
        )
    ideas = ideas[:5]
    deduped_gaps: list[PortfolioGap] = []
    seen_gap_keys: set[str] = set()
    for gap in gaps:
        if gap.gap_key in seen_gap_keys:
            continue
        seen_gap_keys.add(gap.gap_key)
        deduped_gaps.append(gap)
    return deduped_gaps[:5], ideas[:5]


def diagnose_portfolio(
    session: Session,
    request: PortfolioConsultRequest | None = None,
    reference_root: Path | None = None,
) -> PortfolioDiagnosis:
    request = request or PortfolioConsultRequest()
    profile, risk_source = _effective_profile(session, request, reference_root=reference_root)
    portfolio = port_repo.get_or_create_default(session)
    positions = compute_positions(session, base_currency=profile.base_currency)
    exposure_summaries, exposure_map, invested = _make_exposure_summaries(
        positions,
        profile.base_currency,
        reference_root=reference_root,
    )
    cash_balances = cash_repo.get_balances_all_currencies(session, portfolio.id)
    cash_value = sum(cash_balances.values(), Decimal("0"))
    watchlist_signals, watchlist_counts = _watchlist_signals(session, reference_root=reference_root)
    warnings = _concentration_warnings(positions, exposure_map, watchlist_counts)
    gaps, ideas = _gap_and_idea_scores(
        profile,
        exposure_map,
        warnings,
        watchlist_counts,
        reference_root=reference_root,
    )
    if not ideas:
        ideas = [
            ResearchIdea(
                area_id="broad-global-equity",
                area="Broad global equity core",
                summary="Research a broad core equity fund before adding narrower satellites.",
                why_now=(
                    "The current portfolio needs a clearer baseline before more "
                    "specific themes are layered on."
                ),
                fit_for_risk=(
                    "Works across most risk scores and suits the current "
                    f"{RISK_LABELS.get(profile.risk_score or 4)} profile."
                ),
                main_risks=["Can feel less exciting than narrow thematic ideas."],
                suitable_product_types=["ETF", "index fund"],
            )
        ]
    follow_up_questions: list[str] = []
    if get_profile(session).risk_score is None and request.risk_score is None:
        follow_up_questions.append(
            "On a 1–7 scale, where would you place your volatility tolerance?"
        )
    if not profile.exclusions:
        follow_up_questions.append(
            "Are there any sectors, countries, or products you want excluded?"
        )
    if not profile.product_preferences:
        follow_up_questions.append(
            "Do you prefer ETFs, funds, investment trusts, or are you open to a mix?"
        )
    if profile.distribution_preference is None:
        follow_up_questions.append(
            "Do you prefer accumulating or distributing share classes where both exist?"
        )

    return PortfolioDiagnosis(
        risk_score=profile.risk_score or 4,
        risk_score_source=risk_source
        if risk_source in {"explicit", "profile", "inferred"}
        else "default",
        constraints_used=_constraints(profile),
        profile_used=profile,
        base_currency=profile.base_currency,
        invested_value=invested,
        cash_value=cash_value,
        watchlist_signal_count=sum(watchlist_counts.values()),
        watchlist_signals=watchlist_signals,
        exposure_summaries=exposure_summaries,
        concentration_warnings=warnings,
        gaps=gaps,
        research_ideas=ideas[:5],
        follow_up_questions=follow_up_questions,
        regulated_advice_boundary=(
            "This is portfolio-aware research guidance for a simulated portfolio, "
            "not a personal recommendation."
        ),
    )


def consult_ideas(
    session: Session,
    request: PortfolioConsultRequest | None = None,
    reference_root: Path | None = None,
) -> list[ResearchIdea]:
    return diagnose_portfolio(
        session, request=request, reference_root=reference_root
    ).research_ideas


def consult_area(
    session: Session,
    area_name: str,
    request: PortfolioConsultRequest | None = None,
    research_root: Path = Path("research"),
    reference_root: Path | None = None,
) -> ConsultantRecommendation:
    diagnosis = diagnose_portfolio(session, request=request, reference_root=reference_root)
    selected = next(
        (
            idea
            for idea in diagnosis.research_ideas
            if area_name.lower() in {idea.area.lower(), idea.area_id.lower()}
        ),
        None,
    )
    if selected is None:
        raise ValueError(f"No consultant research area matched '{area_name}'.")
    verified: list[FactsheetSummary] = []
    for identifier in selected.candidate_identifiers:
        try:
            verified.append(
                locate_factsheet(
                    identifier,
                    research_root=research_root,
                    reference_root=reference_root,
                    fetch_source=False,
                )
            )
        except ValueError:
            continue
    product_guidance = (
        "Start with verified factsheets before making any product-level comparison."
        if not verified
        else (
            "Use the verified factsheets below as a starting point, then compare "
            "overlap, fees, and concentration."
        )
    )
    warning_excerpt = (
        ", ".join(warning.summary for warning in diagnosis.concentration_warnings[:2])
        or "none flagged"
    )
    return ConsultantRecommendation(
        selected_area=selected.area,
        summary=selected.summary,
        trade_offs=selected.main_risks,
        what_to_research=[
            selected.why_now,
            (
                "Check whether this area reduces the current concentration warnings: "
                f"{warning_excerpt}."
            ),
        ],
        product_guidance=product_guidance,
        candidate_identifiers=selected.candidate_identifiers,
        verified_factsheets=verified,
        follow_up_questions=diagnosis.follow_up_questions,
    )
