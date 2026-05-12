from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import vmarket.db as db_module
from vmarket.cli import app
from vmarket.db import get_session, init_db
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo
from vmarket.repositories import watchlist as wl_repo
from vmarket.research.schema import EvidenceRole, NormalizedEvidenceItem, SourceClass
from vmarket.research.store import evidence_path, write_evidence_items
from vmarket.research.wiki import init_research_workspace
from vmarket.services.cash_service import deposit
from vmarket.services.staged_action_service import list_actions
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist
from vmarket.services.workspace_service import list_workflow_sessions
from vmarket.web.app import create_app

runner = CliRunner()


@pytest.fixture
def cockpit_db_path(tmp_path):
    original = db_module._engine
    original_path = db_module._engine_path
    if original is not None:
        original.dispose()
    db_module._engine = None
    db_module._engine_path = None

    db_path = tmp_path / "cockpit.sqlite"
    init_db(db_path)
    yield db_path

    if db_module._engine is not None:
        db_module._engine.dispose()
    db_module._engine = original
    db_module._engine_path = original_path


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


def test_cockpit_dashboard_loads(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Agent Cockpit" in response.text
    assert "Virtual Market" in response.text
    assert "Total value" in response.text
    assert "Portfolio" in response.text


def test_cockpit_portfolio_page_embeds_standalone_report(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    page = client.get("/portfolio")
    standalone = client.get("/overview/standalone")

    assert page.status_code == 200
    assert "Holdings" in page.text
    assert 'src="/overview/standalone?days=30"' in page.text

    assert standalone.status_code == 200
    assert "Portfolio Overview" in standalone.text
    assert "portfolio-chart" in standalone.text
    assert "Apple Inc" in standalone.text

    # /overview should redirect to /portfolio
    redirect = client.get("/overview", follow_redirects=False)
    assert redirect.status_code == 301


def test_sync_prices_route_redirects_to_portfolio(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))
    response = client.post("/sync/prices", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/portfolio"


def test_cockpit_theme_workspace_renders_supported_themes(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.get("/themes")

    assert response.status_code == 200
    assert "Theme Workspace" in response.text
    assert "Cybersecurity" in response.text
    assert "AI Infrastructure" in response.text


def test_cockpit_consult_page_renders_profile_and_ideas(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.get("/consult")

    assert response.status_code == 200
    assert "Portfolio Consultant" in response.text
    assert "Saved profile" in response.text
    assert "Run consultation" in response.text


def test_workflows_page_lists_supported_task_flows(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.get("/workflows")

    assert response.status_code == 200
    assert "Task workspace" in response.text
    assert "Thematic Analysis" in response.text
    assert "Portfolio Consultation" in response.text


def test_cockpit_theme_analysis_uses_existing_engine(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.post(
        "/themes/analyse",
        data={
            "theme": "cybersecurity",
            "amount": "500",
            "investor_country": "GB",
            "preferred_companies": "CrowdStrike, Cloudflare, Palo Alto",
            "volatility_tolerance": "medium",
            "time_horizon": "long",
            "target_role": "auto",
            "implementation_scope": "both",
        },
    )

    assert response.status_code == 200
    assert "Best thematic fit" in response.text
    assert "Best risk-adjusted implementation" in response.text
    with get_session(cockpit_db_path) as session:
        sessions = list_workflow_sessions(session, workflow="thematic-analysis")
        assert sessions
        reopened = client.get(f"/themes?session_id={sessions[0].id}")
    assert reopened.status_code == 200
    assert f"Session #{sessions[0].id}" in reopened.text


def test_agent_context_and_prompt_endpoints_return_machine_readable_payloads(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    context = client.get("/agent/context.json?workflow=morning-brief")
    prompt = client.get("/agent/prompt/morning-brief.md")

    assert context.status_code == 200
    payload = context.json()
    assert payload["workflow"] == "morning-brief"
    assert "overview" in payload
    assert ".venv/bin/vmarket portfolio show" in payload["recommended_commands"]

    assert prompt.status_code == 200
    assert "Virtual Market Morning Brief Packet" in prompt.text
    assert "Recommended Commands" in prompt.text


def test_data_quality_endpoint_returns_report(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.get("/api/data-quality.json")

    assert response.status_code == 200
    payload = response.json()
    assert "issues" in payload
    assert "warning_count" in payload


def test_consult_agent_context_endpoint_returns_diagnosis(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    context = client.get("/agent/context.json?workflow=portfolio-consultation")

    assert context.status_code == 200
    payload = context.json()
    assert payload["workflow"] == "portfolio-consultation"
    assert payload["consult_diagnosis"] is not None
    assert ".venv/bin/vmarket consult portfolio" in payload["recommended_commands"][-1]


def test_journal_page_renders_saved_entry(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    save = client.post(
        "/journal/save",
        data={
            "workflow": "action-review",
            "title": "Review staged buy",
            "summary": "Pending buy should wait for more evidence.",
            "redirect_to": "/journal",
        },
        follow_redirects=False,
    )

    assert save.status_code == 303
    response = client.get("/journal")
    assert response.status_code == 200
    assert "decision journal" in response.text.lower()
    assert "Review staged buy" in response.text


def test_cockpit_export_context_cli_emits_json(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)

    result = runner.invoke(
        app,
        [
            "cockpit",
            "export-context",
            "--format",
            "json",
            "--workflow",
            "morning-brief",
            "--db-path",
            str(cockpit_db_path),
        ],
    )

    assert result.exit_code == 0
    assert '"workflow": "morning-brief"' in result.stdout
    assert '"recommended_commands"' in result.stdout


def test_cockpit_export_context_cli_supports_portfolio_consultation(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)

    result = runner.invoke(
        app,
        [
            "cockpit",
            "export-context",
            "--format",
            "json",
            "--workflow",
            "portfolio-consultation",
            "--factsheet",
            "VUKE",
            "--db-path",
            str(cockpit_db_path),
        ],
    )

    assert result.exit_code == 0
    assert '"workflow": "portfolio-consultation"' in result.stdout
    assert '"consult_diagnosis"' in result.stdout
    assert '"identifier": "VUKE"' in result.stdout


def test_cockpit_workflows_and_journal_cli_commands(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))
    client.post(
        "/journal/save",
        data={
            "workflow": "action-review",
            "title": "Review staged buy",
            "summary": "Pending buy should wait for more evidence.",
            "redirect_to": "/journal",
        },
        follow_redirects=False,
    )
    client.post(
        "/themes/analyse",
        data={
            "theme": "cybersecurity",
            "amount": "500",
            "investor_country": "GB",
            "preferred_companies": "CrowdStrike, Cloudflare, Palo Alto",
            "volatility_tolerance": "medium",
            "time_horizon": "long",
            "target_role": "auto",
            "implementation_scope": "both",
        },
    )

    workflows = runner.invoke(
        app,
        ["cockpit", "workflows", "--db-path", str(cockpit_db_path)],
    )
    journal = runner.invoke(
        app,
        ["cockpit", "journal", "--db-path", str(cockpit_db_path)],
    )

    assert workflows.exit_code == 0
    assert "cybersecurity analysis" in workflows.stdout.lower()
    assert journal.exit_code == 0
    assert "Review staged buy" in journal.stdout


def test_research_page_renders_local_brief(tmp_path, monkeypatch, cockpit_db_path):
    monkeypatch.chdir(tmp_path)
    research_root = tmp_path / "research"
    init_research_workspace(research_root)
    write_evidence_items(
        evidence_path("META.US", root=research_root),
        [
            NormalizedEvidenceItem(
                source_class=SourceClass.SOCIAL,
                evidence_role=EvidenceRole.SENTIMENT,
                source_name="Reddit",
                source_type="reddit_post",
                collected_at=datetime(2026, 5, 9, 10, 0, 0),
                title="Why investors are debating META",
                symbols=["META.US"],
                dedupe_key="meta1",
            )
        ],
    )
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    response = client.post("/research", data={"symbol": "META.US"})

    assert response.status_code == 200
    assert "Research workspace" in response.text
    assert "META.US evidence brief" in response.text


def test_staged_watch_add_confirms_into_watchlist(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    stage = client.post(
        "/actions/stage",
        data={
            "kind": "watch_add",
            "source": "theme_analysis",
            "symbol": "CHIP",
            "name": "VanEck Semiconductor ETF",
            "currency": "GBP",
            "asset_type": "etf",
            "explanation": "Stage semiconductor ETF follow-up.",
        },
        follow_redirects=False,
    )

    assert stage.status_code == 303
    with get_session(cockpit_db_path) as session:
        actions = list_actions(session, status="pending")
        assert len(actions) == 1
        action_id = actions[0].id

    confirm = client.post(f"/actions/{action_id}/confirm", follow_redirects=False)

    assert confirm.status_code == 303
    with get_session(cockpit_db_path) as session:
        actions = list_actions(session, status="confirmed")
        assert actions[0].kind == "watch_add"
        instrument = inst_repo.get_by_symbol(session, "CHIP")
        assert instrument is not None
        assert wl_repo.get_by_instrument_id(session, instrument.id) is not None


def test_staged_buy_confirms_once_and_creates_one_new_trade(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
        instrument = inst_repo.get_by_symbol(session, "AAPL.US")
        portfolio = port_repo.get_or_create_default(session)
        assert instrument is not None
        starting_count = len(
            trade_repo.list_trades_for_instrument(session, portfolio.id, instrument.id)
        )
    client = TestClient(create_app(db_path=cockpit_db_path))

    client.post(
        "/actions/stage",
        data={
            "kind": "buy",
            "source": "user",
            "symbol": "AAPL.US",
            "quantity": "1",
            "price": "180",
            "currency": "USD",
            "notes": "Cockpit staged buy",
            "explanation": "Test staged buy",
        },
        follow_redirects=False,
    )

    with get_session(cockpit_db_path) as session:
        pending = list_actions(session, status="pending")
        action_id = pending[0].id

    client.post(f"/actions/{action_id}/confirm", follow_redirects=False)

    with get_session(cockpit_db_path) as session:
        instrument = inst_repo.get_by_symbol(session, "AAPL.US")
        portfolio = port_repo.get_or_create_default(session)
        assert instrument is not None
        ending_count = len(
            trade_repo.list_trades_for_instrument(session, portfolio.id, instrument.id)
        )
        confirmed = list_actions(session, status="confirmed")
        assert confirmed[0].id == action_id
        assert ending_count == starting_count + 1


def test_allocation_drift_tab_renders(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))
    response = client.get("/portfolio")
    assert response.status_code == 200
    assert "Allocation drift" in response.text
    # AAPL.US seeded as asset_type='stock', so 'stock' bucket should appear
    assert "stock" in response.text


def test_save_targets_persists_and_shows_in_drift(cockpit_db_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    r = client.post(
        "/portfolio/targets",
        data={"target_stock": "60", "target_etf": "40"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    targets_file = tmp_path / "user_data" / "targets.json"
    assert targets_file.exists()
    import json
    targets = json.loads(targets_file.read_text())
    assert targets.get("stock") == 60.0


def test_benchmark_overlay_set_and_clear(cockpit_db_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    # Set benchmark
    r = client.post("/portfolio/benchmark", data={"symbol": "VWRP.L"}, follow_redirects=False)
    assert r.status_code == 303
    assert (tmp_path / "user_data" / "benchmark.txt").read_text().strip() == "VWRP.L"

    # Portfolio page shows the pill
    page = client.get("/portfolio")
    assert "VWRP.L" in page.text

    # Clear benchmark
    r = client.post("/portfolio/benchmark/clear", follow_redirects=False)
    assert r.status_code == 303
    assert not (tmp_path / "user_data" / "benchmark.txt").exists()


def test_what_if_preview_shows_cost_and_cash(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
        # Stage a buy action with an explicit price so no DB price lookup is needed
        from vmarket.services.staged_action_service import stage_action
        stage_action(
            session,
            kind="buy",
            payload={"symbol": "AAPL.US", "quantity": "2", "price": "180", "currency": "USD"},
            source="user",
        )
        session.commit()

    client = TestClient(create_app(db_path=cockpit_db_path))
    response = client.get("/decisions")
    assert response.status_code == 200
    # Estimated cost = 2 × 180 = 360 USD
    assert "360.00" in response.text
    assert "Preview impact" in response.text


def test_memo_page_loads_without_memo_file(cockpit_db_path):
    client = TestClient(create_app(db_path=cockpit_db_path))
    response = client.get("/memo")
    assert response.status_code == 200
    assert "Daily Memo" in response.text
    assert "Generate memo" in response.text


def test_memo_generate_creates_file_and_redirects(cockpit_db_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))
    response = client.post("/memo/generate", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/memo"
    memos = list((tmp_path / "reports").glob("daily_*.md"))
    assert memos, "Expected a daily memo file to be written"


def test_cockpit_watchlist_page_shows_tracked_symbol(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        add_to_watchlist(session, "CIBR.L", name="Some ETF", currency="GBP")
        session.commit()
    client = TestClient(create_app(db_path=cockpit_db_path))
    response = client.get("/watchlist")
    assert response.status_code == 200
    assert "CIBR.L" in response.text
    assert "Watchlist" in response.text


def test_discarded_action_does_not_mutate_watchlist(cockpit_db_path):
    with get_session(cockpit_db_path) as session:
        _seed_dashboard_portfolio(session)
    client = TestClient(create_app(db_path=cockpit_db_path))

    client.post(
        "/actions/stage",
        data={
            "kind": "watch_remove",
            "source": "user",
            "symbol": "AAPL.US",
            "explanation": "Maybe remove Apple later.",
        },
        follow_redirects=False,
    )

    with get_session(cockpit_db_path) as session:
        pending = list_actions(session, status="pending")
        action_id = pending[0].id

    client.post(f"/actions/{action_id}/discard", follow_redirects=False)

    with get_session(cockpit_db_path) as session:
        discarded = list_actions(session, status="discarded")
        assert discarded[0].id == action_id
        instrument = inst_repo.get_by_symbol(session, "AAPL.US")
        assert instrument is not None
        assert wl_repo.get_by_instrument_id(session, instrument.id) is not None
