from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from vmarket.services.valuation_service import compute_positions

_TARGETS_FILE = Path("user_data/targets.json")


@dataclass
class DriftRow:
    label: str
    target_pct: float
    actual_pct: float
    drift_pct: float        # actual − target; positive = overweight
    severity: str           # 'ok', 'mild', 'significant'
    symbols: list[str]


def get_targets() -> dict[str, float]:
    """Return target percentages keyed by asset-type label."""
    try:
        return json.loads(_TARGETS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_targets(targets: dict[str, float]) -> None:
    _TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TARGETS_FILE.write_text(json.dumps(targets, indent=2), encoding="utf-8")


def compute_allocation_drift(session: Session) -> list[DriftRow]:
    """
    Bucket live positions by asset_type, compute actual allocation percentages,
    and compare against stored targets.
    """
    positions = compute_positions(session)
    targets = get_targets()

    # Bucket positions by asset_type (None → 'unclassified')
    buckets: dict[str, list] = {}
    for pos in positions:
        label = (pos.asset_type or "unclassified").lower()
        buckets.setdefault(label, []).append(pos)

    total_base = sum(
        (p.value_in_base for p in positions if p.value_in_base is not None), Decimal("0")
    )

    # All labels = union of buckets and targets
    all_labels = sorted(set(buckets) | set(k.lower() for k in targets))

    rows: list[DriftRow] = []
    for label in all_labels:
        bucket_positions = buckets.get(label, [])
        bucket_value = sum(
            (p.value_in_base for p in bucket_positions if p.value_in_base is not None),
            Decimal("0"),
        )
        actual_pct = float(bucket_value / total_base * 100) if total_base > 0 else 0.0
        target_pct = float(targets.get(label, targets.get(label.title(), 0.0)))
        drift_pct = actual_pct - target_pct

        abs_drift = abs(drift_pct)
        if abs_drift >= 10:
            severity = "significant"
        elif abs_drift >= 5:
            severity = "mild"
        else:
            severity = "ok"

        rows.append(
            DriftRow(
                label=label,
                target_pct=target_pct,
                actual_pct=actual_pct,
                drift_pct=drift_pct,
                severity=severity,
                symbols=[p.symbol for p in bucket_positions],
            )
        )

    rows.sort(key=lambda r: abs(r.drift_pct), reverse=True)
    return rows
