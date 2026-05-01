from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from pydantic import TypeAdapter

from vmarket.research.schema import NormalizedEvidenceItem

_ITEM_ADAPTER = TypeAdapter(NormalizedEvidenceItem)


def evidence_path(symbol: str, run_date: date | None = None, root: Path | None = None) -> Path:
    base = root or Path("research")
    safe_symbol = symbol.upper().replace("/", "_")
    stamp = (run_date or date.today()).isoformat()
    return base / "normalized" / safe_symbol / f"{stamp}.jsonl"


def stable_dedupe_key(*parts: str) -> str:
    joined = "\n".join(part.strip() for part in parts if part and part.strip())
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def write_evidence_items(path: Path, items: Iterable[NormalizedEvidenceItem]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            payload = item.model_dump(mode="json", exclude_none=True)
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            count += 1
    return count


def read_evidence_items(path: Path) -> list[NormalizedEvidenceItem]:
    if not path.exists():
        return []

    items: list[NormalizedEvidenceItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        items.append(_ITEM_ADAPTER.validate_json(line))
    return items


def read_symbol_evidence(
    symbol: str,
    root: Path | None = None,
    limit_files: int | None = None,
) -> list[NormalizedEvidenceItem]:
    base = root or Path("research")
    safe_symbol = symbol.upper().replace("/", "_")
    paths = sorted((base / "normalized" / safe_symbol).glob("*.jsonl"), reverse=True)
    if limit_files is not None:
        paths = paths[:limit_files]

    seen: set[str] = set()
    items: list[NormalizedEvidenceItem] = []
    for path in paths:
        for item in read_evidence_items(path):
            if item.dedupe_key in seen:
                continue
            seen.add(item.dedupe_key)
            items.append(item)
    return items

