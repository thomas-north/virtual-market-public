from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from vmarket.consult.models import FactsheetHolding, FactsheetSummary, WeightedExposure
from vmarket.consult.store import load_factsheet_registry


def _normalized_root(root: Path) -> Path:
    return root / "normalized" / "factsheets"


def _raw_root(root: Path) -> Path:
    return root / "raw" / "factsheets"


def _normalize_identifier(identifier: str) -> str:
    return identifier.strip().upper()


def _cache_path(identifier: str, research_root: Path) -> Path:
    return _normalized_root(research_root) / f"{_normalize_identifier(identifier)}.json"


def _write_raw_capture(identifier: str, research_root: Path, response: requests.Response) -> Path:
    raw_root = _raw_root(research_root)
    raw_root.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(response.url)
    suffix = Path(parsed.path).suffix or ".html"
    output = raw_root / f"{_normalize_identifier(identifier)}{suffix}"
    output.write_bytes(response.content)
    return output


def _registry_entry(identifier: str, reference_root: Path | None = None) -> dict | None:
    wanted = _normalize_identifier(identifier)
    for entry in load_factsheet_registry(reference_root=reference_root):
        aliases = {entry.get("identifier", "").upper()}
        aliases.update(alias.upper() for alias in entry.get("aliases", []))
        if wanted in aliases:
            return entry
    return None


def _summary_from_payload(payload: dict) -> FactsheetSummary:
    return FactsheetSummary(
        identifier=payload["identifier"],
        fund_name=payload["fund_name"],
        ticker=payload.get("ticker"),
        isin=payload.get("isin"),
        ter_pct=payload.get("ter_pct"),
        ocf_pct=payload.get("ocf_pct"),
        aum_value=payload.get("aum_value"),
        holdings_count=payload.get("holdings_count"),
        top_holdings=[
            FactsheetHolding.model_validate(item) for item in payload.get("top_holdings", [])
        ],
        country_exposure=[
            WeightedExposure.model_validate(item) for item in payload.get("country_exposure", [])
        ],
        sector_exposure=[
            WeightedExposure.model_validate(item) for item in payload.get("sector_exposure", [])
        ],
        distribution_policy=payload.get("distribution_policy"),
        replication_method=payload.get("replication_method"),
        domicile=payload.get("domicile"),
        benchmark_index=payload.get("benchmark_index"),
        factsheet_date=date.fromisoformat(payload["factsheet_date"])
        if payload.get("factsheet_date")
        else None,
        source_url=payload["source_url"],
        source_type=payload["source_type"],
        fallback_used=payload.get("fallback_used", False),
        collected_at=(
            datetime.fromisoformat(payload["collected_at"])
            if payload.get("collected_at")
            else datetime.now(UTC)
        ),
        verification_notes=payload.get("verification_notes", []),
    )


def _write_normalized(summary: FactsheetSummary, research_root: Path) -> Path:
    path = _cache_path(summary.identifier, research_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path


def load_cached_factsheet(identifier: str, research_root: Path) -> FactsheetSummary | None:
    path = _cache_path(identifier, research_root)
    if not path.exists():
        return None
    return _summary_from_payload(json.loads(path.read_text(encoding="utf-8")))


def locate_factsheet(
    identifier: str,
    research_root: Path = Path("research"),
    reference_root: Path | None = None,
    fetch_source: bool = True,
    timeout: int = 20,
) -> FactsheetSummary:
    cached = load_cached_factsheet(identifier, research_root=research_root)
    if cached is not None:
        return cached

    entry = _registry_entry(identifier, reference_root=reference_root)
    if entry is None:
        raise ValueError(f"No verified factsheet registry entry found for {identifier}.")

    notes = list(entry.get("verification_notes", []))
    if fetch_source:
        try:
            response = requests.get(entry["source_url"], timeout=timeout)
            response.raise_for_status()
            raw_path = _write_raw_capture(identifier, research_root, response)
            notes.append(f"Raw source captured at {raw_path}.")
        except requests.RequestException as exc:
            notes.append(f"Source capture failed: {exc}")

    summary = _summary_from_payload(
        {
            **entry,
            "identifier": _normalize_identifier(identifier),
            "collected_at": datetime.now(UTC).isoformat(),
            "verification_notes": notes,
        }
    )
    _write_normalized(summary, research_root=research_root)
    return summary
