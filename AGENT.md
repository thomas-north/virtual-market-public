# Virtual Market — Public Agent Guide

This file explains how an external coding agent should operate the **public**
Virtual Market repository safely.

## Working style

- treat this repo as a local fake-money simulator
- never assume real broker access exists
- keep all personal portfolio data local and untracked
- prefer reproducible CLI commands over hidden manual steps

## Local state

Personal state belongs in gitignored local storage such as:

```text
user_data/
```

Do not commit:

- SQLite databases
- screenshots
- raw research artifacts
- generated reports
- personal notes or portfolio snapshots

## Current public product surface

The public repo currently exposes the core simulator and research flows.

Typical commands:

```bash
.venv/bin/vmarket init
.venv/bin/vmarket cash deposit 500 --currency GBP
.venv/bin/vmarket watch add AAPL.US --name "Apple Inc" --currency USD --asset-type stock
.venv/bin/vmarket sync prices --days 30
.venv/bin/vmarket portfolio
.venv/bin/vmarket memo daily
.venv/bin/vmarket research brief META.US
```

The cockpit, onboarding, thematic analysis, and portfolio consultation workflows
are planned public sync additions and may not yet exist on every public branch.
Check `vmarket --help` before assuming a newer command surface.

## Symbol rules

Use these formats:

- US equities: `TICKER.US`
- LSE instruments: `TICKER.L`
- UK funds/OEICs: 7-character SEDOL

If a symbol format is wrong, price sync will usually fail.

## Contribution safety

When making public-repo changes:

- preserve backward compatibility unless the PR clearly changes the contract
- update tests and docs together
- keep local/private workflow assumptions out of committed files
- avoid adding repo-specific personal tooling to the public contract

## Public mirror context

This repository is maintained as a curated open-source mirror of a faster-moving
private implementation repo. Public changes should be understandable on their own
and safe for outside contributors to build on.
