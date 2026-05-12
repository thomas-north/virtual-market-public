from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from plotly.offline import get_plotlyjs
from sqlalchemy.orm import Session

from vmarket.reports.io import write_report_file
from vmarket.repositories import cash as cash_repo
from vmarket.repositories import job_runs as job_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import watchlist as wl_repo
from vmarket.services.chart_service import (
    benchmark_price_series,
    holding_value_series,
    portfolio_value_series,
)
from vmarket.services.data_quality import build_data_quality_report
from vmarket.services.freshness import is_manual_price_symbol, price_status_for
from vmarket.services.valuation_service import compute_positions


def build_portfolio_snapshot_payload(session: Session, days: int = 30) -> dict[str, object]:
    portfolio = port_repo.get_or_create_default(session)
    base_currency = portfolio.base_currency
    points = portfolio_value_series(session, days=days)
    positions = compute_positions(session, base_currency=base_currency)
    position_series = holding_value_series(session, days=days)
    balances = cash_repo.get_balances_all_currencies(session, portfolio.id)
    watchlist_items = wl_repo.list_all(session)
    last_sync = job_repo.get_latest(session, "sync_prices")

    total_cash = sum(balances.values(), Decimal("0"))
    total_invested = sum(
        (position.value_in_base for position in positions if position.value_in_base is not None),
        Decimal("0"),
    )
    total_value = total_cash + total_invested
    unrealised_pnl = sum(
        (position.unrealised_pnl for position in positions if position.unrealised_pnl is not None),
        Decimal("0"),
    )

    baseline_point = next(
        (point for point in points if point.value > 0),
        points[0] if points else None,
    )
    latest_point = points[-1] if points else None
    change_value = (
        latest_point.value - baseline_point.value
        if latest_point is not None and baseline_point is not None
        else None
    )
    change_pct = (
        (change_value / baseline_point.value * Decimal("100"))
        if change_value is not None and baseline_point is not None and baseline_point.value > 0
        else None
    )
    change_label = "30-day change"
    if baseline_point is not None and points and baseline_point.date != points[0].date:
        change_label = "Change since first active day"

    active_positions: list[dict[str, object]] = []
    manual_positions: list[dict[str, object]] = []
    for position in positions:
        row = _holding_row(position, total_invested, position_series.get(position.symbol, []))
        if position.price_status == "manual":
            manual_positions.append(row)
        else:
            active_positions.append(row)

    active_positions.sort(key=lambda row: row["sort_value"], reverse=True)
    manual_positions.sort(key=lambda row: row["symbol"])

    watchlist_highlights = _watchlist_highlights(watchlist_items, positions, session)
    data_quality_report = build_data_quality_report(session)
    data_quality = [issue.model_dump(mode="json") for issue in data_quality_report.issues]

    fresh_count = sum(1 for position in positions if position.price_status == "fresh")
    manual_count = sum(1 for position in positions if position.price_status == "manual")
    warning_count = data_quality_report.warning_count

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "as_of": date.today().isoformat(),
        "base_currency": base_currency,
        "summary": {
            "portfolio_name": portfolio.name,
            "freshness_label": (
                f"{fresh_count} priced holdings, {manual_count} manual-price holdings, "
                f"{warning_count} active data warnings"
            ),
            "last_sync": (
                last_sync.finished_at.isoformat()
                if last_sync and last_sync.finished_at
                else None
            ),
            "cards": [
                _metric_card("Total value", total_value, base_currency, tone="neutral"),
                _metric_card("Invested", total_invested, base_currency, tone="neutral"),
                _metric_card("Cash", total_cash, base_currency, tone="neutral"),
                _metric_card(
                    change_label,
                    change_value,
                    base_currency,
                    pct=change_pct,
                    tone="accent",
                ),
                _metric_card(
                    "Unrealised P/L",
                    unrealised_pnl,
                    base_currency,
                    tone=_tone_for_delta(unrealised_pnl),
                ),
            ],
        },
        "portfolio_series": _portfolio_series(session, points, days),
        "holdings": {
            "active": active_positions,
            "manual": manual_positions,
            "allocation_chart": [
                {"symbol": row["symbol"], "value": row["base_value"]}
                for row in active_positions
                if row["base_value"] is not None and row["base_value"] > 0
            ],
            "pnl_chart": [
                {"symbol": row["symbol"], "pct": row["unrealised_pnl_pct"]}
                for row in active_positions
                if row["unrealised_pnl_pct"] is not None
            ],
        },
        "watchlist_highlights": watchlist_highlights,
        "data_quality": data_quality,
        "cash_balances": [
            {
                "currency": currency,
                "value": float(value),
                "display": _money(value, currency),
            }
            for currency, value in sorted(balances.items())
        ],
    }


