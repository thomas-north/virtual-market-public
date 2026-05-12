from __future__ import annotations

import json
from pathlib import Path


def get_reference_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "reference" / "consult"


def load_json(name: str, reference_root: Path | None = None) -> dict | list:
    root = reference_root or get_reference_root()
    return json.loads((root / name).read_text(encoding="utf-8"))


def load_classifications(reference_root: Path | None = None) -> dict:
    data = load_json("classifications.json", reference_root=reference_root)
    return data if isinstance(data, dict) else {}


def load_research_areas(reference_root: Path | None = None) -> list[dict]:
    data = load_json("research_areas.json", reference_root=reference_root)
    return data if isinstance(data, list) else []


def load_factsheet_registry(reference_root: Path | None = None) -> list[dict]:
    data = load_json("factsheets.json", reference_root=reference_root)
    return data if isinstance(data, list) else []
