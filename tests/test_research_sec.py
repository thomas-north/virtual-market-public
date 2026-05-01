from datetime import date
from unittest.mock import Mock, patch

from vmarket.research.schema import EvidenceRole, SourceClass
from vmarket.research.sec import (
    filings_to_evidence,
    normalize_cik,
    recent_filings_from_submissions,
)


def test_normalize_cik_pads_to_ten_digits():
    assert normalize_cik("1326801") == "0001326801"


def test_recent_filings_from_submissions_filters_by_date():
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-26-001", "0001-26-002"],
                "filingDate": ["2026-04-25", "2026-03-01"],
                "reportDate": ["2026-03-31", "2026-02-01"],
                "form": ["10-Q", "8-K"],
                "primaryDocument": ["meta-20260331.htm", "old.htm"],
                "primaryDocDescription": ["Quarterly report", "Old report"],
            }
        }
    }

    filings = recent_filings_from_submissions(
        payload,
        cik="1326801",
        days=30,
        as_of=date(2026, 4, 26),
    )

    assert len(filings) == 1
    assert filings[0].form == "10-Q"
    assert filings[0].url.endswith("/1326801/000126001/meta-20260331.htm")


def test_filings_to_evidence_uses_direct_validation():
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001-26-001"],
                "filingDate": ["2026-04-25"],
                "reportDate": ["2026-03-31"],
                "form": ["10-Q"],
                "primaryDocument": ["meta-20260331.htm"],
                "primaryDocDescription": ["Quarterly report"],
            }
        }
    }
    filings = recent_filings_from_submissions(payload, cik="1326801", as_of=date(2026, 4, 26))

    items = filings_to_evidence(filings, symbol="META.US", company_name="Meta Platforms")

    assert items[0].source_class == SourceClass.DIRECT
    assert items[0].evidence_role == EvidenceRole.VALIDATION
    assert items[0].symbols == ["META.US"]
    assert items[0].companies == ["Meta Platforms"]


def test_fetch_company_submissions_uses_sec_user_agent():
    from vmarket.research.sec import fetch_company_submissions

    response = Mock()
    response.json.return_value = {"name": "Meta"}
    response.raise_for_status.return_value = None

    with patch("vmarket.research.sec.requests.get", return_value=response) as get:
        result = fetch_company_submissions("1326801", user_agent="VirtualMarket test@example.com")

    assert result == {"name": "Meta"}
    assert "0001326801.json" in get.call_args.args[0]
    assert get.call_args.kwargs["headers"]["User-Agent"] == "VirtualMarket test@example.com"