_BENCHMARK_FILE = Path("user_data/benchmark.txt")


def get_benchmark_symbol() -> str | None:
    """Return the configured benchmark symbol, or None if not set."""
    try:
        sym = _BENCHMARK_FILE.read_text(encoding="utf-8").strip()
        return sym or None
    except FileNotFoundError:
        return None


def set_benchmark_symbol(symbol: str) -> None:
    _BENCHMARK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _BENCHMARK_FILE.write_text(symbol.strip().upper(), encoding="utf-8")


def clear_benchmark_symbol() -> None:
    _BENCHMARK_FILE.unlink(missing_ok=True)


def _portfolio_series(session, points, days: int) -> dict[str, object]:
    dates = [p.date.isoformat() for p in points]
    total = [float(p.value) for p in points]
    invested = [float(p.invested) for p in points]
    cash = [float(p.cash) for p in points]

    benchmark_symbol = get_benchmark_symbol()
    benchmark: list[float | None] | None = None
    if benchmark_symbol and points:
        raw = benchmark_price_series(session, benchmark_symbol, [p.date for p in points])
        # Only include if we have at least one non-None value
        if any(v is not None for v in raw):
            benchmark = raw

    result: dict[str, object] = {
        "days": days,
        "dates": dates,
        "total": total,
        "invested": invested,
        "cash": cash,
        "benchmark_symbol": benchmark_symbol,
        "benchmark": benchmark,
    }
    return result


def build_overview_payload(session: Session, days: int = 30) -> dict[str, object]:
    return build_portfolio_snapshot_payload(session, days=days)


