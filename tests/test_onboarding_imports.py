from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import vmarket.config as config
import vmarket.db as db_module
from vmarket.cli import app
from vmarket.db import get_session, init_db
from vmarket.onboarding import (
    confirm_import_draft,
    create_import_draft,
    discard_import_draft,
    get_onboarding_state,
    parse_csv_rows,
    parse_pasted_rows,
)
from vmarket.repositories import trades as trade_repo
from vmarket.repositories import watchlist as watch_repo
from vmarket.repositories.portfolios import get_or_create_default
from vmarket.web.app import create_app

runner = CliRunner()


def test_default_db_path_uses_private_user_data(monkeypatch):
    monkeypatch.delenv("VMARKET_DB_PATH", raising=False)

    assert config.get_db_path() == Path("user_data/vmarket.sqlite")


def test_env_db_path_still_overrides_private_default(monkeypatch, tmp_path):
    custom = tmp_path / "custom.sqlite"
    monkeypatch.setenv("VMARKET_DB_PATH", str(custom))

    assert config.get_db_path() == custom


def test_portfolio_csv_parser_warns_for_duplicates_and_symbol_shape():
    rows = parse_csv_rows(
        "symbol,name,quantity,average_cost,currency\n"
        "AAPL.US,Apple,5,180,USD\n"
        "AAPL.US,Apple duplicate,1,181,USD\n"
        "MSFT,Microsoft,2,400,USD\n",
        "portfolio",
    )

    assert rows[0].symbol == "AAPL.US"
    assert any("Duplicate symbol" in warning for warning in rows[1].warnings)
    assert any("market suffix" in warning for warning in rows[2].warnings)


def test_pasted_watchlist_parser_accepts_simple_lines():
    rows = parse_pasted_rows("AAPL.US USD stock Apple Inc\nVWRP.L GBP etf Vanguard", "watchlist")

    assert rows[0].symbol == "AAPL.US"
    assert rows[0].currency == "USD"
    assert rows[1].asset_type == "etf"


def test_confirm_portfolio_import_creates_cash_and_trade(session):
    rows = parse_csv_rows(
        "symbol,name,quantity,average_cost,currency,asset_type\n"
        "AAPL.US,Apple,5,180,USD,stock\n",
        "portfolio",
    )
    draft = create_import_draft(
        session,
        kind="portfolio",
        source_kind="csv",
        rows=rows,
    )
    session.commit()

    confirmed = confirm_import_draft(session, draft.id)
    session.commit()

    portfolio = get_or_create_default(session)
    trades = trade_repo.list_trades(session, portfolio.id)
    state = get_onboarding_state(session)
    assert confirmed.status == "confirmed"
    assert len(trades) == 1
    assert trades[0].instrument.symbol == "AAPL.US"
    assert state.portfolio_ready is True


def test_value_snapshot_portfolio_import_allows_missing_units(session):
    rows = parse_csv_rows(
        "symbol,name,current_value,gain_amount,currency,asset_type\n"
        "META.US,Meta Platforms,448.72,-46.53,GBP,stock\n",
        "portfolio",
    )
    assert rows[0].quantity is None
    assert rows[0].warnings == []

    draft = create_import_draft(
        session,
        kind="portfolio",
        source_kind="csv",
        rows=rows,
    )
    session.commit()

    confirm_import_draft(session, draft.id)
    session.commit()

    portfolio = get_or_create_default(session)
    trades = trade_repo.list_trades(session, portfolio.id)
    assert len(trades) == 1
    assert trades[0].quantity == 1
    assert trades[0].price == Decimal("495.250000")
    assert "synthetic unit" in (trades[0].notes or "")


def test_discard_import_draft_has_no_side_effects(session):
    rows = parse_csv_rows(
        "symbol,name,currency,asset_type\nAAPL.US,Apple,USD,stock\n",
        "watchlist",
    )
    draft = create_import_draft(session, kind="watchlist", source_kind="csv", rows=rows)
    session.commit()

    discard_import_draft(session, draft.id)
    session.commit()

    assert watch_repo.list_all(session) == []


def test_onboarding_cli_initializes_private_workspace(tmp_path, monkeypatch):
    db_path = tmp_path / "vmarket.sqlite"
    user_data = tmp_path / "user_data"
    monkeypatch.setenv("VMARKET_USER_DATA_DIR", str(user_data))
    original = db_module._engine
    if original is not None:
        original.dispose()
    db_module._engine = None
    try:
        result = runner.invoke(app, ["onboard", "--db-path", str(db_path)])
    finally:
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = original

    assert result.exit_code == 0
    assert db_path.exists()
    assert (user_data / "screenshots").exists()
    assert "Private workspace ready" in result.stdout


def test_cockpit_onboarding_routes_create_and_confirm_import(tmp_path):
    original = db_module._engine
    if original is not None:
        original.dispose()
    db_module._engine = None
    db_path = tmp_path / "cockpit.sqlite"
    try:
        init_db(db_path)
        client = TestClient(create_app(db_path=db_path))

        page = client.get("/onboarding")
        assert page.status_code == 200
        assert "Setup checklist" in page.text

        created = client.post(
            "/imports/portfolio/manual",
            data={
                "symbol": "AAPL.US",
                "name": "Apple",
                "quantity": "5",
                "average_cost": "180",
                "currency": "USD",
                "asset_type": "stock",
            },
            follow_redirects=False,
        )
        assert created.status_code == 303
        draft_path = created.headers["location"]
        assert draft_path.startswith("/imports/")

        draft_page = client.get(draft_path)
        assert "AAPL.US" in draft_page.text
        confirm = client.post(f"{draft_path}/confirm", follow_redirects=False)
        assert confirm.status_code == 303

        with get_session(db_path) as session:
            portfolio = get_or_create_default(session)
            assert len(trade_repo.list_trades(session, portfolio.id)) == 1
    finally:
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = original


def test_screenshot_upload_creates_pending_draft_without_mutation(tmp_path, monkeypatch):
    original = db_module._engine
    if original is not None:
        original.dispose()
    db_module._engine = None
    db_path = tmp_path / "cockpit.sqlite"
    user_data = tmp_path / "user_data"
    monkeypatch.setenv("VMARKET_USER_DATA_DIR", str(user_data))
    try:
        init_db(db_path)
        client = TestClient(create_app(db_path=db_path))

        response = client.post(
            "/imports/screenshot",
            files={"file": ("portfolio.png", b"fake-image", "image/png")},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert (user_data / "screenshots").exists()
        with get_session(db_path) as session:
            state = get_onboarding_state(session, db_path=db_path)
            portfolio = get_or_create_default(session)
            assert state.pending_imports == 1
            assert trade_repo.list_trades(session, portfolio.id) == []

        packet = client.get("/agent/prompt/onboarding-import.md")
        assert packet.status_code == 200
        assert "Onboarding Import Packet" in packet.text
        assert "Do not confirm imports yourself" in packet.text
    finally:
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = original
