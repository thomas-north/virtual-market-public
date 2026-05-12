from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.consultant_profile import ConsultantProfileRecord


def get_default(session: Session) -> ConsultantProfileRecord | None:
    return session.scalar(
        select(ConsultantProfileRecord).where(ConsultantProfileRecord.profile_name == "default")
    )


def get_or_create_default(session: Session) -> ConsultantProfileRecord:
    record = get_default(session)
    if record is None:
        record = ConsultantProfileRecord(profile_name="default")
        session.add(record)
        session.flush()
    return record


def delete_default(session: Session) -> None:
    record = get_default(session)
    if record is not None:
        session.delete(record)
        session.flush()
