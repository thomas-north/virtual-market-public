from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.job_run import JobRun


def start(session: Session, job_name: str) -> JobRun:
    run = JobRun(job_name=job_name, started_at=datetime.now(UTC))
    session.add(run)
    session.flush()
    return run


def finish(session: Session, run: JobRun, status: str, message: str | None = None) -> None:
    run.finished_at = datetime.now(UTC)
    run.status = status
    run.message = message
    session.flush()


def get_latest(session: Session, job_name: str) -> JobRun | None:
    return session.scalar(
        select(JobRun)
        .where(JobRun.job_name == job_name, JobRun.status == "success")
        .order_by(JobRun.finished_at.desc())
        .limit(1)
    )
