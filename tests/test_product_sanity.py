from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import vmarket.db as db_module
from vmarket.db import get_session, init_db
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist
from vmarket.web.app import create_app


@pytest.fixture
def cockpit_db_path(tmp_path):
    original = db_module._engine
    if original is not None:
        original.dispose()
    db_module._engine = None

    db_path = tmp_path / "product-sanity.sqlite"
    init_db(db_path)
    yield db_path

    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = original


def _seed_dashboard_portfolio(session) -> None:
    deposit(session, Decimal("9000"), "GBP")
    deposit(session, Decimal("2500"), "USD")
    add_to_watchlist(session, "AAPL.US", name="Apple Inc", currency="USD", asset_type="stock")
    session.commit()

    instrument = inst_repo.get_by_symbol(session, "AAPL.US")
    price_repo.upsert_price_bars(
        session,
        instrument.id,
        [
            PriceBarDTO(
                symbol="AAPL.US",
                date=date.today(),
                open=None,
                high=None,
                low=None,
                close=Decimal("180"),
                adjusted_close=Decimal("180"),
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
    buy(session, "AAPL.US", Decimal("5"), price=Decimal("180"), currency="USD")
    session.commit()


def test_main_user_journey_smoke(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    dashboard = client.get("/")
    workflows = client.get("/workflows")
    theme = client.post(
        "/themes/analyse",
        data={
            "theme": "cybersecurity",
            "amount": "500",
            "investor_country": "GB",
            "preferred_companies": "CrowdStrike, Cloudflare",
            "volatility_tolerance": "medium",
            "time_horizon": "long",
            "target_role": "auto",
            "implementation_scope": "both",
        },
    )
    consult = client.post("/consult", data={"risk_score": "5"})
    agent = client.get("/agent?workflow=portfolio-consultation")
    actions = client.get("/actions")

    assert dashboard.status_code == 200
    assert workflows.status_code == 200
    assert theme.status_code == 200
    assert consult.status_code == 200
    assert agent.status_code == 200
    assert actions.status_code == 200
    assert "Virtual Market — simulated portfolio workspace" in dashboard.text
    assert "Task workspace" in workflows.text
    assert "Best thematic fit" in theme.text
    assert "Research areas" in consult.text
    assert "Prompt preview" in agent.text
    assert "Pending and historical actions" in actions.text
