#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
. .venv/bin/activate

echo "[$(date)] Starting daily sync..."

vmarket sync prices --days 7
vmarket sync fx --days 7
vmarket report overview --html reports/overview.html
vmarket report memo --output "reports/daily_$(date +%F).md"
vmarket report chart portfolio --days 30 --html reports/chart_portfolio.html
vmarket report chart allocation --html reports/chart_allocation.html
vmarket report chart pnl --html reports/chart_pnl.html

echo "[$(date)] Sync complete."
