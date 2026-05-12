# Contributing To Virtual Market

Thanks for contributing.

This repository is the public open-source home of Virtual Market. It is
maintained as a **curated public mirror** of a faster-moving private working
repository, so a little process helps keep both sides clean.

## Local setup

```bash
git clone https://github.com/thomas-north/virtual-market-public.git
cd virtual-market-public
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run checks

```bash
ruff check vmarket
pytest -q
vmarket --help
```

If you add or change commands, please also smoke-test the relevant subcommand.

## Local data and privacy

Keep personal simulator state out of git.

Examples of local-only material:

- `user_data/`
- SQLite databases
- raw research captures
- generated reports
- screenshots
- notes

## Pull request expectations

Good PRs here usually:

- describe the user-facing reason for the change
- update tests with the code
- update docs when behavior changes
- avoid committing machine-local paths, secrets, or personal portfolio data

## Public/private repo workflow

This public repo is curated from a private implementation repo.

That means:

- not every private commit is replayed here
- public PRs should still make sense as standalone open-source changes
- accepted public changes may later be pulled back into the private repo

As a contributor, you do **not** need access to the private repo. Treat this repo
as the source of truth for anything you can see and test here.

## Agent-assisted contributions

Using an external coding agent is welcome. If you do:

- keep the agent operating within this public repo only
- review generated code before submitting
- make sure docs and tests stay aligned
- do not rely on unpublished private commands or local-only scaffolding

## License

By contributing, you agree that your contributions are made under the
Apache-2.0 license used by this repository.
