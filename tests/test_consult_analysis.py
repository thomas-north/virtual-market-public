from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from typer.testing import CliRunner

import vmarket.db as db_module
from vmarket.cli import app
from vmarket.consult import diagnose_portfolio
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist

runner = CliRunner()


@pytest.fixture
def consult_db_path(tmp_path):
    original = db_module._engine
    if original is not None:
        original.dispose()
    db_module._engine = None

    db_path = tmp_path / "consult.sqlite"
    yield db_path

    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = original


def _seed_consult_portfolio(session) -> None:
    deposit(session, Decimal("25000"), "GBP")
    deposit(session, Decimal("12000"), "USD")
    session.commit()

    add_to_watchlist(
        session,
        "VUKE",
        name="Vanguard FTSE 100 UCITS ETF",
        currency="GBP",
        asset_type="etf",
    )
    add_to_watchlist(
        session,
        "CRWD.US",
        name="CrowdStrike Holdings",
        currency="USD",
        asset_type="stock",
    )
    session.commit()

    prices = {
        "AAPL.US": Decimal("180"),
        "GOOG.US": Decimal("160"),
        "META.US": Decimal("500"),
    }
    for symbol, close in prices.items():
        instrument = inst_repo.get_or_create(
            session,
            symbol,
            provider_symbol=symbol,
            currency="USD",
            asset_type="stock",
        )
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
                    close=close,
                    adjusted_close=close,
                    volume=None,
                    currency="USD",
                    source="test",
                )
            ],
        )
    fx_repo.upsert_fx_rate(
        session,
        fx_date=date.today(),
        base="GBP",
        quote="USD",
        rate=Decimal("1.25"),
        source="test",
    )
    session.commit()

    buy(session, "AAPL.US", Decimal("18"), price=Decimal("180"), currency="USD")
    buy(session, "GOOG.US", Decimal("14"), price=Decimal("160"), currency="USD")
    buy(session, "META.US", Decimal("8"), price=Decimal("500"), currency="USD")
    session.commit()


def test_diagnose_portfolio_highlights_concentration_and_research_gaps(session):
    _seed_consult_portfolio(session)

    diagnosis = diagnose_portfolio(session)

    warning_keys = {warning.warning_key for warning in diagnosis.concentration_warnings}
    idea_names = {idea.area for idea in diagnosis.research_ideas}

    assert diagnosis.risk_score_source == "inferred"
    assert diagnosis.watchlist_signal_count >= 2
    assert "technology-tilt" in warning_keys
    assert "us-tilt" in warning_keys
    assert "Healthcare diversification" in idea_names
    assert "UK mid caps" in idea_names
    assert diagnosis.follow_up_questions


def test_consult_profile_cli_round_trip_and_portfolio_json(consult_db_path):
    env = {"VMARKET_DB_PATH": str(consult_db_path)}

    from vmarket.db import get_session, init_db

    init_db(consult_db_path)
    with get_session(consult_db_path) as session:
        _seed_consult_portfolio(session)

    set_result = runner.invoke(
        app,
        [
            "consult",
            "profile",
            "set",
            "--risk-score",
            "5",
            "--exclude",
            "defence",
            "--product-preference",
            "ETF",
            "--distribution-preference",
            "accumulating",
        ],
        env=env,
    )
    assert set_result.exit_code == 0

    show_result = runner.invoke(app, ["consult", "profile", "show", "--json"], env=env)
    assert show_result.exit_code == 0
    profile_payload = json.loads(show_result.stdout)
    assert profile_payload["risk_score"] == 5
    assert profile_payload["exclusions"] == ["defence"]

    consult_result = runner.invoke(app, ["consult", "portfolio", "--json"], env=env)
    assert consult_result.exit_code == 0
    payload = json.loads(consult_result.stdout)
    assert payload["risk_score"] == 5
    assert payload["risk_score_source"] == "profile"
    assert payload["profile_used"]["product_preferences"] == ["ETF"]
    assert 1 <= len(payload["research_ideas"]) <= 5


def test_consult_area_and_factsheet_cli_remain_cautious(consult_db_path):
    env = {"VMARKET_DB_PATH": str(consult_db_path)}

    from vmarket.db import get_session, init_db

    init_db(consult_db_path)
    with get_session(consult_db_path) as session:
        _seed_consult_portfolio(session)

    area_result = runner.invoke(
        app,
        ["consult", "area", "UK mid caps", "--risk-score", "5", "--json"],
        env=env,
    )
    assert area_result.exit_code == 0
    area_payload = json.loads(area_result.stdout)
    assert area_payload["selected_area"] == "UK mid caps"
    assert area_payload["verified_factsheets"] == []
    assert "verified factsheets" in area_payload["product_guidance"].lower()

    factsheet_result = runner.invoke(
        app,
        ["consult", "factsheet", "VUKE", "--no-fetch", "--json"],
        env=env,
    )
    assert factsheet_result.exit_code == 0
    factsheet_payload = json.loads(factsheet_result.stdout)
    assert factsheet_payload["identifier"] == "VUKE"
    assert "Vanguard FTSE 100 UCITS ETF" in factsheet_payload["fund_name"]
