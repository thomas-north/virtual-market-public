from sqlalchemy.orm import Session

from vmarket.dto.portfolio import PositionDTO
from vmarket.services.valuation_service import compute_positions


def get_snapshot(session: Session, base_currency: str | None = None) -> list[PositionDTO]:
    return compute_positions(session, base_currency=base_currency)
