from datetime import datetime

from vmarket.research.schema import EvidenceRole, NormalizedEvidenceItem, SourceClass
from vmarket.research.store import (
    evidence_path,
    read_evidence_items,
    read_symbol_evidence,
    stable_dedupe_key,
    write_evidence_items,
)


def _item(title: str, key: str) -> NormalizedEvidenceItem:
    return NormalizedEvidenceItem(
        source_class=SourceClass.SOCIAL,
        evidence_role=EvidenceRole.SENTIMENT,
        source_name="Reddit",
        source_type="reddit_post",
        collected_at=datetime(2026, 4, 26, 12, 0, 0),
        title=title,
        symbols=["META.US"],
        dedupe_key=key,
    )


def test_evidence_path_groups_by_symbol_and_date(tmp_path):
    path = evidence_path("meta.us", root=tmp_path)

    assert path.parent.name == "META.US"
    assert path.suffix == ".jsonl"


def test_write_and_read_evidence_items(tmp_path):
    path = evidence_path("META.US", root=tmp_path)
    write_evidence_items(path, [_item("A", "k1")])

    items = read_evidence_items(path)

    assert len(items) == 1
    assert items[0].title == "A"


def test_read_symbol_evidence_dedupes_across_files(tmp_path):
    path1 = tmp_path / "normalized" / "META.US" / "2026-04-26.jsonl"
    path2 = tmp_path / "normalized" / "META.US" / "2026-04-25.jsonl"
    write_evidence_items(path1, [_item("A", "k1")])
    write_evidence_items(path2, [_item("A older", "k1"), _item("B", "k2")])

    items = read_symbol_evidence("META.US", root=tmp_path)

    assert [item.dedupe_key for item in items] == ["k1", "k2"]


def test_stable_dedupe_key_is_stable():
    assert stable_dedupe_key("Reddit", "META") == stable_dedupe_key("Reddit", "META")

