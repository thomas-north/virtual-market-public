from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.data_quality import build_data_quality_report
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist


def test_data_quality_report_flags_stale_fx(session):
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

    report = build_data_quality_report(session)
    labels = {issue.label for issue in report.issues}

    assert "Stale FX" in labels
    assert report.warning_count >= 1


def test_data_quality_report_flags_approximate_holdings_and_pence_review(session):
    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "CYBR.L", currency="GBP", asset_type="etf")
    session.commit()

    buy(
        session,
        "CYBR.L",
        Decimal("1"),
        price=Decimal("5"),
        currency="GBP",
        notes=(
            "Approximate value-snapshot import: recorded as one synthetic unit because "
            "broker units were unavailable."
        ),
    )
    session.commit()

    instrument = inst_repo.get_by_symbol(session, "CYBR.L")
    price_repo.upsert_price_bars(
        session,
        instrument.id,
        [
            PriceBarDTO(
                "CYBR.L",
                date.today(),
                None,
                None,
                None,
                Decimal("500"),
                Decimal("500"),
                None,
                "GBP",
                "test",
            )
        ],
    )
    session.commit()

    report = build_data_quality_report(session)
    by_label = {issue.label: issue for issue in report.issues}

    assert "Approximate imported holdings" in by_label
    assert by_label["Approximate imported holdings"].symbols == ["CYBR.L"]
    assert "Possible pence/GBP mismatch" in by_label
    assert by_label["Possible pence/GBP mismatch"].symbols == ["CYBR.L"]


def test_data_quality_report_flags_symbols_needing_review(session):
    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "CYBR", currency="GBP", asset_type="etf")
    session.commit()

    report = build_data_quality_report(session)
    by_label = {issue.label: issue for issue in report.issues}

    assert "Symbols needing review" in by_label
    assert by_label["Symbols needing review"].symbols == ["CYBR"]
