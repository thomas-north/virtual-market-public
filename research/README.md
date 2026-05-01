# Private Research Workspace

This directory is the local research workspace for Virtual Market.

The reusable project commits this README and `sources.example.json`, but ignores
personal research data:

- `raw/`
- `normalized/`
- `wiki/`
- `*.local.json`

Run:

```bash
.venv/bin/vmarket research init
```

That creates the private directories and starter wiki files.

Copy `sources.example.json` to `sources.local.json` if you want to customise
source lists for your own portfolio.

