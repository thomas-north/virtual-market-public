from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.portfolio import Portfolio


def get_default(session: Session) -> Portfolio | None:
    return session.scalar(select(Portfolio).where(Portfolio.name == "Default"))


def get_or_create_default(session: Session, base_currency: str = "GBP") -> Portfolio:
    portfolio = get_default(session)
    if portfolio is None:
        portfolio = Portfolio(name="Default", base_currency=base_currency)
        session.add(portfolio)
        session.flush()
    return portfolio
