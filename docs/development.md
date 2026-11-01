# 🧰 Development

## Project layout

```text
Trade-Observability-Platform/
├── top/                        Python package
│   ├── server.py               HTTP server, JSON API, CLI (top-platform)
│   ├── store.py                DuckDB schema, Yahoo download, top-sync
│   ├── universe.py             The 50 Nifty names, sectors, weights
│   ├── arrays.py               Small NumPy-like array helpers (no NumPy needed)
│   ├── indicators.py           Indicator math and the study catalog
│   ├── strategies.py           Long/flat strategies and their catalog
│   ├── backtest.py             Next-open fill backtester and metrics
│   ├── harmonics.py            Zigzag pivots and Scott Carney ratio rules
│   ├── patterns.py             Darvas boxes, breakout and trend detector
│   ├── creators.py             @neurotrader888 and @UnbiasedTradingGoshawk rules
│   ├── market.py               Equal-weight Nifty 50 proxy from stored bars
│   ├── explain.py              Readings, technical rating, swing plan, odds
│   ├── fundamentals.py         Screener.in fetch and parser
│   ├── verify.py               Named self-checks (python -m top.verify)
│   └── web/                    index.html, app.js, styles.css, guide.html, vendor/
├── tests/                      Offline unit and HTTP integration tests
├── scripts/                    generate_catalog_docs.py
├── docs/                       Guides, catalogs, design, API; images/ holds screenshots
├── .github/                    CI workflow, issue and PR templates
├── pyproject.toml              Package metadata, entry points
└── requirements.txt
```

## Set up

```bash
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

`-e` (editable) means changes to `top/` take effect on the next server start. Front-end changes in `top/web/` need only a browser hard-reload.

## Run

```bash
top-platform                     # http://127.0.0.1:8000
top-platform --port 8050 --no-sync
TOP_DB=/tmp/scratch.duckdb top-platform
```

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

- `tests/support.py` points the store at a temporary DuckDB and seeds deterministic synthetic bars for all 50 names. No network is needed.
- `tests/test_engine.py` covers indicator, strategy, backtest, harmonic, parser, and interpretation logic.
- `tests/test_api.py` starts the real server on a free port and calls every route, including a path-traversal check.
- `TOP_NETWORK_TESTS=1` adds a live Screener.in call.

On live data, run `python -m top.verify`. It exits 0 when every check passes.

CI (`.github/workflows/ci.yml`) runs the tests on Python 3.10–3.13. It also builds a wheel, checks that the web assets are inside, installs it into a clean virtual environment, and starts the server.

## Code layout

| Path | What to change there |
| --- | --- |
| `top/indicators.py` | Indicator math and the `_build()` catalog |
| `top/strategies.py` | Strategy rules and the `_register()` catalog |
| `top/harmonics.py` | Pattern specs and ratio rules |
| `top/creators.py` | Creator strategies and studies; pass `creator`, `sources`, `confidence` to `_add` |
| `top/explain.py` | Readings (`WHAT`, `FAMILY`, `ZONES`, readers), rating, swing plan |
| `top/server.py` | API routes |
| `top/web/app.js` | Front end |
| `top/web/guide.html` | User guide (keep it in step with features) |

### Add an indicator

1. Write the math in `indicators.py` using the existing helpers (`sma`, `ema`, `rolling_max`, …). Use `top.arrays` (imported as `np`); do not import NumPy.
2. Register it in `_build()`:

   ```python
   _add("my_osc", "My oscillator", M, O, [_num("length", "Length", 14, 2, 100)], ["value"],
        lambda f, p: {"value": my_osc(f.c, _param(p, "length", 14))})
   ```

   `M` is the section and `O` is the pane (`O` for its own pane, `P` for price).
3. Add it to a family in `explain.py` (`FAMILY`, and `ZONES` if bounded) so the Interpretation pane reads it well. Add a one-line `WHAT` entry.
4. Run the tests. `test_every_study_has_a_latest_value` catches series that never fill.

### Add a strategy

1. Register it in `strategies.py` `_register()`:

   ```python
   _add("my_rule", "My rule", "Trend", "Long when ...", [], lambda f, p: _hold(entry_mask, exit_mask, warmup))
   ```

   It must return a position array: 1 long, 0 flat, NaN during warm-up.
2. Run the tests. `test_every_strategy_backtests` runs it.

## Conventions

- Python 3.10+, standard library plus `duckdb` only.
- Keep `duckdb==1.1.3` unless you also drop support for older CPUs (see `docs/design.md` §7).
- Never hold the DuckDB lock (`session()`) during network calls.
- New API inputs must be validated against the symbol or strategy catalogs.
- Escape any server or third-party text in the front end with `esc()`.

## Generated docs

`docs/indicators.md` and `docs/strategies.md` are generated from the catalogs:

```bash
python scripts/generate_catalog_docs.py
```

Run it whenever you add or change an indicator or strategy.

## Screenshots

The README images in `docs/images/` are taken with headless Chrome against a running server, using [shareable links](user-guide.md#shareable-links):

```bash
shot() { google-chrome --headless=new --disable-gpu --hide-scrollbars --user-data-dir=/tmp/top-shot \
  --window-size=1440,${3:-900} --virtual-time-budget=30000 --screenshot=docs/images/$1.png "http://127.0.0.1:8000/?$2"; }
shot overview        "symbol=ICICIBANK&studies=sma:20,sma:50,sma:200,bbands&range=252"
shot harmonics       "symbol=BHARTIARTL&range=504&run=harmonics&studies=harm_butterfly"
shot darvas-breakout "symbol=INFY&carney=0&studies=darvas,breakout_trend&range=126"
shot backtest        "symbol=INFY&carney=0&studies=nt_trendlines,nt_zigzag&strategy=nt_trendline_breakout&range=1260&run=backtest" 1000
shot creators-scan   "symbol=BHARTIARTL&strategy=ut_double_seven&run=scan&menu=strategy&q=@"
```

## Release

1. Bump `version` in `pyproject.toml` and `top/__init__.py`.
2. Run the tests and `python -m top.verify`.
3. Tag `vX.Y.Z` and push the tag. Users can install with `pip install "git+https://github.com/garv08/Trade-Observability-Platform.git@vX.Y.Z"`.
