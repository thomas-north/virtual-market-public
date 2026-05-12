from __future__ import annotations

import sqlite3

from sqlalchemy import create_engine

import vmarket.models  # noqa: F401
from vmarket.db import Base, init_db
from vmarket.migrations import MIGRATIONS


def test_init_db_applies_schema_migrations_to_existing_database(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()

    init_db(db_path)

    with sqlite3.connect(db_path) as connection:
        migration_rows = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        job_run_indexes = connection.execute("PRAGMA index_list('job_runs')").fetchall()
        price_indexes = connection.execute("PRAGMA index_list('price_bars')").fetchall()
        portfolio_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('portfolios')").fetchall()
        }
        trade_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('trades')").fetchall()
        }

    assert [row[0] for row in migration_rows] == [
        migration.migration_id for migration in MIGRATIONS
    ]
    assert any(index[1] == "ix_job_runs_lookup" for index in job_run_indexes)
    assert any(index[1] == "ix_price_bars_instrument_date" for index in price_indexes)
    assert {"benchmark_symbol", "drift_targets_json"}.issubset(portfolio_columns)
    assert {"provenance_kind", "provenance_confidence", "provenance_note"}.issubset(trade_columns)


def test_init_db_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "repeatable.sqlite"

    init_db(db_path)
    init_db(db_path)

    with sqlite3.connect(db_path) as connection:
        migration_rows = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()

    assert [row[0] for row in migration_rows] == [
        migration.migration_id for migration in MIGRATIONS
    ]
