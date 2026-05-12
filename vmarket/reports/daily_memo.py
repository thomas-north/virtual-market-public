from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from vmarket.services.memo_service import generate_daily_memo


def write_or_print(
    session: Session,
    output: Path | None = None,
    memo_date: date | None = None,
) -> str:
    content = generate_daily_memo(session, memo_date=memo_date)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    return content
