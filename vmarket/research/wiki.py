from __future__ import annotations

from datetime import date
from pathlib import Path

WIKI_DIRS = (
    "entities",
    "theses",
    "sources",
    "questions",
)


def init_research_workspace(root: Path | None = None) -> list[Path]:
    base = root or Path("research")
    created: list[Path] = []

    for rel in ("raw", "normalized", "wiki", *(f"wiki/{name}" for name in WIKI_DIRS)):
        path = base / rel
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)

    index = base / "wiki" / "index.md"
    if not index.exists():
        index.write_text(_starter_index(), encoding="utf-8")
        created.append(index)

    log = base / "wiki" / "log.md"
    if not log.exists():
        log.write_text(_starter_log(), encoding="utf-8")
        created.append(log)

    return created


def append_log_entry(
    message: str,
    root: Path | None = None,
    entry_date: date | None = None,
) -> Path:
    base = root or Path("research")
    log = base / "wiki" / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    stamp = entry_date or date.today()
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## [{stamp.isoformat()}] {message}\n")
    return log


def _starter_index() -> str:
    return """# Research Wiki Index

This private wiki is maintained by the agent from local raw and normalized
evidence. Raw sources remain the source of truth.

## Entities

## Theses

## Sources

## Questions
"""


def _starter_log() -> str:
    return """# Research Wiki Log

Append-only record of research ingests, wiki updates, and analysis questions.
"""

