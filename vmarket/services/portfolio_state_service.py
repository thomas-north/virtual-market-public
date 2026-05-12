from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from vmarket.config import get_user_data_dir
from vmarket.repositories import portfolios as port_repo


def _legacy_benchmark_path() -> Path:
    return get_user_data_dir() / "benchmark.txt"


def _legacy_targets_path() -> Path:
    return get_user_data_dir() / "targets.json"


def _portfolio(session: Session):
    return port_repo.get_or_create_default(session)


def _normalise_targets(targets: dict[str, float]) -> dict[str, float]:
    return {str(label).strip().lower(): float(value) for label, value in targets.items()}


def _read_legacy_benchmark() -> str | None:
    try:
        symbol = _legacy_benchmark_path().read_text(encoding="utf-8").strip().upper()
    except FileNotFoundError:
        return None
    return symbol or None


def _read_legacy_targets() -> dict[str, float]:
    try:
        raw = json.loads(_legacy_targets_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return _normalise_targets(
        {str(key): float(value) for key, value in raw.items() if isinstance(value, (int, float))}
    )


def get_benchmark_symbol(session: Session, *, migrate_legacy: bool = True) -> str | None:
    portfolio = _portfolio(session)
    if portfolio.benchmark_symbol:
        return portfolio.benchmark_symbol
    if migrate_legacy:
        legacy = _read_legacy_benchmark()
        if legacy:
            portfolio.benchmark_symbol = legacy
            session.flush()
            return legacy
    return None


def get_allocation_targets(session: Session, *, migrate_legacy: bool = True) -> dict[str, float]:
    portfolio = _portfolio(session)
    if portfolio.drift_targets_json:
        try:
            raw = json.loads(portfolio.drift_targets_json)
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict):
            return _normalise_targets(
                {
                    str(key): float(value)
                    for key, value in raw.items()
                    if isinstance(value, (int, float))
                }
            )
    if migrate_legacy:
        legacy = _read_legacy_targets()
        if legacy:
            save_allocation_targets(session, legacy)
            return legacy
    return {}


def save_allocation_targets(session: Session, targets: dict[str, float]) -> dict[str, float]:
    portfolio = _portfolio(session)
    normalised = _normalise_targets(targets)
    portfolio.drift_targets_json = json.dumps(normalised, sort_keys=True)
    session.flush()
    return normalised
