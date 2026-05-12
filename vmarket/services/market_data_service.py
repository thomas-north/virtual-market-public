from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from sqlalchemy.orm import Session

from vmarket.config import get_alpha_vantage_key
from vmarket.errors import ProviderError
from vmarket.providers.alpha_vantage import AlphaVantageProvider
from vmarket.providers.stooq import StooqProvider
from vmarket.providers.yahoo_finance import YahooFinanceProvider
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import job_runs as job_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo
from vmarket.repositories import watchlist as wl_repo
from vmarket.services.freshness import is_manual_price_symbol


@dataclass
class SyncResult:
    fetched: int = 0
    updated_bars: int = 0
    failed: list[str] = field(default_factory=list)
    manual_priced: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _symbols_to_sync(session: Session) -> list[str]:
    portfolio = port_repo.get_or_create_default(session)
    symbols: set[str] = set()

    for item in wl_repo.list_all(session):
        symbols.add(item.instrument.symbol)

    for trade in trade_repo.list_trades(session, portfolio.id):
        symbols.add(trade.instrument.symbol)

    return sorted(symbols)


def infer_market_currency(symbol: str) -> str | None:
    symbol = symbol.upper()
    if symbol.endswith(".US"):
        return "USD"
    if symbol.endswith(".L"):
        return "GBP"
    if len(symbol) == 7 and symbol.isalnum():
        return "GBP"
    return None


def _normalise_bars(bars, canonical_symbol: str) -> list:
    inferred_currency = infer_market_currency(canonical_symbol)
    return [
        replace(
            bar,
            symbol=canonical_symbol,
            currency=bar.currency or inferred_currency,
        )
        for bar in bars
    ]


def sync_prices(
    session: Session,
    symbol: str | None = None,
    days: int = 7,
) -> SyncResult:
    result = SyncResult()
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    if symbol:
        symbols = [symbol]
    else:
        symbols = _symbols_to_sync(session)

    if not symbols:
        result.warnings.append("No instruments to sync. Add instruments to watchlist first.")
        return result

    stooq = StooqProvider()
    yahoo = YahooFinanceProvider()
    av_key = get_alpha_vantage_key()
    av = AlphaVantageProvider(av_key) if av_key else None

    job = job_repo.start(session, "sync_prices")

    for sym in symbols:
        if is_manual_price_symbol(sym):
            result.manual_priced.append(sym)
            result.warnings.append(
                f"{sym} is manual-price only. Record trades with --price; "
                "automatic sync is skipped."
            )
            continue

        instrument = inst_repo.get_by_symbol(session, sym)
        if instrument is None:
            result.failed.append(sym)
            result.warnings.append(f"Instrument {sym} not found in database.")
            continue

        provider_symbol = instrument.provider_symbol
        is_lse = sym.upper().endswith(".L")
        bars = None

        try:
            bars = _normalise_bars(
                stooq.fetch_daily_prices([provider_symbol], start_date, end_date),
                sym,
            )
        except ProviderError as exc:
            stooq_err = str(exc)
            # Yahoo Finance handles both LSE (.L) and US stocks (strip .US suffix).
            # It's tried before Alpha Vantage to preserve the AV daily quota.
            yf_symbol = sym if is_lse else sym.split(".")[0].upper()
            try:
                raw = yahoo.fetch_daily_prices([yf_symbol], start_date, end_date)
                bars = _normalise_bars(raw, sym)
            except ProviderError as yf_exc:
                yf_err = str(yf_exc)
                if not is_lse and av:
                    try:
                        bars = _normalise_bars(
                            av.fetch_daily_prices([sym], start_date, end_date),
                            sym,
                        )
                    except ProviderError as av_exc:
                        result.failed.append(sym)
                        result.warnings.append(
                            f"Stooq failed for {sym}: {stooq_err}. "
                            f"Yahoo Finance failed: {yf_err}. "
                            f"Alpha Vantage also failed: {av_exc}"
                        )
                        continue
                else:
                    result.failed.append(sym)
                    result.warnings.append(
                        f"Stooq failed for {sym}: {stooq_err}. "
                        f"Yahoo Finance also failed: {yf_err}"
                    )
                    continue

        if bars:
            count = price_repo.upsert_price_bars(session, instrument.id, bars)
            result.updated_bars += count
            result.fetched += 1

    status = "success" if not result.failed else ("partial" if result.fetched else "failed")
    msg = (
        f"Fetched {result.fetched} instruments, {result.updated_bars} bars. "
        f"Manual-only: {result.manual_priced}. Failed: {result.failed}"
    )
    job_repo.finish(session, job, status=status, message=msg)

    return result
