from datetime import datetime

from vmarket.research.brief import render_evidence_brief
from vmarket.research.schema import EvidenceRole, NormalizedEvidenceItem, SourceClass


def test_render_evidence_brief_groups_social_items():
    item = NormalizedEvidenceItem(
        source_class=SourceClass.SOCIAL,
        evidence_role=EvidenceRole.SENTIMENT,
        source_name="Reddit",
        source_type="reddit_post",
        collected_at=datetime(2026, 4, 26, 12, 0, 0),
        title="Why investors are debating META",
        symbols=["META.US"],
        themes=["AI capex"],
        dedupe_key="k1",
    )

    brief = render_evidence_brief("META.US", [item])

    assert "# META.US - Research Evidence Brief" in brief
    assert "## social" in brief
    assert "AI capex=1" in brief
    assert "No direct source evidence" in brief

