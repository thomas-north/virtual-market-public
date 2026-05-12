# Research And LLM Wiki

Virtual Market can maintain a private research layer alongside the simulated
portfolio. The reusable app ships the rules and tools; each user's live research
corpus stays local.

## Privacy Boundary

Do not commit personal research artifacts.

Ignored local paths:

- `research/raw/`
- `research/normalized/`
- `research/wiki/`
- `research/*.local.json`

Committed reusable paths:

- `RESEARCH.md`
- `research/README.md`
- `research/sources.example.json`
- `vmarket/research/`

## Operating Model

Use three layers:

1. Raw sources: immutable local captures from the last roughly 30 days.
2. Normalized evidence: compact JSONL records with source class, role, URL,
   date, entity tags, and excerpts.
3. LLM Wiki: Obsidian-friendly Markdown pages maintained by the agent.

The wiki is a synthesis layer, not the source of truth. Raw sources remain the
truth layer.

## Source Classes

Use this hierarchy when judging evidence:

- `direct`: official company pages, filings, regulator feeds, issuer factsheets.
- `class_a`: public institutional research and market commentary.
- `corroborating_journalism`: reputable business and market journalism.
- `social`: Reddit and similar sources for sentiment, objections, alternatives,
  repeated claims, and idea discovery.

No buy/sell/trim recommendation should rely on `social` evidence alone.

## Reliable Source Strategy

Use `research/sources.example.json` as the reusable source registry. Users can
copy it to `research/sources.local.json` and add personal holdings, issuer
factsheet URLs, preferred newsletters, or local source notes.

Prefer deterministic Python collectors for sources with stable public APIs or
feeds:

- SEC EDGAR company submissions and company facts for US-listed names.
- Federal Reserve RSS feeds for US macro and rate context.
- Companies House API for UK companies when useful.
- Bank of England, ECB, and FCA public pages for macro and regulatory context.
- Issuer factsheet URLs registered by the user for funds and ETFs.

Use agents or OpenClaw for sources that need judgement, search, or browsing:

- company investor-relations pages with inconsistent layouts
- Reuters/BBC company and market context
- Morningstar, AJ Bell, BlackRock, J.P. Morgan, Goldman Sachs commentary
- Reddit and other social sources

Avoid unofficial RSS generators as core dependencies. They can be useful for
experiments, but the durable system should prefer official APIs, official pages,
or explicit agent/search passes.

## Human-Like Semantic Research

For a stock such as `META.US`, the agent should emulate a careful human:

- Search relevant investing communities for the company, ticker, and close
  competitors.
- Read why people say they are buying, selling, avoiding, or replacing it.
- Extract repeated claims and objections.
- Validate factual claims against direct or higher-quality sources.
- Separate sentiment from evidence.
- Note alternatives investors mention instead of the target company.

Reddit is useful for discovering the conversation. It is not validation by
itself.

## Suggested Wiki Layout

```text
research/wiki/
  index.md
  log.md
  entities/
    META.US.md
  theses/
    meta-ai-product-thesis.md
  sources/
    2026-04-26-meta-reddit-roundup.md
  questions/
    meta-vs-alternatives-2026-04-26.md
```

## Workflow

1. Run `vmarket research init` to create the local private directories.
2. Collect recent source material with an agent or OpenClaw skill.
3. Store raw captures under `research/raw/<SYMBOL>/<YYYY-MM-DD>/`.
4. Normalize material into `research/normalized/<SYMBOL>/<YYYY-MM-DD>.jsonl`.
5. Ask the agent to update the wiki from normalized evidence.
6. Use the wiki to inform portfolio memos and trade planning.

## Normalized Evidence JSONL

Each line in a normalized evidence file is one JSON object matching the
`NormalizedEvidenceItem` schema in `vmarket.research.schema`.

Recommended path:

```text
research/normalized/META.US/2026-04-26.jsonl
```

Minimal example:

```json
{"source_class":"social","evidence_role":"sentiment","source_name":"Reddit","source_type":"reddit_post","collected_at":"2026-04-26T12:00:00","title":"Why investors are debating META","text_excerpt":"Several investors framed META as an AI capex risk versus ad resilience story.","symbols":["META.US"],"companies":["Meta Platforms"],"themes":["AI capex","advertising resilience"],"is_portfolio_relevant":true,"dedupe_key":"example-meta-reddit-1"}
```

Render a deterministic local brief from normalized evidence:

```bash
.venv/bin/vmarket research brief META.US
```

## SEC EDGAR Collector

US-listed companies can be collected from SEC EDGAR submissions:

```bash
.venv/bin/vmarket research collect-sec META.US --cik 1326801 --company-name "Meta Platforms"
```

The command writes normalized evidence to:

```text
research/normalized/META.US/<today>.jsonl
```

Set `VMARKET_SEC_USER_AGENT` in `.env` to identify yourself to the SEC.
