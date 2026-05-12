from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from shutil import copyfileobj

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from vmarket.consult import diagnose_portfolio, get_profile, locate_factsheet, save_profile
from vmarket.consult.models import ConsultantProfile, PortfolioConsultRequest, PortfolioDiagnosis
from vmarket.db import get_session, init_db
from vmarket.onboarding import (
    confirm_import_draft,
    create_import_draft,
    discard_import_draft,
    get_import_draft,
    get_onboarding_state,
    list_import_drafts,
    parse_csv_rows,
    parse_pasted_rows,
)
from vmarket.onboarding.models import ImportDraftRow
from vmarket.onboarding.service import ensure_user_data_dirs
from vmarket.reports.overview import build_overview_payload, render_overview_html
from vmarket.services.data_quality import build_data_quality_report
from vmarket.services.staged_action_service import (
    confirm_action,
    discard_action,
    list_actions,
    stage_action,
)
from vmarket.services.watchlist_service import build_watchlist_rows
from vmarket.services.workspace_service import (
    create_journal_entry,
    get_workflow_session,
    list_journal_entries,
    record_workflow_session,
)
from vmarket.themes import analyze_theme
from vmarket.themes.models import ThemeAnalysisRequest, ThemeAnalysisResult
from vmarket.web.context import (
    build_agent_context_bundle,
    build_cockpit_overview,
    build_prompt_packet,
    build_research_workspace,
    build_workflows_page,
    note_context_export,
    render_prompt_markdown,
)

WEB_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_ROOT / "templates"))


