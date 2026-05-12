from datetime import date, timedelta
from decimal import Decimal

from typer.testing import CliRunner

from vmarket.cli import app
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.reports.overview import build_overview_payload
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist

runner = CliRunner()


def test_report_overview_help():
    result = runner.invoke(app, ["report", "overview", "--help"])

    assert result.exit_code == 0
    assert "overview" in result.stdout
    assert "Generate the primary portfolio overview page." in result.stdout
    assert "reports/overview.html" in result.stdout


def test_report_overview_writes_html(session, tmp_path):
    deposit(session, Decimal("5000"), "GBP")
    add_to_watchlist(session, "AAPL.US", currency="USD", asset_type="stock")
    session.commit()

    instrument = inst_repo.get_by_symbol(session, "AAPL.US")
    price_repo.upsert_price_bars(
        session,
        instrument.id,
        [
            PriceBarDTO(
                "AAPL.US",
                date.today(),
                None,
                None,
                None,
                Decimal("180"),
                Decimal("180"),
                None,
                "USD",
                "stooq",
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

    output = tmp_path / "overview.html"
    result = runner.invoke(app, ["report", "overview", "--html", str(output)])

    assert result.exit_code == 0
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Portfolio Overview" in content
    assert "portfolio-chart" in content
    assert "watchlist_highlights" in content


def test_build_overview_payload_separates_manual_holdings(session):
    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "BD6PG78", currency="GBP", asset_type="fund")
    session.commit()

    buy(session, "BD6PG78", Decimal("10"), price=Decimal("5"), currency="GBP")
    session.commit()

    payload = build_overview_payload(session)

    assert payload["holdings"]["manual"][0]["symbol"] == "BD6PG78"
    assert payload["holdings"]["active"] == []


def test_build_overview_payload_flags_stale_fx(session):
    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "AAPL.US", currency="GBP", asset_type="stock")
    session.commit()

    buy(session, "AAPL.US", Decimal("10"), price=Decimal("10"), currency="GBP")
    session.commit()

    instrument = inst_repo.get_by_symbol(session, "AAPL.US")
    price_repo.upsert_price_bars(
        session,
        instrument.id,
        [
            PriceBarDTO(
                "AAPL.US",
                date.today(),
                None,
                None,
                None,
                Decimal("20"),
                Decimal("20"),
                None,
                "USD",
                "stooq",
            )
        ],
    )
    fx_repo.upsert_fx_rate(
        session,
        fx_date=date.today() - timedelta(days=10),
        base="GBP",
        quote="USD",
        rate=Decimal("2"),
        source="test",
    )
    session.commit()

    payload = build_overview_payload(session)

    assert any(item["label"] == "Stale FX" for item in payload["data_quality"])
