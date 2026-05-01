from datetime import datetime

from vmarket.research.schema import (
    EvidenceRole,
    NormalizedEvidenceItem,
    SourceClass,
    default_role_for_source_class,
)


def test_normalized_evidence_dedupes_lists():
    item = NormalizedEvidenceItem(
        source_class=SourceClass.SOCIAL,
        evidence_role=EvidenceRole.SENTIMENT,
        source_name="Reddit",
        source_type="reddit_post",
        collected_at=datetime(2026, 4, 26, 12, 0, 0),
        title="Why investors are debating META",
        symbols=["META.US", "META.US", "meta"],
        companies=["Meta", "Meta"],
        dedupe_key="abc123",
    )

    assert item.symbols == ["META.US", "meta"]
    assert item.companies == ["Meta"]


def test_default_role_for_source_class():
    assert default_role_for_source_class(SourceClass.DIRECT) == EvidenceRole.VALIDATION
    assert default_role_for_source_class(SourceClass.SOCIAL) == EvidenceRole.DISCOVERY

