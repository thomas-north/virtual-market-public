from __future__ import annotations

from pathlib import Path

import typer

from vmarket.cli.common import abort, console, success
from vmarket.db import get_session, init_db
from vmarket.onboarding import (
    confirm_import_draft,
    create_import_draft,
    discard_import_draft,
    get_import_draft,
    list_import_drafts,
    parse_csv_rows,
    parse_pasted_rows,
)

import_app = typer.Typer(help="Import portfolio and watchlist data through reviewable drafts.")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        abort(str(exc))


def _print_draft(draft) -> None:
    console.print(f"[bold]Draft #{draft.id}[/bold] {draft.kind} from {draft.source_kind}")
    console.print(
        f"Status: {draft.status} · rows: {draft.row_count} · "
        f"warnings: {draft.warning_count}"
    )
    if draft.stored_path:
        console.print(f"Stored path: {draft.stored_path}")
    for row in draft.rows:
        warning_text = f" [yellow]({'; '.join(row.warnings)})[/yellow]" if row.warnings else ""
        quantity_text = row.quantity if row.quantity is not None else "snapshot"
        value_text = f" value={row.current_value}" if row.current_value is not None else ""
        console.print(
            f"- {row.symbol or '<missing symbol>'} "
            f"{quantity_text} {row.currency or ''} {row.name or ''}{value_text}"
            f"{warning_text}"
        )


@import_app.command("portfolio")
def import_portfolio(
    csv_path: Path | None = typer.Option(None, "--csv", help="CSV file to import."),
    paste_path: Path | None = typer.Option(
        None,
        "--paste",
        help="Plain-text paste file to import.",
    ),
) -> None:
    """Create a pending portfolio import draft."""
    if bool(csv_path) == bool(paste_path):
        abort("Provide exactly one of --csv or --paste.")
    source_kind = "csv" if csv_path else "paste"
    path = csv_path or paste_path
    assert path is not None
    rows = (
        parse_csv_rows(_read_text(path), "portfolio")
        if csv_path
        else parse_pasted_rows(_read_text(path), "portfolio")
    )
    init_db()
    with get_session() as session:
        draft = create_import_draft(
            session,
            kind="portfolio",
            source_kind=source_kind,
            rows=rows,
            original_filename=path.name,
            stored_path=str(path),
        )
        session.commit()
    _print_draft(draft)
    success(
        "Review with `vmarket import drafts`, then confirm with "
        f"`vmarket import confirm {draft.id}`."
    )


@import_app.command("watchlist")
def import_watchlist(
    csv_path: Path = typer.Option(..., "--csv", help="CSV file to import."),
) -> None:
    """Create a pending watchlist import draft."""
    rows = parse_csv_rows(_read_text(csv_path), "watchlist")
    init_db()
    with get_session() as session:
        draft = create_import_draft(
            session,
            kind="watchlist",
            source_kind="csv",
            rows=rows,
            original_filename=csv_path.name,
            stored_path=str(csv_path),
        )
        session.commit()
    _print_draft(draft)
    success(
        "Review with `vmarket import drafts`, then confirm with "
        f"`vmarket import confirm {draft.id}`."
    )


@import_app.command("drafts")
def import_drafts() -> None:
    """List import drafts."""
    init_db()
    with get_session() as session:
        drafts = list_import_drafts(session)
    if not drafts:
        console.print("No import drafts yet.")
        return
    for draft in drafts:
        _print_draft(draft)


@import_app.command("show")
def import_show(draft_id: int = typer.Argument(..., help="Import draft id.")) -> None:
    """Show one import draft."""
    init_db()
    with get_session() as session:
        draft = get_import_draft(session, draft_id)
    if draft is None:
        abort(f"Unknown import draft id: {draft_id}")
    _print_draft(draft)


@import_app.command("confirm")
def import_confirm(draft_id: int = typer.Argument(..., help="Import draft id.")) -> None:
    """Confirm a pending import draft and mutate the simulated portfolio/watchlist."""
    init_db()
    with get_session() as session:
        try:
            draft = confirm_import_draft(session, draft_id)
            session.commit()
        except ValueError as exc:
            abort(str(exc))
    success(f"Confirmed import draft #{draft.id}.")


@import_app.command("discard")
def import_discard(draft_id: int = typer.Argument(..., help="Import draft id.")) -> None:
    """Discard a pending import draft without side effects."""
    init_db()
    with get_session() as session:
        try:
            draft = discard_import_draft(session, draft_id)
            session.commit()
        except ValueError as exc:
            abort(str(exc))
    success(f"Discarded import draft #{draft.id}.")
