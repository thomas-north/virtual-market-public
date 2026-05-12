from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vmarket.db import Base


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    migration_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
