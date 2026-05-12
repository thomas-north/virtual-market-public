from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class MigrationStep:
    sql: str
    table: str | None = None
    column: str | None = None


@dataclass(frozen=True)
class Migration:
    migration_id: str
    steps: tuple[MigrationStep, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        migration_id="20260510_01_add_job_run_lookup_index",
        steps=(
            MigrationStep(
                sql="CREATE INDEX IF NOT EXISTS ix_job_runs_lookup "
                "ON job_runs (job_name, status, finished_at DESC)",
            ),
        ),
    ),
    Migration(
        migration_id="20260510_02_add_price_bar_latest_index",
        steps=(
            MigrationStep(
                sql="CREATE INDEX IF NOT EXISTS ix_price_bars_instrument_date "
                "ON price_bars (instrument_id, date DESC)",
            ),
        ),
    ),
    Migration(
        migration_id="20260510_03_add_portfolio_state_columns",
        steps=(
            MigrationStep(
                sql="ALTER TABLE portfolios ADD COLUMN benchmark_symbol VARCHAR(32)",
                table="portfolios",
                column="benchmark_symbol",
            ),
            MigrationStep(
                sql=(
                    "ALTER TABLE portfolios ADD COLUMN drift_targets_json TEXT "
                    "NOT NULL DEFAULT '{}'"
                ),
                table="portfolios",
                column="drift_targets_json",
            ),
        ),
    ),
    Migration(
        migration_id="20260510_04_add_trade_provenance_columns",
        steps=(
            MigrationStep(
                sql="ALTER TABLE trades ADD COLUMN provenance_kind VARCHAR(32)",
                table="trades",
                column="provenance_kind",
            ),
            MigrationStep(
                sql="ALTER TABLE trades ADD COLUMN provenance_confidence NUMERIC(5, 4)",
                table="trades",
                column="provenance_confidence",
            ),
            MigrationStep(
                sql="ALTER TABLE trades ADD COLUMN provenance_note VARCHAR(512)",
                table="trades",
                column="provenance_note",
            ),
        ),
    ),
)


def _column_exists(connection, table: str, column: str) -> bool:
    rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def run_migrations(engine: Engine) -> list[str]:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        applied = {
            row[0]
            for row in connection.execute(
                text("SELECT migration_id FROM schema_migrations")
            ).fetchall()
        }

        executed: list[str] = []
        for migration in MIGRATIONS:
            if migration.migration_id in applied:
                continue
            for step in migration.steps:
                if (
                    step.table
                    and step.column
                    and _column_exists(connection, step.table, step.column)
                ):
                    continue
                connection.execute(text(step.sql))
            connection.execute(
                text(
                    """
                    INSERT INTO schema_migrations (migration_id, applied_at)
                    VALUES (:migration_id, CURRENT_TIMESTAMP)
                    """
                ),
                {"migration_id": migration.migration_id},
            )
            executed.append(migration.migration_id)
    return executed
