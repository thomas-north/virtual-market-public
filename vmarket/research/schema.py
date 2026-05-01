from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SourceClass(StrEnum):
    DIRECT = "direct"
    CLASS_A = "class_a"
    CORROBORATING_JOURNALISM = "corroborating_journalism"
    SOCIAL = "social"


class EvidenceRole(StrEnum):
    VALIDATION = "validation"
    OPPORTUNITY = "opportunity"
    CORROBORATION = "corroboration"
    DISCOVERY = "discovery"
    SENTIMENT = "sentiment"


class NormalizedEvidenceItem(BaseModel):
    source_class: SourceClass
    evidence_role: EvidenceRole
    source_name: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    published_at: datetime | date | None = None
    collected_at: datetime
    canonical_url: HttpUrl | None = None
    title: str = Field(min_length=1)
    text_excerpt: str = Field(default="", max_length=4000)
    symbols: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    is_portfolio_relevant: bool = False
    is_watchlist_relevant: bool = False
    dedupe_key: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("symbols", "companies", "themes", mode="before")
    @classmethod
    def _dedupe_string_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        seen: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in seen:
                seen.append(text)
        return seen


def default_role_for_source_class(source_class: SourceClass) -> EvidenceRole:
    if source_class == SourceClass.DIRECT:
        return EvidenceRole.VALIDATION
    if source_class == SourceClass.CLASS_A:
        return EvidenceRole.OPPORTUNITY
    if source_class == SourceClass.CORROBORATING_JOURNALISM:
        return EvidenceRole.CORROBORATION
    return EvidenceRole.DISCOVERY

