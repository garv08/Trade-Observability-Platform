# TOP — Trade Observability Platform

A local, browser-based research desk for the **Nifty 50**. It stores five years of daily history in DuckDB and charts it with TradingView Lightweight Charts. It has 146 indicators, Scott Carney harmonic patterns, 86 backtestable strategies (including rules adapted from the YouTube channels @neurotrader888 and @UnbiasedTradingGoshawk), and a one-click trend scan. It reads Screener.in fundamentals, and an **Interpretation** pane explains in plain English what everything on the chart means and lays out a rule-based swing-trade plan.

Everything runs on your machine: one Python process and one DuckDB file, with no accounts or API keys.

> **Research tool, not advice.** Prices are delayed public daily data. TOP is not a live NSE feed, not a broker, and not affiliated with NSE, TradingView, Screener.in, or Harmonic Trader. Backtests and historical odds describe the past, not the future.

![CI](https://github.com/garv08/Trade-Observability-Platform/actions/workflows/ci.yml/badge.svg)

---

## Contents

- [Features](#features)
- [Install](#install)
- [Run](#run)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [Project layout](#project-layout)
- [Development and tests](#development-and-tests)
- [License](#license)

## Features

| Area | What you get |
| --- | --- |
| Universe | All 50 Nifty names, including `M&M`, `ETERNAL` (formerly Zomato), and `TMPV` (Tata Motors passenger vehicles) |
| Data | About five years of adjusted daily bars from Yahoo Finance, stored in DuckDB (`data/nse.duckdb`) |
| Chart | Candles and volume, overlays on price, oscillator panes, and 6M/1Y/2Y/5Y/All ranges. Bands and channels are shaded light grey between their upper and lower lines |
| Durations | Every study with a period has quick presets (5 … 200), free entry, and **+ Another** to add the same average again with a different period (e.g. SMA 20/50/200). EMA ribbon lengths are adjustable |
| Darvas and breakouts | **Darvas box** (3-day top and bottom confirmation, breakout and box-broken markers) and a **Breakout & trend detector** (volume-confirmed breakouts and breakdowns, failed-breakout flags, ATR trailing trend), each with a backtestable strategy |
| Indicators | 146 studies in 10 sections: Harmonics, @neurotrader888, @UnbiasedTradingGoshawk, Moving averages, Bands and channels, Trend, Momentum, Volatility, Volume, Price statistics |
| Harmonics | Scott Carney Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab, Cypher, Shark, 5-0, AB=CD, and Three Drives. Patterns are drawn as X-A-B-C-D legs with ratio guides and are on by default for every stock |
| Backtests | 86 long/flat strategies (trend, breakout, trend reversal, harmonics, oscillator, mean reversion, price action, volume, and two creator sections). Fills at the next open, with costs. **Backtest 50** runs one strategy on every name |
| YouTube creators | 9 strategies and 6 studies from **@neurotrader888** (re-implemented from his MIT-licensed GitHub code) and 4 strategies and 2 studies from **@UnbiasedTradingGoshawk** (from the public sources his videos test). Each shows its sources and a confidence label. See [docs/creators.md](docs/creators.md) |
| Trend scan | Every trend, breakout, and reversal rule on the selected stock in one click |
| Fundamentals | Ratios and pros/cons from the public Screener.in page, cached for six hours |
| Interpretation | Plain-English reading of every selected study and strategy, a technical rating (moving-average and oscillator votes), and a swing plan: setup, trigger, entry, stop, targets, and position size. Levels are drawn on the chart. Shows how the same plan did on that stock's own history |
| Controls | Every control sits in the left panel as a searchable dropdown |
| Verify | In-app **Verify** button and `python -m top.verify` run named checks on the front end, back end, and data |

## Install

### Requirements

- **Python 3.10, 3.11, 3.12, or 3.13**
- **git**, to clone the repository
- Internet access the first time, to download history (about 1–2 minutes for all 50 names)
- About 20 MB of disk for the database

The only Python dependency is `duckdb==1.1.3`, installed automatically.

### Linux (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip   # python3-venv is needed for "python3 -m venv"

git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

On Ubuntu 24.04+, if `python3 -m venv` complains about `ensurepip`, install the versioned package, for example `sudo apt install python3.12-venv`.

### macOS

```bash
# Python 3.10–3.13 from python.org or Homebrew (brew install python@3.12)
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### Windows (PowerShell)

```powershell
# Install Python 3.12 from python.org (tick "Add python.exe to PATH") and Git for Windows
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -e .
```

### Install without cloning

Ubuntu and Debian block `pip install` into the system Python, so install into a virtual environment:

```bash
sudo apt install -y git python3-venv python3-pip      # once
python3 -m venv ~/top-venv
~/top-venv/bin/pip install "git+https://github.com/garv08/Trade-Observability-Platform.git"
~/top-venv/bin/top-platform                            # then open http://127.0.0.1:8000
```

Or with [pipx](https://pipx.pypa.io/), which manages the virtual environment for you:

```bash
sudo apt install -y git pipx && pipx ensurepath        # once; open a new terminal afterwards
pipx install "git+https://github.com/garv08/Trade-Observability-Platform.git"
top-platform
```

Both give you the `top-platform` and `top-sync` commands. The web app is bundled inside the package. The database is created in the folder you start TOP from (`./data/nse.duckdb`); set `TOP_DB` to keep it in one place, for example `TOP_DB=~/top-data/nse.duckdb top-platform`.

### Check the install

```bash
top-platform --help
python -c "import top; print('TOP', top.__version__)"
```

## Run

```bash
# from the project folder, with the virtual environment active
top-platform              # or: python -m top
```

Open **http://127.0.0.1:8000** in a browser. Use `127.0.0.1`, not `localhost`: the server binds IPv4 only.

On the first start TOP creates `data/nse.duckdb` in the current folder and downloads daily history for all 50 names in the background. The top bar shows progress (`Sync 12/50`) and then `DuckDB 50/50`. Later starts reuse the stored data. Click **Sync history** to refresh.

You can also fill or refresh the database without the server:

```bash
top-sync                  # downloads all 50 names, prints progress
```

Then:

1. Pick a stock from the **Stock** dropdown on the left.
2. Add studies from the section dropdowns. Carney harmonics are already on.
3. Read the **Interpretation** pane under the chart.
4. Pick a strategy, then **Run backtest** or **Backtest 50**.
5. Use **Trend scan**, **Fundamentals**, **Harmonics list**, and **Verify** for more.

The full user guide is built in: click **Guide** in the top bar, or open `http://127.0.0.1:8000/guide.html`.

To check everything end to end:

```bash
python -m top.verify      # exits 0 when every check passes
```

## Configuration

| Setting | Flag | Environment variable | Default |
| --- | --- | --- | --- |
| Bind address | `--host` | `TOP_HOST` | `127.0.0.1` |
| Port | `--port` | `TOP_PORT` | `8000` |
| Database file | `top-sync --db` | `TOP_DB` | `./data/nse.duckdb` (relative to where you start TOP) |
| Download on start if empty | `--no-sync` turns it off | `TOP_AUTO_SYNC=0` turns it off | on |

Example: `TOP_DB=~/market/nse.duckdb top-platform --port 8050`

TOP has no login. Keep it on `127.0.0.1` unless you put it behind your own access control.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `python3 -m venv` fails with `ensurepip is not available` | `sudo apt install python3-venv`, or the versioned package such as `python3.12-venv` |
| `Command 'pip' not found` | Install it with `sudo apt install python3-pip`, then install TOP inside a virtual environment (see [Install without cloning](#install-without-cloning)) |
| `error: externally-managed-environment` | Ubuntu/Debian protect the system Python. Use a virtual environment or `pipx` as shown above, not `sudo pip` |
| `top-platform: command not found` | Activate the virtual environment (`source .venv/bin/activate`) or run it by path, for example `~/top-venv/bin/top-platform` |
| `Illegal instruction` when starting | Your CPU lacks SSE4.2/POPCNT. TOP pins `duckdb==1.1.3` for this reason; make sure nothing upgraded it (`pip install duckdb==1.1.3`). Do not install NumPy 2 into the same environment for TOP; it does not need NumPy |
| `No matching distribution found for duckdb==1.1.3` | Use Python 3.10–3.13. DuckDB 1.1.3 has no wheels for Python 3.14 |
| Browser says "Failed to fetch" or "The desk did not answer" | Check the server is running and open `http://127.0.0.1:8000` (not `localhost`) |
| `Address already in use` | Another process uses port 8000. Run `top-platform --port 8050` |
| Page looks old after an update | Hard-reload: Ctrl+Shift+R (Cmd+Shift+R on macOS) |
| Some names show "no bars" | Click **Sync history** or run `top-sync`. Yahoo occasionally rate-limits; run it again later |
| Fundamentals error | Screener.in may be unreachable or rate-limiting. Try later |
| A command `top` opens the Linux process viewer | That is the system `top`. TOP's command is `top-platform` (or `python -m top`) |

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/design.md](docs/design.md) | Design document: goals, architecture, data flow, modules, algorithms (backtest, harmonics, interpretation), key decisions, limits |
| [docs/api.md](docs/api.md) | HTTP API reference with request and response examples |
| [docs/creators.md](docs/creators.md) | YouTube creator strategies: sources, rules, adaptations, confidence, first Nifty 50 results |
| [docs/development.md](docs/development.md) | Code layout, running tests, adding an indicator or strategy, releasing |
| [User guide](top/web/guide.html) | Built into the app at `/guide.html` |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Lightweight Charts (Apache-2.0) and data-source notes |
| [docs/archive/](docs/archive/) | Early planning notes, kept for history |

## Project layout

```text
Trade-Observability-Platform/
├── top/                      Python package
│   ├── server.py             HTTP server and JSON API (stdlib ThreadingHTTPServer)
│   ├── store.py              DuckDB schema, Yahoo download, top-sync command
│   ├── universe.py           The 50 Nifty names, sectors, weights
│   ├── arrays.py             Small NumPy-like array helpers (no NumPy needed)
│   ├── indicators.py         146 studies and their catalog
│   ├── strategies.py         86 long/flat strategies and their catalog
│   ├── creators.py           @neurotrader888 and @UnbiasedTradingGoshawk strategies and studies
│   ├── market.py             Equal-weight Nifty 50 proxy from stored bars
│   ├── backtest.py           Next-open fill backtester and metrics
│   ├── harmonics.py          Zigzag pivots and Scott Carney ratio rules
│   ├── explain.py            Plain-language readings, technical rating, swing plan, historical odds
│   ├── fundamentals.py       Screener.in page fetch and parser
│   ├── verify.py             Named self-checks (python -m top.verify)
│   └── web/                  Front end: index.html, app.js, styles.css, guide.html, vendor/
├── tests/                    Offline unit and HTTP integration tests (synthetic data)
├── docs/                     Design, API, development docs
├── .github/workflows/ci.yml  Tests on Python 3.10–3.13 and a wheel smoke test
├── pyproject.toml
└── requirements.txt
```

## Development and tests

```bash
pip install -e .
python -m unittest discover -s tests -t . -v      # offline: synthetic data in a temp DuckDB, real HTTP server
TOP_NETWORK_TESTS=1 python -m unittest tests.test_api   # adds a live Screener.in call
```

See [docs/development.md](docs/development.md) for more.

## License

TOP is released under the [MIT License](LICENSE). The bundled TradingView Lightweight Charts library is under the Apache License 2.0. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
