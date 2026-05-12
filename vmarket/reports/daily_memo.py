from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from vmarket.reports.io import write_report_file
from vmarket.services.memo_service import generate_daily_memo


def write_or_print(
    session: Session,
    output: Path | None = None,
    memo_date: date | None = None,
) -> str:
    content = generate_daily_memo(session, memo_date=memo_date)
    if output:
        write_report_file(output, content)
    return content
