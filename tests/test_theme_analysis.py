import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from vmarket.cli import app
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist
from vmarket.themes import ThemeAnalysisRequest, analyze_theme, list_supported_themes

runner = CliRunner()


def _seed_holding(session, symbol: str, name: str, quantity: str, price: str) -> None:
    add_to_watchlist(session, symbol, name=name, currency="GBP", asset_type="stock")
    session.commit()
    instrument = inst_repo.get_by_symbol(session, symbol)
    price_repo.upsert_price_bars(
        session,
        instrument.id,
        [
            PriceBarDTO(
                symbol=symbol,
                date=date.today(),
                open=None,
                high=None,
                low=None,
                close=Decimal(price),
                adjusted_close=Decimal(price),
                volume=None,
                currency="GBP",
                source="test",
            )
        ],
    )
    session.commit()
    buy(session, symbol, Decimal(quantity), price=Decimal(price), currency="GBP")
    session.commit()


def _seed_growth_portfolio(session, cash: str = "30000") -> None:
    deposit(session, Decimal(cash), "GBP")
    session.commit()
    _seed_holding(session, "CRWD.US", "CrowdStrike", "10", "420")
    _seed_holding(session, "NET.US", "Cloudflare", "14", "95")
    _seed_holding(session, "PANW.US", "Palo Alto Networks", "8", "260")
    _seed_holding(session, "AVGO.US", "Broadcom", "7", "880")
    _seed_holding(session, "GOOG.US", "Alphabet", "18", "140")


def test_all_eight_supported_themes_load():
    theme_ids = [theme.theme_id for theme in list_supported_themes()]

    assert theme_ids == [
        "ai-infrastructure",
        "cybersecurity",
        "defence",
        "dividend-income",
        "healthcare",
        "india",
        "robotics",
        "semiconductors",
    ]


def test_theme_registry_is_ingestion_ready():
    cybersecurity = next(
        theme for theme in list_supported_themes() if theme.theme_id == "cybersecurity"
    )
    profile = cybersecurity.candidates[0]

    assert cybersecurity.starter_stock_basket is not None
    assert profile.facts.ter_pct is not None
    assert profile.facts.aum_usd_millions is not None
    assert profile.facts.top_holdings
    assert profile.facts.methodology_summary
    assert profile.facts.listings
    assert profile.facts.listing_currencies


def test_small_high_conviction_sleeve_can_prefer_stock_basket_for_thematic_fit(session):
    _seed_growth_portfolio(session)

    result = analyze_theme(
        session,
        ThemeAnalysisRequest(
            theme="cybersecurity",
            amount=Decimal("500"),
            allocation_currency="GBP",
            investor_country="GB",
            preferred_companies=["CrowdStrike", "Cloudflare", "Palo Alto", "Zscaler", "Okta"],
            volatility_tolerance="medium",
            time_horizon="long",
            target_role="auto",
            implementation_scope="both",
        ),
    )

    assert result.portfolio_context.allocation_analysis.size_bucket == "satellite"
    assert result.best_thematic_fit.implementation_kind == "stock_basket"
    assert result.best_risk_adjusted_option.implementation_kind == "etf"


def test_larger_sleeve_pushes_best_thematic_fit_back_toward_etf(session):
    _seed_growth_portfolio(session)

    result = analyze_theme(
        session,
        ThemeAnalysisRequest(
            theme="cybersecurity",
            amount=Decimal("2500"),
            allocation_currency="GBP",
            investor_country="GB",
            preferred_companies=["CrowdStrike", "Cloudflare", "Palo Alto", "Zscaler", "Okta"],
            volatility_tolerance="medium",
            time_horizon="long",
            target_role="auto",
            implementation_scope="both",
        ),
    )

    assert result.portfolio_context.allocation_analysis.size_bucket == "meaningful_sleeve"
    assert result.best_thematic_fit.implementation_kind == "etf"
    assert result.best_thematic_fit.profile_id == "CYSE"


