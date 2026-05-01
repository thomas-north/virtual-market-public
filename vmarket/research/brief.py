from __future__ import annotations

from collections import Counter
from datetime import date

from vmarket.research.schema import NormalizedEvidenceItem, SourceClass


def render_evidence_brief(
    symbol: str,
    items: list[NormalizedEvidenceItem],
    as_of: date | None = None,
) -> str:
    as_of = as_of or date.today()
    lines: list[str] = [
        f"# {symbol.upper()} - Research Evidence Brief",
        "",
        f"Generated: {as_of.isoformat()}",
        f"Evidence items: {len(items)}",
        "",
    ]

    if not items:
        lines.extend(
            [
                "No normalized evidence found.",
                "",
                "Next step: collect recent raw sources and normalize them into JSONL.",
            ]
        )
        return "\n".join(lines)

    source_counts = Counter(item.source_class.value for item in items)
    role_counts = Counter(item.evidence_role.value for item in items)
    lines.append("## Coverage")
    lines.append("")
    lines.append(_counter_line("Source classes", source_counts))
    lines.append(_counter_line("Evidence roles", role_counts))
    lines.append("")

    for source_class in SourceClass:
        group = [item for item in items if item.source_class == source_class]
        if not group:
            continue
        lines.append(f"## {source_class.value}")
        lines.append("")
        for item in sorted(group, key=_sort_key, reverse=True)[:8]:
            published = _date_label(item)
            url = f" [{item.canonical_url}]" if item.canonical_url else ""
            excerpt = f" - {item.text_excerpt[:240]}" if item.text_excerpt else ""
            lines.append(f"- {published} {item.title}{url}{excerpt}")
        lines.append("")

    social_items = [item for item in items if item.source_class == SourceClass.SOCIAL]
    if social_items:
        lines.append("## Semantic Read")
        lines.append("")
        lines.append(
            "Social evidence is useful for repeated claims, objections, sentiment, "
            "and alternatives. It is not validation by itself."
        )
        lines.append("")
        themes = Counter(theme for item in social_items for theme in item.themes)
        if themes:
            lines.append(_counter_line("Repeated themes", themes))
            lines.append("")

    if SourceClass.DIRECT.value not in source_counts:
        lines.append("## Gaps")
        lines.append("")
        lines.append(
            "- No direct source evidence is present; "
            "avoid recommendations from this brief alone."
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _counter_line(label: str, counter: Counter[str]) -> str:
    values = ", ".join(f"{key}={count}" for key, count in sorted(counter.items()))
    return f"- {label}: {values or 'none'}"


def _date_label(item: NormalizedEvidenceItem) -> str:
    if item.published_at is None:
        return "(undated)"
    return f"({item.published_at.isoformat()[:10]})"


def _sort_key(item: NormalizedEvidenceItem) -> tuple[str, str]:
    published = item.published_at.isoformat() if item.published_at else ""
    return (published, item.title)
