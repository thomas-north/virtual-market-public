#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
. .venv/bin/activate

echo "[$(date)] Starting daily sync..."

vmarket sync prices --days 7
vmarket sync fx --days 7
vmarket memo daily --output "reports/daily_$(date +%F).md"
vmarket chart portfolio --days 30 --html reports/chart_portfolio.html
vmarket chart allocation --html reports/chart_allocation.html
vmarket chart pnl --html reports/chart_pnl.html

echo "[$(date)] Sync complete."
