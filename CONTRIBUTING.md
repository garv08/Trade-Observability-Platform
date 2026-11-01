# 🤝 Contributing to TOP

Thanks for helping improve TOP. Bug reports, ideas, docs fixes, new indicators, and new strategies are all welcome.

## Ground rules

- **Research tool, not advice.** Contributions must not present results as recommendations or promise returns.
- **No look-ahead.** A signal at bar *t* may use data up to and including bar *t* only. Trades fill at the next open.
- **Long or flat.** Strategies return positions of `1` (long), `0` (flat), or `NaN` (warm-up). NSE cash shorts are intraday only.
- **Keep dependencies at one.** Standard library plus `duckdb==1.1.3`. No NumPy (see [design §7](docs/design.md#7-key-decisions)).
- **Credit ideas.** If a rule comes from a book, paper, video, or repository, add the source and respect its license.

## Set up

```bash
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
top-platform --port 8050
```

## Before you open a pull request

```bash
python -m unittest discover -s tests -t . -v      # offline tests (synthetic data + real HTTP server)
python scripts/generate_catalog_docs.py           # if you added or changed an indicator or strategy
python -m top.verify                              # optional, on real data after a sync
```

- Add or update tests in `tests/`.
- Update the docs your change touches: README, `docs/`, and the in-app guide `top/web/guide.html`.
- Keep commits focused, with a clear message.

## Adding things

| You want to add | Start here |
| --- | --- |
| An indicator | [docs/development.md → Add an indicator](docs/development.md#add-an-indicator) |
| A strategy | [docs/development.md → Add a strategy](docs/development.md#add-a-strategy) |
| A creator strategy | `top/creators.py`; pass `creator`, `sources`, `confidence`, and `notes` to `_add` |
| An API route | `top/server.py`; validate inputs against the symbol or strategy catalogs |
| UI | `top/web/app.js`, `styles.css`; escape server or third-party text with `esc()` |

## Reporting bugs and ideas

Use the [issue templates](https://github.com/garv08/Trade-Observability-Platform/issues/new/choose). For security problems, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