def test_visible_size_ratio_changes_bucket_and_recommendation(session):
    _seed_growth_portfolio(session, cash="90000")

    tiny = analyze_theme(
        session,
        ThemeAnalysisRequest(
            theme="cybersecurity",
            amount=Decimal("500"),
            allocation_currency="GBP",
            preferred_companies=["CrowdStrike", "Cloudflare", "Palo Alto"],
            implementation_scope="both",
        ),
    )
    large = analyze_theme(
        session,
        ThemeAnalysisRequest(
            theme="cybersecurity",
            amount=Decimal("2500"),
            allocation_currency="GBP",
            preferred_companies=["CrowdStrike", "Cloudflare", "Palo Alto"],
            implementation_scope="both",
        ),
    )

    assert tiny.portfolio_context.allocation_analysis.size_bucket == "small_satellite"
    assert large.portfolio_context.allocation_analysis.size_bucket == "satellite"
    assert tiny.best_thematic_fit.implementation_kind == "stock_basket"
    assert large.best_thematic_fit.implementation_kind in {"stock_basket", "etf"}


def test_low_volatility_preference_favours_broader_implementation(session):
    _seed_growth_portfolio(session)

    result = analyze_theme(
        session,
        ThemeAnalysisRequest(
            theme="cybersecurity",
            amount=Decimal("1800"),
            allocation_currency="GBP",
            investor_country="GB",
            preferred_companies=["CrowdStrike", "Cloudflare", "Palo Alto"],
            volatility_tolerance="low",
            time_horizon="medium",
            target_role="auto",
            implementation_scope="both",
        ),
    )

    assert result.best_risk_adjusted_option.implementation_kind == "etf"
    assert (
        result.best_risk_adjusted_option.volatility_risk <= result.best_thematic_fit.volatility_risk
    )


def test_uk_context_prefers_gbp_listings_when_available(session):
    result = analyze_theme(
        session,
        ThemeAnalysisRequest(
            theme="semiconductors",
            amount=Decimal("1500"),
            allocation_currency="GBP",
            investor_country="GB",
            preferred_companies=["ASML", "TSMC"],
            implementation_scope="etf",
        ),
    )

    listed = {candidate.profile_id: candidate.listing_currency for candidate in result.candidates}
    assert listed["CHIP"] == "GBP"
    assert listed["SEMI"] == "GBP"
    assert listed["SILI"] == "USD"


def test_json_output_contains_typed_candidates_and_decision_rules(session):
    _seed_growth_portfolio(session)

    result = runner.invoke(
        app,
        [
            "theme",
            "analyse",
            "cybersecurity",
            "--amount",
            "500",
            "--preferred-company",
            "CrowdStrike",
            "--preferred-company",
            "Cloudflare",
            "--preferred-company",
            "Palo Alto",
            "--preferred-company",
            "Zscaler",
            "--preferred-company",
            "Okta",
            "--implementation-scope",
            "both",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["best_thematic_fit"]["implementation_kind"] in {"etf", "stock_basket"}
    assert payload["best_thematic_fit_decision"]["decision_rules"]
    assert "alternatives_weaker" in payload["best_risk_adjusted_decision"]
    assert payload["portfolio_context"]["allocation_analysis"]["size_bucket"]


def test_compare_ideas_cli_surfaces_basket_and_etf(session):
    _seed_growth_portfolio(session)

    result = runner.invoke(
        app,
        [
            "theme",
            "compare-ideas",
            "cybersecurity",
            "--amount",
            "500",
            "--preferred-company",
            "CrowdStrike",
            "--preferred-company",
            "Cloudflare",
        ],
    )

    assert result.exit_code == 0
    assert "stock_basket" in result.stdout
    assert "etf" in result.stdout


def test_theme_list_cli_shows_all_supported_themes():
    result = runner.invoke(app, ["theme", "list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    theme_ids = [theme["theme_id"] for theme in payload]
    assert "ai-infrastructure" in theme_ids
    assert "dividend-income" in theme_ids
    assert "india" in theme_ids


def test_compare_etfs_cli_renders_profiles():
    result = runner.invoke(app, ["theme", "compare-etfs", "CYSE", "FCBR", "LOCK"])

    assert result.exit_code == 0
    assert "CYSE" in result.stdout
    assert "FCBR" in result.stdout
    assert "LOCK" in result.stdout


def test_unknown_theme_errors_clearly():
    result = runner.invoke(app, ["theme", "analyse", "unknown-theme", "--amount", "1000"])

    assert result.exit_code == 1
    assert "Unsupported theme" in result.stderr


def test_skill_is_generic_and_theme_registry_aware():
    skill_path = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "thematic-investment-discussion"
        / "SKILL.md"
    )
    content = skill_path.read_text()

    assert "vmarket theme list" in content
    assert "compare-ideas" in content
    assert "semiconductors" in content
    assert "ai-infrastructure" in content