def render_overview_html(payload: dict[str, object]) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"))
    plotly_js = get_plotlyjs()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portfolio Overview</title>
  <style>
    :root {{
      --bg: #0b1117;
      --panel: #121a23;
      --panel-soft: #182331;
      --panel-elevated: #1d2938;
      --border: rgba(197, 218, 240, 0.12);
      --text: #eef3f7;
      --muted: #8ea1b4;
      --accent: #5ac8a8;
      --accent-soft: rgba(90, 200, 168, 0.14);
      --danger: #f26d6d;
      --danger-soft: rgba(242, 109, 109, 0.14);
      --warning: #f4c96b;
      --warning-soft: rgba(244, 201, 107, 0.14);
      --radius: 8px;
      --shadow: 0 18px 40px rgba(1, 8, 16, 0.32);
      --mono: "IBM Plex Mono", "SFMono-Regular", "Menlo", monospace;
      --sans: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top right, rgba(90, 200, 168, 0.12), transparent 28%),
        linear-gradient(180deg, #0b1117 0%, #0e151d 100%);
      color: var(--text);
      font-family: var(--sans);
    }}
    .shell {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 24px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      color: var(--muted);
      font-family: var(--mono);
      font-size: 12px;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 6px 0 10px;
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1.05;
      font-weight: 650;
    }}
    .subtitle {{
      color: var(--muted);
      max-width: 820px;
      font-size: 15px;
      line-height: 1.5;
    }}
    .freshness-pill {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 10px 14px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .card, .panel {{
      background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent 50%), var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }}
    .card {{
      padding: 16px 18px;
      min-height: 128px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .card-label {{
      color: var(--muted);
      font-size: 13px;
    }}
    .card-value {{
      font-size: clamp(24px, 2.4vw, 34px);
      line-height: 1.05;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .tone-accent .card-value {{ color: var(--accent); }}
    .tone-positive .card-value {{ color: var(--accent); }}
    .tone-negative .card-value {{ color: var(--danger); }}
    .card-meta {{
      font-family: var(--mono);
      font-size: 12px;
      color: var(--muted);
    }}
    .main-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.9fr) minmax(320px, 0.9fr);
      gap: 18px;
      margin-bottom: 18px;
    }}
    .panel {{
      padding: 18px;
    }}
    .panel h2 {{
      margin: 0 0 6px;
      font-size: 18px;
    }}
    .panel-intro {{
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 14px;
    }}
    .chart-panel {{
      min-height: 460px;
    }}
    .chart-host {{
      width: 100%;
      min-height: 360px;
    }}
    .side-stack {{
      display: grid;
      gap: 18px;
    }}
    .mini-list {{
      display: grid;
      gap: 10px;
    }}
    .mini-item {{
      padding: 12px 14px;
      background: var(--panel-soft);
      border: 1px solid rgba(197, 218, 240, 0.08);
      border-radius: 6px;
    }}
    .mini-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 6px;
      align-items: baseline;
    }}
    .mini-symbol {{
      font-weight: 650;
      font-size: 14px;
    }}
    .mini-note {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 5px 9px;
      border-radius: 999px;
      font-size: 11px;
      font-family: var(--mono);
      text-transform: uppercase;
      letter-spacing: 0;
      border: 1px solid transparent;
    }}
    .badge-fresh, .badge-positive {{
      color: #9de8d2;
      background: var(--accent-soft);
      border-color: rgba(90, 200, 168, 0.18);
    }}
    .badge-stale, .badge-warning {{
      color: #f3d990;
      background: var(--warning-soft);
      border-color: rgba(244, 201, 107, 0.2);
    }}
    .badge-manual, .badge-neutral {{
      color: #c7d5e3;
      background: rgba(199, 213, 227, 0.08);
      border-color: rgba(199, 213, 227, 0.12);
    }}
    .badge-missing, .badge-negative {{
      color: #ffb3b3;
      background: var(--danger-soft);
      border-color: rgba(242, 109, 109, 0.18);
    }}
    .holdings-panel {{
      margin-bottom: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      text-transform: uppercase;
      font-family: var(--mono);
      text-align: left;
      padding: 0 0 12px;
      letter-spacing: 0;
    }}
    td {{
      padding: 12px 0;
      border-top: 1px solid rgba(197, 218, 240, 0.08);
      vertical-align: middle;
      font-size: 14px;
    }}
    .symbol-cell strong {{
      display: block;
      font-size: 14px;
      margin-bottom: 2px;
    }}
    .subline {{
      color: var(--muted);
      font-size: 12px;
    }}
    .numeric {{
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .trend-svg {{
      width: 112px;
      height: 28px;
      display: block;
    }}
    .trend-empty {{
      color: var(--muted);
      font-size: 12px;
      font-family: var(--mono);
    }}
    .split-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .section-title {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 14px;
    }}
    .section-meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .empty {{
      color: var(--muted);
      padding: 12px 0 4px;
    }}
    @media (max-width: 1200px) {{
      .summary-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 980px) {{
      .topbar,
      .main-grid,
      .split-grid {{
        grid-template-columns: 1fr;
        display: grid;
      }}
      .topbar {{
        align-items: stretch;
      }}
      .summary-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 640px) {{
      .shell {{
        padding: 18px 16px 36px;
      }}
      .summary-grid {{
        grid-template-columns: 1fr;
      }}
      .chart-host {{
        min-height: 320px;
      }}
      table, thead, tbody, th, td, tr {{
        display: block;
      }}
      thead {{
        display: none;
      }}
      td {{
        padding: 8px 0;
      }}
      tr {{
        border-top: 1px solid rgba(197, 218, 240, 0.08);
        padding: 12px 0;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div>
        <div class="eyebrow">Virtual Market / Overview</div>
        <h1 id="overview-title"></h1>
        <div class="subtitle" id="overview-subtitle"></div>
      </div>
      <div class="freshness-pill" id="freshness-pill"></div>
    </div>

    <div class="summary-grid" id="summary-grid"></div>

    <div class="main-grid">
      <section class="panel chart-panel">
        <div class="section-title">
          <div>
            <h2>Portfolio performance</h2>
            <div class="section-meta">Whole portfolio value over the last 30 days.</div>
          </div>
        </div>
        <div id="portfolio-chart" class="chart-host"></div>
      </section>

      <div class="side-stack">
        <section class="panel">
          <div class="section-title">
            <div>
              <h2>Watchlist focus</h2>
              <div class="section-meta">
                Target hits, near-target names, and manual-price items.
              </div>
            </div>
          </div>
          <div id="watchlist-list" class="mini-list"></div>
        </section>

        <section class="panel">
          <div class="section-title">
            <div>
              <h2>Data quality</h2>
              <div class="section-meta">
                Freshness and valuation caveats that affect interpretation.
              </div>
            </div>
          </div>
          <div id="data-quality-list" class="mini-list"></div>
        </section>
      </div>
    </div>

    <section class="panel holdings-panel">
      <div class="section-title">
        <div>
          <h2>Holdings breakdown</h2>
          <div class="section-meta">
            Current positions, weights, P/L, valuation state, and 30-day trend.
          </div>
        </div>
      </div>
      <div id="holdings-active"></div>
      <div id="holdings-manual" style="margin-top:18px;"></div>
    </section>

    <div class="split-grid">
      <section class="panel">
        <div class="section-title">
          <div>
            <h2>Allocation</h2>
            <div class="section-meta">Current weight of priced holdings in base currency.</div>
          </div>
        </div>
        <div id="allocation-chart" class="chart-host"></div>
      </section>

      <section class="panel">
        <div class="section-title">
          <div>
            <h2>Unrealised P/L</h2>
            <div class="section-meta">Relative gain or loss for priced holdings.</div>
          </div>
        </div>
        <div id="pnl-chart" class="chart-host"></div>
      </section>
    </div>
  </div>

  <script>{plotly_js}</script>
  <script id="overview-payload" type="application/json">{payload_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById("overview-payload").textContent);

    function money(value, currency = payload.base_currency) {{
      if (value === null || value === undefined) return "N/A";
      return new Intl.NumberFormat("en-GB", {{
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }}).format(value);
    }}

    function number(value, digits = 1) {{
      if (value === null || value === undefined) return "N/A";
      return new Intl.NumberFormat("en-GB", {{
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }}).format(value);
    }}

    function pct(value) {{
      if (value === null || value === undefined) return "N/A";
      const prefix = value > 0 ? "+" : "";
      return `${{prefix}}${{number(value, 1)}}%`;
    }}

    function badgeClass(status) {{
      if (status === "fresh" || status === "positive") return "badge badge-fresh";
      if (status === "stale" || status === "warning") return "badge badge-stale";
      if (status === "missing" || status === "negative") return "badge badge-missing";
      return "badge badge-manual";
    }}

    function badge(text, status) {{
      return `<span class="${{badgeClass(status)}}">${{text}}</span>`;
    }}

    function renderSummary() {{
      document.getElementById("overview-title").textContent =
        `${{payload.summary.portfolio_name}} portfolio overview`;
      const lastSyncText = payload.summary.last_sync
        ? `Last successful price sync: ${{new Date(payload.summary.last_sync).toLocaleString()}}.`
        : "No successful price sync recorded yet.";
      document.getElementById("overview-subtitle").textContent =
        `As of ${{payload.as_of}}. Base currency: ${{payload.base_currency}}. ${{lastSyncText}}`;
      document.getElementById("freshness-pill").textContent = payload.summary.freshness_label;

      const grid = document.getElementById("summary-grid");
      grid.innerHTML = payload.summary.cards.map((card) => `
        <article class="card tone-${{card.tone}}">
          <div class="card-label">${{card.label}}</div>
          <div class="card-value">${{card.display}}</div>
          <div class="card-meta">${{card.meta}}</div>
        </article>
      `).join("");
    }}

    function renderPortfolioChart() {{
      const ps = payload.portfolio_series;
      const traces = [
        {{
          x: ps.dates,
          y: ps.total,
          name: "Total",
          mode: "lines",
          line: {{ color: "#5ac8a8", width: 3 }},
        }},
        {{
          x: ps.dates,
          y: ps.invested,
          name: "Invested",
          mode: "lines",
          line: {{ color: "#84a8ff", width: 2 }},
          fill: "tozeroy",
          fillcolor: "rgba(132, 168, 255, 0.08)",
        }},
        {{
          x: ps.dates,
          y: ps.cash,
          name: "Cash",
          mode: "lines",
          line: {{ color: "#f4c96b", width: 2, dash: "dot" }},
        }},
      ];
      if (ps.benchmark && ps.benchmark.length) {{
        // Normalise benchmark to start at the same value as portfolio total
        const firstTotal = ps.total.find((v) => v != null);
        const firstBench = ps.benchmark.find((v) => v != null);
        if (firstTotal != null && firstBench != null && firstBench !== 0) {{
          const scale = firstTotal / firstBench;
          traces.push({{
            x: ps.dates,
            y: ps.benchmark.map((v) => v != null ? v * scale : null),
            name: ps.benchmark_symbol + " (benchmark)",
            mode: "lines",
            line: {{ color: "#8ea1b4", width: 2, dash: "dot" }},
            connectgaps: false,
          }});
        }}
      }}
      Plotly.newPlot("portfolio-chart", traces, {{
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: {{ color: "#eef3f7", family: '"Avenir Next", "Segoe UI", sans-serif' }},
        margin: {{ l: 44, r: 12, t: 18, b: 36 }},
        xaxis: {{ gridcolor: "rgba(197,218,240,0.06)", zeroline: false }},
        yaxis: {{ gridcolor: "rgba(197,218,240,0.06)", zeroline: false }},
        legend: {{ orientation: "h", x: 0, y: 1.12 }},
      }}, {{
        displayModeBar: false,
        responsive: true,
      }});
    }}

    function sparklineSvg(values) {{
      const numeric = values.filter((value) => value !== null && value !== undefined);
      if (numeric.length < 2) {{
        return '<span class="trend-empty">n/a</span>';
      }}
      const width = 112;
      const height = 28;
      const min = Math.min(...numeric);
      const max = Math.max(...numeric);
      const range = max - min || 1;
      const points = values.map((value, index) => {{
        const x = (index / Math.max(values.length - 1, 1)) * width;
        const normalized = value === null || value === undefined
          ? null
          : height - (((value - min) / range) * (height - 4) + 2);
        return normalized === null ? null : `${{x.toFixed(1)}},${{normalized.toFixed(1)}}`;
      }}).filter(Boolean);
      const color = numeric[numeric.length - 1] >= numeric[0] ? "#5ac8a8" : "#f26d6d";
      return `<svg
        class="trend-svg"
        viewBox="0 0 ${{width}} ${{height}}"
        preserveAspectRatio="none"
      >
        <polyline
          fill="none"
          stroke="${{color}}"
          stroke-width="2.2"
          points="${{points.join(" ")}}"
        />
      </svg>`;
    }}

    function holdingRow(row) {{
      const weightText =
        row.weight_pct === null ? "N/A" : `${{number(row.weight_pct, 1)}}%`;
      const fxBadge = row.fx_status !== "not_needed"
        ? ` ${{badge(row.fx_status.replace("_", " "), row.fx_status)}}`
        : "";
      return `
        <tr>
          <td class="symbol-cell">
            <strong>${{row.symbol}}</strong>
            <div class="subline">${{row.name || ""}}</div>
          </td>
          <td class="numeric">${{number(row.quantity, 4)}}</td>
          <td class="numeric">${{money(row.base_value, payload.base_currency)}}</td>
          <td class="numeric">${{weightText}}</td>
          <td class="numeric">${{pct(row.unrealised_pnl_pct)}}</td>
          <td>${{badge(row.price_status, row.price_status)}}${{fxBadge}}</td>
          <td>${{sparklineSvg(row.sparkline)}}</td>
        </tr>
      `;
    }}

    function renderHoldings() {{
      const active = payload.holdings.active;
      const manual = payload.holdings.manual;
      const activeHost = document.getElementById("holdings-active");
      const manualHost = document.getElementById("holdings-manual");

      activeHost.innerHTML = active.length ? `
        <table>
          <thead>
            <tr>
              <th>Holding</th>
              <th>Qty</th>
              <th>Base value</th>
              <th>Weight</th>
              <th>Unrealised P/L</th>
              <th>Status</th>
              <th>30-day trend</th>
            </tr>
          </thead>
          <tbody>${{active.map(holdingRow).join("")}}</tbody>
        </table>
      ` : '<div class="empty">No priced holdings are available for the current window.</div>';

      manualHost.innerHTML = manual.length ? `
        <div class="section-title">
          <div>
            <h2>Manual-price holdings</h2>
            <div class="section-meta">
              These positions are carried in the portfolio but require
              explicit trade pricing.
            </div>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Holding</th>
              <th>Qty</th>
              <th>Avg cost</th>
              <th>Status</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            ${{manual.map((row) => `
              <tr>
                <td class="symbol-cell">
                  <strong>${{row.symbol}}</strong>
                  <div class="subline">${{row.name || ""}}</div>
                </td>
                <td class="numeric">${{number(row.quantity, 4)}}</td>
                <td class="numeric">${{money(row.avg_cost, row.currency)}}</td>
                <td>${{badge(row.price_status, row.price_status)}}</td>
                <td class="subline">${{row.price_status_note}}</td>
              </tr>
            `).join("")}}
          </tbody>
        </table>
      ` : "";
    }}

    function renderWatchlist() {{
      const host = document.getElementById("watchlist-list");
      host.innerHTML = payload.watchlist_highlights.length
        ? payload.watchlist_highlights.map((item) => `
        <article class="mini-item">
          <div class="mini-top">
            <div class="mini-symbol">${{item.symbol}}</div>
            <div class="numeric">${{item.latest_price_display}}</div>
          </div>
          <div class="mini-note">${{item.note}}</div>
          <div class="badge-row">
            ${{badge(item.status, item.status)}}
            ${{item.flag ? badge(item.flag, item.flag_tone) : ""}}
          </div>
        </article>
      `).join("")
        : '<div class="empty">No watchlist highlights right now.</div>';
    }}

    function renderDataQuality() {{
      const host = document.getElementById("data-quality-list");
      host.innerHTML = payload.data_quality.length ? payload.data_quality.map((item) => `
        <article class="mini-item">
          <div class="mini-top">
            <div class="mini-symbol">${{item.label}}</div>
            <div>${{badge(item.severity, item.severity)}}</div>
          </div>
          <div class="mini-note">${{item.message}}</div>
        </article>
      `).join("") : '<div class="empty">No active data-quality issues.</div>';
    }}

    function renderBreakdownCharts() {{
      const allocation = payload.holdings.allocation_chart;
      if (allocation.length) {{
        Plotly.newPlot("allocation-chart", [{{
          type: "pie",
          labels: allocation.map((item) => item.symbol),
          values: allocation.map((item) => item.value),
          hole: 0.55,
          textinfo: "label+percent",
          marker: {{
            colors: ["#5ac8a8", "#84a8ff", "#f4c96b", "#f28e5c", "#9bc1cf", "#c4d96f"],
          }},
        }}], {{
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: {{ color: "#eef3f7", family: '"Avenir Next", "Segoe UI", sans-serif' }},
          margin: {{ l: 12, r: 12, t: 18, b: 18 }},
          showlegend: false,
        }}, {{
          displayModeBar: false,
          responsive: true,
        }});
      }}

      const pnl = payload.holdings.pnl_chart;
      if (pnl.length) {{
        Plotly.newPlot("pnl-chart", [{{
          type: "bar",
          orientation: "h",
          y: pnl.map((item) => item.symbol),
          x: pnl.map((item) => item.pct),
          marker: {{
            color: pnl.map((item) => item.pct >= 0 ? "#5ac8a8" : "#f26d6d"),
          }},
        }}], {{
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
        font: {{
          color: "#eef3f7",
          family: '"Avenir Next", "Segoe UI", sans-serif',
        }},
        margin: {{ l: 64, r: 12, t: 18, b: 36 }},
          xaxis: {{
            gridcolor: "rgba(197,218,240,0.06)",
            zeroline: false,
            ticksuffix: "%",
          }},
          yaxis: {{ gridcolor: "rgba(197,218,240,0.0)" }},
        }}, {{
          displayModeBar: false,
          responsive: true,
        }});
      }}
    }}

    renderSummary();
    renderPortfolioChart();
    renderHoldings();
    renderWatchlist();
    renderDataQuality();
    renderBreakdownCharts();
  </script>
</body>
</html>
"""


def write_overview_html(session: Session, output: Path, days: int = 30) -> Path:
    payload = build_overview_payload(session, days=days)
    content = render_overview_html(payload)
    return write_report_file(output, content)


def _metric_card(
    label: str,
    value: Decimal | None,
    currency: str,
    *,
    pct: Decimal | None = None,
    tone: str = "neutral",
) -> dict[str, str]:
    meta_parts = [f"As of {date.today().isoformat()}"]
    if pct is not None:
        meta_parts.append(f"{_signed_decimal(pct, 1)}%")
    return {
        "label": label,
        "display": _money(value, currency),
        "meta": " / ".join(meta_parts),
        "tone": _tone_for_delta(value) if tone == "accent" and value is not None else tone,
    }


def _holding_row(
    position,
    total_invested: Decimal,
    series_points,
) -> dict[str, object]:
    weight_pct = (
        (position.value_in_base / total_invested * Decimal("100"))
        if position.value_in_base is not None and total_invested > 0
        else None
    )
    sparkline = [
        float(point.value) if point.value is not None else None
        for point in series_points
    ]
    return {
        "symbol": position.symbol,
        "name": position.name or "",
        "quantity": float(position.quantity),
        "avg_cost": float(position.avg_cost),
        "currency": position.cost_currency,
        "latest_price": float(position.latest_price) if position.latest_price is not None else None,
        "market_value": float(position.market_value) if position.market_value is not None else None,
        "base_value": float(position.value_in_base) if position.value_in_base is not None else None,
        "unrealised_pnl": (
            float(position.unrealised_pnl)
            if position.unrealised_pnl is not None
            else None
        ),
        "unrealised_pnl_pct": (
            float(position.unrealised_pnl_pct)
            if position.unrealised_pnl_pct is not None
            else None
        ),
        "weight_pct": float(weight_pct) if weight_pct is not None else None,
        "price_status": position.price_status,
        "price_status_note": position.price_status_note,
        "fx_status": position.fx_status,
        "sparkline": sparkline,
        "sort_value": float(position.value_in_base or Decimal("0")),
    }


def _watchlist_highlights(
    watchlist_items,
    positions,
    session: Session,
) -> list[dict[str, object]]:
    held_symbols = {position.symbol for position in positions}
    items: list[dict[str, object]] = []
    for item in watchlist_items:
        symbol = item.instrument.symbol
        latest_bar = price_repo.get_latest(session, item.instrument_id)
        latest_price = price_repo.best_price(latest_bar) if latest_bar else None
        status = price_status_for(symbol, latest_bar.date if latest_bar else None)

        flag = ""
        flag_tone = "neutral"
        note = status.note
        priority = 4

        if (
            latest_price is not None
            and item.target_buy_price is not None
            and latest_price <= item.target_buy_price
        ):
            flag = "buy target hit"
            flag_tone = "positive"
            note = (
                "Trading at or below the buy target of "
                f"{_money(item.target_buy_price, item.instrument.currency or 'GBP')}."
            )
            priority = 0
        elif (
            latest_price is not None
            and item.target_sell_price is not None
            and latest_price >= item.target_sell_price
        ):
            flag = "sell target hit"
            flag_tone = "warning"
            note = (
                "Trading at or above the sell target of "
                f"{_money(item.target_sell_price, item.instrument.currency or 'GBP')}."
            )
            priority = 0
        elif latest_price is not None and _near_target(latest_price, item.target_buy_price):
            flag = "near buy target"
            flag_tone = "warning"
            note = "Within 5% of the configured buy target."
            priority = 1
        elif latest_price is not None and _near_target(latest_price, item.target_sell_price):
            flag = "near sell target"
            flag_tone = "warning"
            note = "Within 5% of the configured sell target."
            priority = 1
        elif symbol in held_symbols:
            flag = "currently held"
            flag_tone = "neutral"
            note = "Already in the portfolio."
            priority = 2
        elif status.state.value == "manual" or is_manual_price_symbol(symbol):
            flag = "manual price"
            flag_tone = "neutral"
            note = status.note
            priority = 3

        items.append(
            {
                "symbol": symbol,
                "name": item.instrument.name or "",
                "latest_price_display": _money(latest_price, item.instrument.currency or "GBP"),
                "status": status.state.value,
                "flag": flag,
                "flag_tone": flag_tone,
                "note": note,
                "priority": priority,
            }
        )

    items.sort(key=lambda entry: (entry["priority"], entry["symbol"]))
    return items[:8]


def _money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.2f} {currency}"


def _signed_decimal(value: Decimal, digits: int) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.{digits}f}"


def _tone_for_delta(value: Decimal | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _near_target(price: Decimal, target: Decimal | None) -> bool:
    if target is None or target == 0:
        return False
    return abs(price - target) / target <= Decimal("0.05")
