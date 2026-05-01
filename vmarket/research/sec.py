from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import requests

from vmarket.config import get_sec_user_agent
from vmarket.research.schema import EvidenceRole, NormalizedEvidenceItem, SourceClass
from vmarket.research.store import stable_dedupe_key

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"


@dataclass(frozen=True)
class SecFiling:
    accession_number: str
    filing_date: date
    report_date: date | None
    form: str
    primary_document: str
    description: str
    url: str


def normalize_cik(cik: str | int) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits:
        raise ValueError("CIK must contain digits")
    return digits.zfill(10)


def fetch_company_submissions(cik: str | int, user_agent: str | None = None) -> dict[str, Any]:
    normalized_cik = normalize_cik(cik)
    response = requests.get(
        SEC_SUBMISSIONS_URL.format(cik=normalized_cik),
        headers={
            "User-Agent": user_agent or get_sec_user_agent(),
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def recent_filings_from_submissions(
    payload: dict[str, Any],
    cik: str | int,
    days: int = 30,
    as_of: date | None = None,
) -> list[SecFiling]:
    cutoff = (as_of or date.today()) - timedelta(days=days - 1)
    recent = payload.get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", []) or []
    filing_dates = recent.get("filingDate", []) or []
    report_dates = recent.get("reportDate", []) or []
    forms = recent.get("form", []) or []
    primary_documents = recent.get("primaryDocument", []) or []
    descriptions = recent.get("primaryDocDescription", []) or []

    filings: list[SecFiling] = []
    normalized_cik = str(int(normalize_cik(cik)))
    for idx, accession in enumerate(accession_numbers):
        filing_date = _parse_date(_get(filing_dates, idx))
        if filing_date is None or filing_date < cutoff:
            continue
        primary_doc = _get(primary_documents, idx)
        accession_clean = str(accession).replace("-", "")
        filings.append(
            SecFiling(
                accession_number=str(accession),
                filing_date=filing_date,
                report_date=_parse_date(_get(report_dates, idx)),
                form=str(_get(forms, idx) or ""),
                primary_document=str(primary_doc or ""),
                description=str(_get(descriptions, idx) or ""),
                url=SEC_ARCHIVE_URL.format(
                    cik=normalized_cik,
                    accession=accession_clean,
                    primary_doc=primary_doc or "",
                ),
            )
        )
    return filings


def filings_to_evidence(
    filings: list[SecFiling],
    *,
    symbol: str,
    company_name: str | None = None,
    collected_at: datetime | None = None,
) -> list[NormalizedEvidenceItem]:
    collected_at = collected_at or datetime.now().astimezone()
    company = company_name or symbol.upper()
    items: list[NormalizedEvidenceItem] = []
    for filing in filings:
        title = f"{company}: SEC {filing.form} filed {filing.filing_date.isoformat()}"
        if filing.description:
            title = f"{title} - {filing.description}"
        items.append(
            NormalizedEvidenceItem(
                source_class=SourceClass.DIRECT,
                evidence_role=EvidenceRole.VALIDATION,
                source_name="SEC EDGAR",
                source_type="sec_filing",
                published_at=filing.filing_date,
                collected_at=collected_at,
                canonical_url=filing.url,
                title=title,
                text_excerpt=_filing_excerpt(filing),
                symbols=[symbol.upper()],
                companies=[company],
                is_portfolio_relevant=True,
                dedupe_key=stable_dedupe_key("sec", symbol.upper(), filing.accession_number),
                metadata={
                    "form": filing.form,
                    "accession_number": filing.accession_number,
                    "report_date": filing.report_date.isoformat() if filing.report_date else None,
                },
            )
        )
    return items


def collect_recent_sec_evidence(
    *,
    symbol: str,
    cik: str | int,
    company_name: str | None = None,
    days: int = 30,
    as_of: date | None = None,
    user_agent: str | None = None,
) -> list[NormalizedEvidenceItem]:
    payload = fetch_company_submissions(cik, user_agent=user_agent)
    filings = recent_filings_from_submissions(payload, cik, days=days, as_of=as_of)
    return filings_to_evidence(filings, symbol=symbol, company_name=company_name)


def _get(values: list[Any], idx: int) -> Any:
    return values[idx] if idx < len(values) else None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _filing_excerpt(filing: SecFiling) -> str:
    parts = [f"Form {filing.form}", f"filed {filing.filing_date.isoformat()}"]
    if filing.report_date:
        parts.append(f"report date {filing.report_date.isoformat()}")
    if filing.description:
        parts.append(filing.description)
    return "; ".join(parts)

