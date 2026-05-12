from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.repositories import cash as cash_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo
from vmarket.repositories import watchlist as wl_repo
from vmarket.services.data_quality import build_data_quality_report
from vmarket.services.freshness import is_manual_price_symbol
from vmarket.services.valuation_service import compute_positions


def _fmt(val: Decimal | None, suffix: str = "") -> str:
    if val is None:
        return "N/A"
    return f"{val:,.2f}{suffix}"


def generate_daily_memo(session: Session, memo_date: date | None = None) -> str:
    memo_date = memo_date or date.today()
    portfolio = port_repo.get_or_create_default(session)
    base = portfolio.base_currency
    positions = compute_positions(session, base_currency=base)
    balances = cash_repo.get_balances_all_currencies(session, portfolio.id)

    total_cash = sum(balances.values(), Decimal("0"))
    total_invested = sum(
        (p.value_in_base for p in positions if p.value_in_base is not None), Decimal("0")
    )
    total_value = total_cash + total_invested

    unrealised_total = sum(
        (p.unrealised_pnl for p in positions if p.unrealised_pnl is not None), Decimal("0")
    )

    today_trades = trade_repo.list_trades_for_date(session, portfolio.id, memo_date)
    wl_items = wl_repo.list_all(session)
    lines: list[str] = []
    lines.append(f"# Daily Virtual Market Memo — {memo_date}")
    lines.append("")

    # Portfolio Summary
    lines.append("## Portfolio Summary")
    lines.append("")
    cash_str = "  \n".join(
        f"- {currency}: {_fmt(bal)}" for currency, bal in sorted(balances.items())
    ) or "- No cash"
    lines.append(f"**Fake cash balances:**  \n{cash_str}")
    lines.append(f"**Invested value:** {_fmt(total_invested)} {base}")
    lines.append(f"**Total portfolio value:** {_fmt(total_value)} {base}")
    lines.append(f"**Unrealised gain/loss:** {_fmt(unrealised_total)} {base}")
    lines.append("")

    # Holdings
    lines.append("## Portfolio Holdings")
    lines.append("")
    if positions:
        lines.append(
            "| Symbol | Name | Qty | Avg Cost | Latest Price | "
            "Market Value | P/L | P/L % | Currency | Provenance | Confidence |"
        )
        lines.append(
            "|--------|------|-----|----------|--------------|--------------|-----|-------|----------|------------|------------|"
        )
        for p in positions:
            pnl_str = _fmt(p.unrealised_pnl)
            pnl_pct = f"{p.unrealised_pnl_pct:.1f}%" if p.unrealised_pnl_pct is not None else "N/A"
            stale_flag = " ⚠" if p.stale else ""
            fx_flag = " ¹" if p.fx_missing else ""
            lines.append(
                f"| {p.symbol} | {p.name or ''} | {p.quantity:.4f} | "
                f"{_fmt(p.avg_cost)} | {_fmt(p.latest_price)}{stale_flag} | "
                f"{_fmt(p.market_value)}{fx_flag} | {pnl_str} | {pnl_pct} | "
                f"{p.cost_currency} | {p.provenance_kind} | {p.provenance_confidence:.2f} |"
            )
        if any(p.fx_missing for p in positions):
            lines.append("")
            lines.append("¹ FX rate missing — native currency valuation shown.")
    else:
        lines.append("No open positions.")
    lines.append("")

    # Top Movers
    lines.append("## Top Portfolio Movers")
    lines.append("")
    by_pnl = sorted(
        [p for p in positions if p.unrealised_pnl_pct is not None],
        key=lambda p: p.unrealised_pnl_pct,
        reverse=True,
    )
    if by_pnl:
        gainers = [p for p in by_pnl if p.unrealised_pnl_pct >= 0][:3]
        fallers = [p for p in reversed(by_pnl) if p.unrealised_pnl_pct < 0][:3]
        if gainers:
            lines.append("**Biggest gainers:**")
            for p in gainers:
                lines.append(f"- {p.symbol}: +{p.unrealised_pnl_pct:.1f}%")
        if fallers:
            lines.append("**Biggest fallers:**")
            for p in fallers:
                lines.append(f"- {p.symbol}: {p.unrealised_pnl_pct:.1f}%")
    else:
        lines.append("No position data available.")
    lines.append("")

    # Watchlist Notes
    lines.append("## Watchlist Notes")
    lines.append("")
    if wl_items:
        for item in wl_items:
            symbol = item.instrument.symbol
            bar = price_repo.get_latest(session, item.instrument_id)
            price = price_repo.best_price(bar) if bar else None
            notes: list[str] = []
            if (
                item.instrument.symbol
                and price is None
                and is_manual_price_symbol(item.instrument.symbol)
            ):
                notes.append("Manual-price only")
            elif price is not None:
                if item.target_buy_price and price <= item.target_buy_price:
                    notes.append(f"Near buy target ({_fmt(item.target_buy_price)})")
                if item.target_sell_price and price >= item.target_sell_price:
                    notes.append(f"Near sell target ({_fmt(item.target_sell_price)})")
            label = f"- **{symbol}**: price {_fmt(price)}"
            if notes:
                label += " — " + ", ".join(notes)
            lines.append(label)
    else:
        lines.append("Watchlist is empty.")
    lines.append("")

    # Trades Today
    lines.append("## Trades Today")
    lines.append("")
    if today_trades:
        for t in today_trades:
            lines.append(
                f"- {t.side.upper()} {t.quantity:.4f} {t.instrument.symbol} @ "
                f"{t.price:.4f} {t.currency}"
            )
    else:
        lines.append("No trades today.")
    lines.append("")

    # Data Quality
    lines.append("## Data Quality")
    lines.append("")
    report = build_data_quality_report(session)
    warning_issues = [issue for issue in report.issues if issue.severity == "warning"]
    if warning_issues:
        for issue in report.issues:
            bullet = f"- {issue.label}: {issue.message}"
            if issue.symbols:
                bullet += f" ({', '.join(issue.symbols)})"
            lines.append(bullet)
    else:
        lines.append("- No data quality issues detected.")
    lines.append("")

    return "\n".join(lines)
