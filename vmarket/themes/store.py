from __future__ import annotations

import json
from pathlib import Path

from vmarket.themes.models import EtfProfile, ThemeDefinition


def get_reference_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "reference" / "themes"


def list_themes() -> list[ThemeDefinition]:
    root = get_reference_root()
    themes: list[ThemeDefinition] = []
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text())
        themes.append(ThemeDefinition.model_validate(data))
    return themes


def load_theme(theme_id: str) -> ThemeDefinition | None:
    wanted = theme_id.strip().lower()
    for theme in list_themes():
        aliases = {theme.theme_id.lower(), theme.label.lower()}
        aliases.update(keyword.lower() for keyword in theme.keywords)
        if wanted in aliases:
            return theme
    return None


def find_profile(identifier: str) -> tuple[ThemeDefinition, EtfProfile] | None:
    wanted = identifier.strip().lower()
    for theme in list_themes():
        for profile in theme.candidates:
            aliases = {profile.profile_id.lower()}
            aliases.update(listing.symbol.lower() for listing in profile.facts.listings)
            if wanted in aliases:
                return theme, profile
    return None