def _split_companies(raw: str) -> list[str]:
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _decimal_or_none(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _theme_request_for_agent(workflow: str, theme: str | None) -> ThemeAnalysisRequest | None:
    if workflow != "thematic-analysis" or not theme:
        return None
    return ThemeAnalysisRequest(theme=theme)


def _consult_request_for_agent(workflow: str) -> PortfolioConsultRequest | None:
    if workflow != "portfolio-consultation":
        return None
    return PortfolioConsultRequest()


def _csv_list(raw: str | None) -> list[str]:
    return [part.strip() for part in str(raw or "").replace("\n", ",").split(",") if part.strip()]


def _consult_request_from_form(form) -> PortfolioConsultRequest:
    exclusions = [
        item.strip()
        for item in str(form.get("exclusions") or "").replace("\n", ",").split(",")
        if item.strip()
    ]
    preferences = [
        item.strip()
        for item in str(form.get("preferences") or "").replace("\n", ",").split(",")
        if item.strip()
    ]
    product_preferences = [
        item.strip()
        for item in str(form.get("product_preferences") or "").replace("\n", ",").split(",")
        if item.strip()
    ]
    risk_raw = str(form.get("risk_score") or "").strip()
    risk_score = int(risk_raw) if risk_raw else None
    return PortfolioConsultRequest(
        risk_score=risk_score,
        exclusions=exclusions,
        preferences=preferences,
        investment_horizon=str(form.get("investment_horizon") or "").strip() or None,
        amount=_decimal_or_none(str(form.get("amount") or "")),
        monthly_amount=_decimal_or_none(str(form.get("monthly_amount") or "")),
        income_preference=str(form.get("income_preference") or "").strip() or None,
        product_preferences=product_preferences,
        distribution_preference=str(form.get("distribution_preference") or "").strip() or None,
        country_jurisdiction=str(form.get("country_jurisdiction") or "").strip() or None,
        base_currency=str(form.get("base_currency") or "").strip() or None,
        prefers_uk_listed=True if form.get("prefers_uk_listed") else None,
        prefers_gbp_lines=True if form.get("prefers_gbp_lines") else None,
    )


def _profile_from_form(form) -> ConsultantProfile:
    return ConsultantProfile(
        risk_score=int(str(form.get("risk_score") or "0")) or None,
        exclusions=_csv_list(form.get("exclusions")),
        preference_tags=_csv_list(form.get("preferences")),
        product_preferences=_csv_list(form.get("product_preferences")),
        income_preference=str(form.get("income_preference") or "").strip() or None,
        distribution_preference=str(form.get("distribution_preference") or "").strip() or None,
        country_jurisdiction=str(form.get("country_jurisdiction") or "UK").strip() or "UK",
        base_currency=str(form.get("base_currency") or "GBP").strip().upper() or "GBP",
        prefers_uk_listed=True if form.get("prefers_uk_listed") else False,
        prefers_gbp_lines=True if form.get("prefers_gbp_lines") else False,
    )


def _manual_portfolio_row(form) -> ImportDraftRow:
    return ImportDraftRow(
        symbol=str(form.get("symbol") or "").strip().upper(),
        name=str(form.get("name") or "").strip() or None,
        quantity=_decimal_or_none(str(form.get("quantity") or "")),
        average_cost=_decimal_or_none(str(form.get("average_cost") or "")),
        cost_basis=_decimal_or_none(str(form.get("cost_basis") or "")),
        current_value=_decimal_or_none(str(form.get("current_value") or "")),
        gain_amount=_decimal_or_none(str(form.get("gain_amount") or "")),
        gain_percent=_decimal_or_none(str(form.get("gain_percent") or "")),
        currency=str(form.get("currency") or "").strip().upper() or None,
        asset_type=str(form.get("asset_type") or "").strip().lower() or None,
        notes=str(form.get("notes") or "").strip() or None,
        current_price=_decimal_or_none(str(form.get("current_price") or "")),
    )


def _with_basic_row_warnings(row: ImportDraftRow, *, portfolio: bool) -> ImportDraftRow:
    if not row.symbol:
        row.warnings.append("Missing symbol")
    if portfolio:
        from vmarket.onboarding.service import _warnings_for_row

        row.warnings = _warnings_for_row(row, "portfolio")
        return row
    if not row.currency:
        row.warnings.append("Missing currency")
    return row


def _payload_from_form(kind: str, form) -> dict[str, str]:
    workflow_session_id = str(form.get("workflow_session_id") or "").strip()
    workflow = str(form.get("workflow") or "").strip()
    redirect_to = str(form.get("redirect_to") or "").strip()
    if kind in {"buy", "sell"}:
        payload = {
            "symbol": str(form.get("symbol") or "").strip(),
            "quantity": str(form.get("quantity") or "").strip(),
            "price": str(form.get("price") or "").strip(),
            "currency": str(form.get("currency") or "").strip(),
            "notes": str(form.get("notes") or "").strip(),
        }
        if workflow_session_id:
            payload["workflow_session_id"] = workflow_session_id
        if workflow:
            payload["workflow"] = workflow
        if redirect_to:
            payload["redirect_to"] = redirect_to
        return payload
    if kind == "watch_add":
        payload = {
            "symbol": str(form.get("symbol") or "").strip(),
            "name": str(form.get("name") or "").strip(),
            "currency": str(form.get("currency") or "").strip(),
            "asset_type": str(form.get("asset_type") or "").strip(),
        }
        if workflow_session_id:
            payload["workflow_session_id"] = workflow_session_id
        if workflow:
            payload["workflow"] = workflow
        if redirect_to:
            payload["redirect_to"] = redirect_to
        return payload
    if kind == "watch_remove":
        payload = {"symbol": str(form.get("symbol") or "").strip()}
        if workflow_session_id:
            payload["workflow_session_id"] = workflow_session_id
        if workflow:
            payload["workflow"] = workflow
        if redirect_to:
            payload["redirect_to"] = redirect_to
        return payload
    payload = {
        "title": str(form.get("title") or "").strip(),
        "body": str(form.get("body") or "").strip(),
        "section": str(form.get("section") or "questions").strip(),
    }
    if workflow_session_id:
        payload["workflow_session_id"] = workflow_session_id
    if workflow:
        payload["workflow"] = workflow
    if redirect_to:
        payload["redirect_to"] = redirect_to
    return payload


def _theme_request_from_form(form) -> ThemeAnalysisRequest:
    return ThemeAnalysisRequest(
        theme=str(form.get("theme") or ""),
        amount=_decimal_or_none(str(form.get("amount") or "")),
        allocation_currency=str(form.get("allocation_currency") or "") or None,
        investor_country=str(form.get("investor_country") or "GB"),
        preferred_companies=_split_companies(str(form.get("preferred_companies") or "")),
        volatility_tolerance=str(form.get("volatility_tolerance") or "medium"),
        time_horizon=str(form.get("time_horizon") or "long"),
        target_role=str(form.get("target_role") or "auto"),
        implementation_scope=str(form.get("implementation_scope") or "both"),
    )


def _theme_form_values(theme_request: ThemeAnalysisRequest) -> dict[str, object]:
    return {
        "theme": theme_request.theme,
        "amount": str(theme_request.amount or ""),
        "allocation_currency": theme_request.allocation_currency or "",
        "investor_country": theme_request.investor_country,
        "preferred_companies": ", ".join(theme_request.preferred_companies),
        "volatility_tolerance": theme_request.volatility_tolerance,
        "time_horizon": theme_request.time_horizon,
        "target_role": theme_request.target_role,
        "implementation_scope": theme_request.implementation_scope,
    }


def _default_theme_form_values() -> dict[str, object]:
    return {
        "investor_country": "GB",
        "volatility_tolerance": "medium",
        "time_horizon": "long",
        "target_role": "auto",
        "implementation_scope": "both",
    }


def create_app(db_path: Path | None = None) -> FastAPI:
    init_db(db_path)
    app = FastAPI(title="Virtual Market Cockpit")
    app.state.db_path = db_path
    app.mount("/static", StaticFiles(directory=str(WEB_ROOT / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            overview = build_cockpit_overview(session)
            workflows_payload = build_workflows_page(session)
            onboarding_state = get_onboarding_state(session, db_path=app.state.db_path)
        return TEMPLATES.TemplateResponse(
            request,
            "dashboard.html",
            {
                "overview": overview,
                "workflows_payload": workflows_payload,
                "onboarding_state": onboarding_state,
                "page_title": "Agent Cockpit",
                "active_page": "dashboard",
            },
        )

    @app.get("/onboarding", response_class=HTMLResponse)
    async def onboarding_page(request: Request) -> HTMLResponse:
        ensure_user_data_dirs()
        with get_session(app.state.db_path) as session:
            state = get_onboarding_state(session, db_path=app.state.db_path)
            saved_profile = get_profile(session)
            drafts = list_import_drafts(session)
        return TEMPLATES.TemplateResponse(
            request,
            "onboarding.html",
            {
                "page_title": "Onboarding",
                "active_page": "onboarding",
                "state": state,
                "saved_profile": saved_profile,
                "drafts": drafts,
            },
        )

    @app.post("/onboarding/profile")
    async def onboarding_profile_route(request: Request) -> RedirectResponse:
        form = await request.form()
        profile = _profile_from_form(form)
        with get_session(app.state.db_path) as session:
            save_profile(session, profile)
            session.commit()
        return RedirectResponse("/onboarding", status_code=303)

    @app.post("/imports/portfolio/manual")
    async def import_portfolio_manual_route(request: Request) -> RedirectResponse:
        form = await request.form()
        row = _with_basic_row_warnings(_manual_portfolio_row(form), portfolio=True)
        with get_session(app.state.db_path) as session:
            draft = create_import_draft(
                session,
                kind="portfolio",
                source_kind="manual",
                rows=[row],
                notes="Manual cockpit portfolio import",
            )
            session.commit()
        return RedirectResponse(f"/imports/{draft.id}", status_code=303)

    @app.post("/imports/portfolio/csv")
    async def import_portfolio_csv_route(request: Request) -> RedirectResponse:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "file"):
            return RedirectResponse("/onboarding", status_code=303)
        content = upload.file.read().decode("utf-8")  # type: ignore[attr-defined]
        rows = parse_csv_rows(content, "portfolio")
        with get_session(app.state.db_path) as session:
            draft = create_import_draft(
                session,
                kind="portfolio",
                source_kind="csv",
                rows=rows,
                original_filename=getattr(upload, "filename", None),
            )
            session.commit()
        return RedirectResponse(f"/imports/{draft.id}", status_code=303)

    @app.post("/imports/portfolio/paste")
    async def import_portfolio_paste_route(request: Request) -> RedirectResponse:
        form = await request.form()
        rows = parse_pasted_rows(str(form.get("content") or ""), "portfolio")
        with get_session(app.state.db_path) as session:
            draft = create_import_draft(
                session,
                kind="portfolio",
                source_kind="paste",
                rows=rows,
                notes="Pasted cockpit portfolio import",
            )
            session.commit()
        return RedirectResponse(f"/imports/{draft.id}", status_code=303)

    @app.post("/imports/watchlist/csv")
    async def import_watchlist_csv_route(request: Request) -> RedirectResponse:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "file"):
            return RedirectResponse("/onboarding", status_code=303)
        content = upload.file.read().decode("utf-8")  # type: ignore[attr-defined]
        rows = parse_csv_rows(content, "watchlist")
        with get_session(app.state.db_path) as session:
            draft = create_import_draft(
                session,
                kind="watchlist",
                source_kind="csv",
                rows=rows,
                original_filename=getattr(upload, "filename", None),
            )
            session.commit()
        return RedirectResponse(f"/imports/{draft.id}", status_code=303)

    @app.post("/imports/screenshot")
    async def import_screenshot_route(request: Request) -> RedirectResponse:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "file"):
            return RedirectResponse("/onboarding", status_code=303)
        user_data = ensure_user_data_dirs()
        filename = Path(getattr(upload, "filename", "portfolio-screenshot.png")).name
        stored = user_data / "screenshots" / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{filename}"
        with stored.open("wb") as handle:
            copyfileobj(upload.file, handle)  # type: ignore[attr-defined]
        with get_session(app.state.db_path) as session:
            draft = create_import_draft(
                session,
                kind="screenshot",
                source_kind="screenshot",
                rows=[],
                original_filename=filename,
                stored_path=str(stored),
                notes=(
                    "Agent-assisted screenshot import. Extract rows into a new "
                    "draft before confirming."
                ),
            )
            session.commit()
        return RedirectResponse(f"/imports/{draft.id}", status_code=303)

    @app.get("/imports/{draft_id}", response_class=HTMLResponse)
    async def import_draft_page(request: Request, draft_id: int) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            draft = get_import_draft(session, draft_id)
        return TEMPLATES.TemplateResponse(
            request,
            "import_draft.html",
            {
                "page_title": "Import Draft",
                "active_page": "onboarding",
                "draft": draft,
            },
        )

    @app.post("/imports/{draft_id}/confirm")
    async def import_draft_confirm_route(draft_id: int) -> RedirectResponse:
        with get_session(app.state.db_path) as session:
            try:
                confirm_import_draft(session, draft_id)
                session.commit()
            except ValueError:
                session.rollback()
                return RedirectResponse(f"/imports/{draft_id}", status_code=303)
        return RedirectResponse("/onboarding", status_code=303)

    @app.post("/imports/{draft_id}/discard")
    async def import_draft_discard_route(draft_id: int) -> RedirectResponse:
        with get_session(app.state.db_path) as session:
            try:
                discard_import_draft(session, draft_id)
                session.commit()
            except ValueError:
                session.rollback()
        return RedirectResponse("/onboarding", status_code=303)

    @app.get("/workflows", response_class=HTMLResponse)
    async def workflows_page(request: Request) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            payload = build_workflows_page(session)
        return TEMPLATES.TemplateResponse(
            request,
            "workflows.html",
            {
                "page_title": "Workflows",
                "active_page": "workflows",
                "payload": payload,
            },
        )

    @app.get("/portfolio", response_class=HTMLResponse)
    async def portfolio_page(request: Request, days: int = 30) -> HTMLResponse:
        from vmarket.reports.overview import get_benchmark_symbol
        from vmarket.services.drift_service import compute_allocation_drift

        with get_session(app.state.db_path) as session:
            overview = build_cockpit_overview(session)
            drift_rows = compute_allocation_drift(session)
        return TEMPLATES.TemplateResponse(
            request,
            "portfolio.html",
            {
                "page_title": "Portfolio",
                "active_page": "portfolio",
                "overview": overview,
                "days": days,
                "benchmark_symbol": get_benchmark_symbol(),
                "drift_rows": drift_rows,
            },
        )

    @app.post("/portfolio/targets")
    async def save_targets_route(request: Request) -> RedirectResponse:
        from vmarket.services.drift_service import save_targets

        form = await request.form()
        targets: dict[str, float] = {}
        for key, value in form.multi_items():
            if key.startswith("target_"):
                label = key[len("target_"):]
                try:
                    targets[label] = float(str(value))
                except ValueError:
                    pass
        save_targets(targets)
        return RedirectResponse("/portfolio#drift", status_code=303)

    @app.get("/overview", response_class=HTMLResponse)
    async def overview_page(request: Request, days: int = 30) -> HTMLResponse:
        return RedirectResponse(f"/portfolio?days={days}", status_code=301)

    @app.get("/overview/standalone")
    async def overview_standalone(days: int = 30) -> Response:
        with get_session(app.state.db_path) as session:
            payload = build_overview_payload(session, days=days)
        return Response(
            render_overview_html(payload),
            media_type="text/html",
        )

    @app.get("/watchlist", response_class=HTMLResponse)
    async def watchlist_page(request: Request) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            rows = build_watchlist_rows(session)
        targets_hit = [r for r in rows if r["flag"] in {"buy target hit", "sell target hit"}]
        return TEMPLATES.TemplateResponse(
            request,
            "watchlist.html",
            {
                "page_title": "Watchlist",
                "active_page": "watchlist",
                "rows": rows,
                "targets_hit": targets_hit,
            },
        )

    @app.post("/portfolio/benchmark")
    async def set_benchmark_route(request: Request) -> RedirectResponse:
        from vmarket.reports.overview import set_benchmark_symbol

        form = await request.form()
        symbol = str(form.get("symbol") or "").strip().upper()
        if symbol:
            set_benchmark_symbol(symbol)
        return RedirectResponse("/portfolio", status_code=303)

    @app.post("/portfolio/benchmark/clear")
    async def clear_benchmark_route() -> RedirectResponse:
        from vmarket.reports.overview import clear_benchmark_symbol

        clear_benchmark_symbol()
        return RedirectResponse("/portfolio", status_code=303)

    @app.post("/sync/prices")
    async def sync_prices_route() -> RedirectResponse:
        from vmarket.services.fx_service import sync_fx_rates
        from vmarket.services.market_data_service import sync_prices as run_price_sync

        with get_session(app.state.db_path) as session:
            run_price_sync(session, days=7)
            sync_fx_rates(session, base="GBP", quotes=["USD", "EUR"], days=7)
            session.commit()
        return RedirectResponse("/portfolio", status_code=303)

    @app.get("/memo", response_class=HTMLResponse)
    async def memo_page(request: Request) -> HTMLResponse:
        from vmarket.web.context import _latest_memo_summary

        memo = _latest_memo_summary()
        full_text = Path(memo.path).read_text(encoding="utf-8") if memo.path else None
        return TEMPLATES.TemplateResponse(
            request,
            "memo.html",
            {
                "page_title": "Daily Memo",
                "active_page": "memo",
                "memo": memo,
                "full_text": full_text,
            },
        )

    @app.post("/memo/generate")
    async def memo_generate_route() -> RedirectResponse:
        from datetime import date

        from vmarket.reports.daily_memo import write_or_print
        from vmarket.reports.io import write_report_file

        with get_session(app.state.db_path) as session:
            content = write_or_print(session)
            session.commit()
        output = Path("reports") / f"daily_{date.today()}.md"
        write_report_file(output, content)
        return RedirectResponse("/memo", status_code=303)

    @app.get("/themes", response_class=HTMLResponse)
    async def themes_page(request: Request, session_id: int | None = None) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            overview = build_cockpit_overview(session)
            current_session = get_workflow_session(session, session_id) if session_id else None
            result = None
            form_values = _default_theme_form_values()
            if (
                current_session is not None
                and current_session.workflow == "thematic-analysis"
            ):
                theme_payload = current_session.input_payload.get("theme_request", {})
                result_payload = current_session.output_payload.get("theme_analysis", {})
                reopened_request = ThemeAnalysisRequest.model_validate(theme_payload)
                form_values = _theme_form_values(reopened_request)
                if result_payload:
                    result = ThemeAnalysisResult.model_validate(result_payload)
        return TEMPLATES.TemplateResponse(
            request,
            "themes.html",
            {
                "overview": overview,
                "page_title": "Theme Workspace",
                "active_page": "themes",
                "result": result,
                "form_values": form_values,
                "current_session": current_session,
            },
        )

    @app.get("/consult", response_class=HTMLResponse)
    async def consult_page(
        request: Request,
        factsheet: str | None = None,
        session_id: int | None = None,
    ) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            overview = build_cockpit_overview(session)
            saved_profile = get_profile(session)
            current_session = get_workflow_session(session, session_id) if session_id else None
            diagnosis = diagnose_portfolio(session)
            form_values = {
                "risk_score": saved_profile.risk_score or "",
                "exclusions": ", ".join(saved_profile.exclusions),
                "preferences": ", ".join(saved_profile.preference_tags),
                "investment_horizon": saved_profile.investment_horizon or "",
                "amount": str(saved_profile.amount or ""),
                "monthly_amount": str(saved_profile.monthly_amount or ""),
                "income_preference": saved_profile.income_preference or "",
                "product_preferences": ", ".join(saved_profile.product_preferences),
                "distribution_preference": saved_profile.distribution_preference or "",
                "country_jurisdiction": saved_profile.country_jurisdiction,
                "base_currency": saved_profile.base_currency,
                "prefers_uk_listed": saved_profile.prefers_uk_listed,
                "prefers_gbp_lines": saved_profile.prefers_gbp_lines,
            }
            if (
                current_session is not None
                and current_session.workflow == "portfolio-consultation"
            ):
                consult_payload = current_session.input_payload.get("consult_request", {})
                diagnosis_payload = current_session.output_payload.get("consult_diagnosis", {})
                consult_request = PortfolioConsultRequest.model_validate(consult_payload)
                diagnosis = PortfolioDiagnosis.model_validate(diagnosis_payload)
                form_values = {
                    "risk_score": consult_request.risk_score or "",
                    "exclusions": ", ".join(consult_request.exclusions),
                    "preferences": ", ".join(consult_request.preferences),
                    "investment_horizon": consult_request.investment_horizon or "",
                    "amount": str(consult_request.amount or ""),
                    "monthly_amount": str(consult_request.monthly_amount or ""),
                    "income_preference": consult_request.income_preference or "",
                    "product_preferences": ", ".join(consult_request.product_preferences),
                    "distribution_preference": consult_request.distribution_preference or "",
                    "country_jurisdiction": consult_request.country_jurisdiction or "",
                    "base_currency": consult_request.base_currency or "",
                    "prefers_uk_listed": bool(consult_request.prefers_uk_listed),
                    "prefers_gbp_lines": bool(consult_request.prefers_gbp_lines),
                }
            factsheet_summary = (
                locate_factsheet(factsheet, fetch_source=False) if factsheet else None
            )
        return TEMPLATES.TemplateResponse(
            request,
            "consult.html",
            {
                "overview": overview,
                "page_title": "Portfolio Consultant",
                "active_page": "consult",
                "saved_profile": saved_profile,
                "diagnosis": diagnosis,
                "factsheet_summary": factsheet_summary,
                "form_values": form_values,
                "current_session": current_session,
            },
        )

    @app.post("/consult", response_class=HTMLResponse)
    async def consult_page_post(request: Request) -> HTMLResponse:
        form = await request.form()
        consult_request = _consult_request_from_form(form)
        factsheet_id = str(form.get("factsheet") or "").strip() or None
        with get_session(app.state.db_path) as session:
            overview = build_cockpit_overview(session)
            saved_profile = get_profile(session)
            diagnosis = diagnose_portfolio(session, request=consult_request)
            factsheet_summary = (
                locate_factsheet(factsheet_id, fetch_source=False) if factsheet_id else None
            )
            current_session = record_workflow_session(
                session,
                workflow="portfolio-consultation",
                title="Portfolio consultation",
                summary=(
                    diagnosis.research_ideas[0].summary if diagnosis.research_ideas else None
                ),
                input_payload={"consult_request": consult_request.model_dump(mode="json")},
                output_payload={"consult_diagnosis": diagnosis.model_dump(mode="json")},
                related_symbols=[],
                related_themes=[],
            )
            session.commit()
        return TEMPLATES.TemplateResponse(
            request,
            "consult.html",
            {
                "overview": overview,
                "page_title": "Portfolio Consultant",
                "active_page": "consult",
                "saved_profile": saved_profile,
                "diagnosis": diagnosis,
                "factsheet_summary": factsheet_summary,
                "current_session": current_session,
                "form_values": {
                    "risk_score": consult_request.risk_score or "",
                    "exclusions": ", ".join(consult_request.exclusions),
                    "preferences": ", ".join(consult_request.preferences),
                    "investment_horizon": consult_request.investment_horizon or "",
                    "amount": str(consult_request.amount or ""),
                    "monthly_amount": str(consult_request.monthly_amount or ""),
                    "income_preference": consult_request.income_preference or "",
                    "product_preferences": ", ".join(consult_request.product_preferences),
                    "distribution_preference": consult_request.distribution_preference or "",
                    "country_jurisdiction": consult_request.country_jurisdiction or "",
                    "base_currency": consult_request.base_currency or "",
                    "prefers_uk_listed": bool(consult_request.prefers_uk_listed),
                    "prefers_gbp_lines": bool(consult_request.prefers_gbp_lines),
                    "factsheet": factsheet_id or "",
                },
            },
        )

    @app.post("/themes/analyse", response_class=HTMLResponse)
    async def analyse_theme_route(request: Request) -> HTMLResponse:
        form = await request.form()
        theme_request = _theme_request_from_form(form)
        with get_session(app.state.db_path) as session:
            overview = build_cockpit_overview(session)
            result = analyze_theme(session, theme_request)
            current_session = record_workflow_session(
                session,
                workflow="thematic-analysis",
                title=f"{result.theme_label} analysis",
                summary=result.best_thematic_fit.recommendation.why_this_fits,
                input_payload={"theme_request": theme_request.model_dump(mode="json")},
                output_payload={"theme_analysis": result.model_dump(mode="json")},
                related_symbols=[
                    candidate.listing_symbol
                    for candidate in result.candidates
                    if candidate.listing_symbol
                ],
                related_themes=[result.theme],
            )
            session.commit()
        return TEMPLATES.TemplateResponse(
            request,
            "themes.html",
            {
                "overview": overview,
                "page_title": "Theme Workspace",
                "active_page": "themes",
                "result": result,
                "form_values": _theme_form_values(theme_request),
                "current_session": current_session,
            },
        )

    @app.get("/research", response_class=HTMLResponse)
    async def research_page(
        request: Request,
        symbol: str | None = None,
        session_id: int | None = None,
    ) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            current_session = get_workflow_session(session, session_id) if session_id else None
            if (
                current_session is not None
                and current_session.workflow == "research-follow-up"
                and symbol is None
            ):
                symbol = str(current_session.input_payload.get("symbol") or "") or None
            workspace, brief = build_research_workspace(symbol=symbol)
        return TEMPLATES.TemplateResponse(
            request,
            "research.html",
            {
                "page_title": "Research Workspace",
                "active_page": "research",
                "workspace": workspace,
                "brief": brief,
                "symbol": symbol or "",
                "current_session": current_session,
            },
        )

    @app.post("/research", response_class=HTMLResponse)
    async def research_page_post(request: Request) -> HTMLResponse:
        form = await request.form()
        symbol = str(form.get("symbol") or "").strip().upper()
        with get_session(app.state.db_path) as session:
            workspace, brief = build_research_workspace(symbol=symbol)
            current_session = None
            if brief is not None:
                current_session = record_workflow_session(
                    session,
                    workflow="research-follow-up",
                    title=f"{brief.symbol} research follow-up",
                    summary=f"Evidence items: {len(brief.evidence_items)}",
                    input_payload={"symbol": brief.symbol},
                    output_payload={
                        "symbol": brief.symbol,
                        "evidence_count": len(brief.evidence_items),
                    },
                    related_symbols=[brief.symbol],
                    related_themes=[],
                )
                session.commit()
        return TEMPLATES.TemplateResponse(
            request,
            "research.html",
            {
                "page_title": "Research Workspace",
                "active_page": "research",
                "workspace": workspace,
                "brief": brief,
                "symbol": symbol,
                "current_session": current_session,
            },
        )

    @app.get("/agent", response_class=HTMLResponse)
    async def agent_page(
        request: Request,
        workflow: str = "thematic-analysis",
        theme: str | None = None,
        session_id: int | None = None,
    ) -> HTMLResponse:
        with get_session(app.state.db_path) as session:
            bundle = build_agent_context_bundle(
                session,
                workflow=workflow,  # type: ignore[arg-type]
                theme_request=_theme_request_for_agent(workflow, theme),
                consult_request=_consult_request_for_agent(workflow),
                workflow_session_id=session_id,
            )
            note_context_export(session, session_id)
            journal_entries = list_journal_entries(session, workflow=bundle.workflow, limit=3)
            stored_session = get_workflow_session(session, session_id) if session_id else None
            session.commit()
            packet = build_prompt_packet(bundle)
        return TEMPLATES.TemplateResponse(
            request,
            "agent.html",
            {
                "bundle": bundle,
                "packet": packet,
                "current_session": stored_session,
                "journal_entries": journal_entries,
                "page_title": "Agent Workspace",
                "active_page": "agent",
            },
        )

    @app.get("/agent/context.json")
    async def agent_context_json(
        request: Request,
        workflow: str = "thematic-analysis",
        theme: str | None = None,
        session_id: int | None = None,
    ) -> dict[str, object]:
        del request
        with get_session(app.state.db_path) as session:
            bundle = build_agent_context_bundle(
                session,
                workflow=workflow,  # type: ignore[arg-type]
                theme_request=_theme_request_for_agent(workflow, theme),
                consult_request=_consult_request_for_agent(workflow),
                workflow_session_id=session_id,
            )
            note_context_export(session, session_id)
            session.commit()
        return bundle.model_dump(mode="json")

    @app.get("/api/data-quality.json")
    async def data_quality_json(request: Request) -> dict[str, object]:
        del request
        with get_session(app.state.db_path) as session:
            report = build_data_quality_report(session)
        return report.model_dump(mode="json")

    @app.get("/agent/prompt/{workflow}.md", response_class=PlainTextResponse)
    async def agent_prompt_markdown(
        workflow: str,
        theme: str | None = None,
        session_id: int | None = None,
    ) -> PlainTextResponse:
        with get_session(app.state.db_path) as session:
            bundle = build_agent_context_bundle(
                session,
                workflow=workflow,  # type: ignore[arg-type]
                theme_request=_theme_request_for_agent(workflow, theme),
                consult_request=_consult_request_for_agent(workflow),
                workflow_session_id=session_id,
            )
            note_context_export(session, session_id)
            session.commit()
            packet = build_prompt_packet(bundle)
        return PlainTextResponse(render_prompt_markdown(packet), media_type="text/markdown")

    @app.get("/decisions", response_class=HTMLResponse)
    async def decisions_page(request: Request) -> HTMLResponse:
        from vmarket.services.preview_service import compute_action_preview

        with get_session(app.state.db_path) as session:
            actions = list_actions(session)
            journal_entries = list_journal_entries(session, limit=20)
            previews = {
                a.id: compute_action_preview(session, a)
                for a in actions
                if a.kind in ("buy", "sell") and a.status == "pending"
            }
        pending_count = sum(1 for a in actions if a.status == "pending")
        return TEMPLATES.TemplateResponse(
            request,
            "decisions.html",
            {
                "page_title": "Actions & Journal",
                "active_page": "decisions",
                "actions": actions,
                "journal_entries": journal_entries,
                "pending_count": pending_count,
                "previews": previews,
            },
        )

    @app.get("/actions", response_class=HTMLResponse)
    async def actions_redirect(request: Request) -> RedirectResponse:
        return RedirectResponse("/decisions", status_code=301)

    @app.get("/journal", response_class=HTMLResponse)
    async def journal_redirect(request: Request) -> RedirectResponse:
        return RedirectResponse("/decisions", status_code=301)

    @app.post("/journal/save")
    async def save_journal_route(request: Request) -> RedirectResponse:
        form = await request.form()
        workflow = str(form.get("workflow") or "action-review")
        title = str(form.get("title") or "Journal entry").strip()
        summary = str(form.get("summary") or "").strip()
        rationale = str(form.get("rationale") or "").strip() or None
        workflow_session_id_raw = str(form.get("workflow_session_id") or "").strip()
        workflow_session_id = int(workflow_session_id_raw) if workflow_session_id_raw else None
        related_symbols = _csv_list(form.get("related_symbols"))
        related_themes = _csv_list(form.get("related_themes"))
        open_questions = _csv_list(form.get("open_questions"))
        redirect_to = str(form.get("redirect_to") or "/journal").strip() or "/journal"
        with get_session(app.state.db_path) as session:
            create_journal_entry(
                session,
                workflow=workflow,
                title=title,
                summary=summary,
                rationale=rationale,
                open_questions=open_questions,
                related_symbols=related_symbols,
                related_themes=related_themes,
                workflow_session_id=workflow_session_id,
            )
            session.commit()
        return RedirectResponse(redirect_to, status_code=303)

    @app.post("/actions/stage")
    async def stage_action_route(request: Request) -> RedirectResponse:
        form = await request.form()
        kind = str(form.get("kind") or "watch_add")
        source = str(form.get("source") or "user")
        explanation = str(form.get("explanation") or "").strip() or None
        redirect_to = str(form.get("redirect_to") or "/actions").strip() or "/actions"
        payload = _payload_from_form(kind, form)
        with get_session(app.state.db_path) as session:
            stage_action(
                session,
                kind=kind,  # type: ignore[arg-type]
                payload=payload,
                source=source,
                explanation=explanation,
            )
            session.commit()
        return RedirectResponse(redirect_to, status_code=303)

    @app.post("/actions/{action_id}/confirm")
    async def confirm_action_route(action_id: int) -> RedirectResponse:
        with get_session(app.state.db_path) as session:
            confirm_action(session, action_id)
            session.commit()
        return RedirectResponse("/decisions", status_code=303)

    @app.post("/actions/{action_id}/discard")
    async def discard_action_route(action_id: int) -> RedirectResponse:
        with get_session(app.state.db_path) as session:
            discard_action(session, action_id)
            session.commit()
        return RedirectResponse("/decisions", status_code=303)

    return app
