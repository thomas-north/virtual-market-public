from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentDTO:
    symbol: str
    name: str | None
    currency: str | None
    asset_type: str | None
    exchange: str | None
    provider: str
