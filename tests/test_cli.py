from datetime import date, timedelta
from decimal import Decimal

from typer.testing import CliRunner

from vmarket.cli import app
from vmarket.consult import save_profile
from vmarket.consult.models import ConsultantProfile
from vmarket.db import get_session, init_db
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist

runner = CliRunner()


def test_help_shows_new_command_groups():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "consult" in result.stdout
    assert "cockpit" in result.stdout
    assert "doctor" in result.stdout
    assert "portfolio" in result.stdout
    assert "report" in result.stdout
    assert "│ watchlist" not in result.stdout


def test_portfolio_show_marks_stale_fx(session):
    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "AAPL.US", currency="GBP")
    session.commit()

    buy(session, "AAPL.US", Decimal("10"), price=Decimal("10"), currency="GBP")
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
                close=Decimal("20"),
                adjusted_close=Decimal("20"),
                volume=None,
                currency="USD",
                source="stooq",
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

    result = runner.invoke(app, ["portfolio", "show"])

    assert result.exit_code == 0
    assert "stale" in result.stdout
    assert "FX rates" in result.stdout


def test_watch_list_marks_manual_price_symbols(session):
    add_to_watchlist(session, "BD6PG78", name="Manual Fund", currency="GBP", asset_type="fund")
    session.commit()

    result = runner.invoke(app, ["watch", "list"])

    assert result.exit_code == 0
    assert "manual" in result.stdout
    assert "BD6PG78" in result.stdout


def test_doctor_json_reports_warnings(tmp_path):
    db_path = tmp_path / "doctor.sqlite"
    init_db(db_path)
    with get_session(db_path) as session:
        deposit(session, Decimal("1000"), "GBP")
        add_to_watchlist(session, "CYBR", currency="GBP", asset_type="etf")
        save_profile(
            session,
            ConsultantProfile(risk_score=5, country_jurisdiction="GB", base_currency="GBP"),
        )
        session.commit()

    result = runner.invoke(app, ["doctor", "--db-path", str(db_path), "--json"])

    assert result.exit_code == 0
    assert '"label": "Symbols needing review"' in result.stdout
