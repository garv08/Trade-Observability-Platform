<div align="center">

# 📈 TOP — Trade Observability Platform

**A local, TradingView-style research desk for India's Nifty 50.**<br/>
Chart all 50 stocks, stack 146 indicators, spot Scott Carney harmonics and Darvas boxes,<br/>
backtest 86 strategies on one stock or all 50, and read a plain-English swing-trade plan, all on your own machine.

[![CI](https://github.com/garv08/Trade-Observability-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/garv08/Trade-Observability-Platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)
![DuckDB](https://img.shields.io/badge/storage-DuckDB-FFF000?logo=duckdb&logoColor=black)
![Charts](https://img.shields.io/badge/charts-Lightweight%20Charts-2962FF)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Platforms](https://img.shields.io/badge/runs%20on-Linux%20%7C%20macOS%20%7C%20Windows-555)

[Quick start](#-quick-start) · [Screenshots](#-a-quick-tour) · [Features](#-features) · [Install guide](docs/installation.md) · [User guide](docs/user-guide.md) · [Docs](docs/README.md)

<img src="docs/images/overview.png" alt="TOP main screen: ICICI Bank with SMA 20/50/200, shaded Bollinger Bands, harmonic patterns, swing-plan levels, and the Interpretation pane" width="100%"/>

</div>

> [!IMPORTANT]
> **Research tool, not advice.** TOP uses delayed public daily data. It is not a live NSE feed, not a broker, and not affiliated with NSE, TradingView, Screener.in, Harmonic Trader, or the YouTube creators whose ideas it adapts. Backtests and historical odds describe the past, not the future.

---

## 🚀 Quick start

```bash
git clone https://github.com/garv08/Trade-Observability-Platform.git
cd Trade-Observability-Platform
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
top-platform
```

Open **http://127.0.0.1:8000**. On the first run TOP downloads about five years of daily history for all 50 stocks (1–2 minutes). The top bar shows `Sync 12/50` and then `DuckDB 50/50`.

> [!TIP]
> On Ubuntu/Debian you may first need `sudo apt install -y git python3-venv python3-pip`. Windows and macOS steps, `pipx`, upgrading, and troubleshooting are in the **[installation guide](docs/installation.md)**.

---

## 📸 A quick tour

<table>
<tr>
<td width="50%" valign="top">

### 1 · Chart, indicators, and the Interpretation pane
Pick any Nifty 50 stock from a searchable dropdown and stack studies from 10 sections. Here: SMA 20/50/200 (added with **+ Another**), Bollinger Bands with a grey fill, and the swing plan's Entry/Stop/T1/T2 on the price axis. The pane below explains every selection in plain English.

</td>
<td width="50%" valign="top">

### 2 · Scott Carney harmonics
Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab, Cypher, Shark, 5-0, AB=CD, and Three Drives, drawn as X-A-B-C-D legs with ratio guides. **Harmonics list** shows each pattern's date, side, PRZ, and measured ratios.

</td>
</tr>
<tr>
<td><img src="docs/images/overview.png" alt="Chart with moving averages, Bollinger fill, and interpretation"/></td>
<td><img src="docs/images/harmonics.png" alt="Bharti Airtel with Carney harmonic patterns and the harmonics list"/></td>
</tr>
<tr>
<td valign="top">

### 3 · Darvas boxes and breakout detection
Nicolas Darvas boxes (3-day top and bottom confirmation) and a volume-confirmed **Breakout & trend detector** that flags breakouts, breakdowns, failed breakouts, and the ATR trailing trend that follows.

</td>
<td valign="top">

### 4 · Backtests with full results
Signal at the close, fill at the next open, with costs. Results include return, CAGR, max drawdown, Sharpe, Sortino, win rate, profit factor, exposure, the equity curve against buy and hold, and every trade.

</td>
</tr>
<tr>
<td><img src="docs/images/darvas-breakout.png" alt="Infosys with Darvas boxes, breakout range, trailing stop, and markers"/></td>
<td><img src="docs/images/backtest.png" alt="Trendline breakout backtest on Infosys with metrics, equity curve, and trades"/></td>
</tr>
<tr>
<td colspan="2" valign="top">

### 5 · Strategies from YouTube creators, and Backtest 50
Rules adapted from **@neurotrader888** and **@UnbiasedTradingGoshawk** sit in their own searchable groups, each with sources and a confidence label. **Backtest 50** runs any strategy on all 50 stocks and ranks them.

<img src="docs/images/creators-scan.png" alt="Creator strategies dropdown and Connors Double 7s ranked across all 50 stocks"/>

</td>
</tr>
</table>

---

## ✨ Features

| | Feature | Details |
| --- | --- | --- |
| 🗂️ | **All 50 Nifty stocks** | About five years of adjusted daily bars in a local DuckDB file. Includes `M&M`, `ETERNAL` (formerly Zomato), and `TMPV`. One-click **Sync history** or `top-sync` |
| 📊 | **TradingView-style chart** | TradingView Lightweight Charts with candles, volume, overlays, oscillator panes, and 6M/1Y/2Y/5Y/All ranges |
| 🧮 | **146 indicators** in 10 sections | Harmonics · @neurotrader888 · @UnbiasedTradingGoshawk · Moving averages · Bands and channels · Trend · Momentum · Volatility · Volume · Price statistics. [Full catalog →](docs/indicators.md) |
| ⏱️ | **Flexible durations** | Period presets (5 … 200), free entry, and **+ Another** to add SMA 20/50/200 side by side. Adjustable EMA-ribbon lengths |
| 🌫️ | **Shaded bands** | Every band or channel with upper and lower lines is shaded light grey, drawn under the candles |
| 🦋 | **Scott Carney harmonics** | 11 patterns plus "all", drawn as XABCD legs, on by default for every stock and backtestable |
| 📦 | **Darvas box & breakout detector** | Boxes, breakouts, breakdowns, failed breakouts, and ATR trailing trend, each with a strategy |
| 🧪 | **86 strategies** | Trend, breakout, trend reversal, harmonics, oscillators, mean reversion, price action, volume, and two creator groups. [Full catalog →](docs/strategies.md) |
| 🏁 | **Backtest 50** | Run one strategy on every stock and rank by return, drawdown, and trades |
| 🎥 | **YouTube creator strategies** | 13 rules adapted from @neurotrader888's MIT-licensed code and the public sources @UnbiasedTradingGoshawk tests. [Details →](docs/creators.md) |
| 🗣️ | **Interpretation pane** | Plain-English reading of every selected study and strategy, a technical rating (MA and oscillator votes), and a swing plan with trigger, entry, stop, T1/T2, position size, and historical odds on the same stock |
| 🔎 | **Trend scan** | Every trend, breakout, and reversal rule on the selected stock in one click |
| 🏢 | **Fundamentals** | Ratios and pros/cons from the public Screener.in page, cached for six hours |
| 🔗 | **Shareable links** | `/?symbol=INFY&studies=sma:50,sma:200,bbands&strategy=darvas_breakout&run=backtest` opens straight to a set-up |
| ✅ | **Verify** | In-app checks across front end, back end, and data, plus `python -m top.verify` and an offline test suite in CI |

---

## 🧭 How it works

```mermaid
flowchart LR
  B["Browser<br/>index.html + app.js<br/>Lightweight Charts"] -- "JSON /api/*" --> S["top-platform<br/>(Python stdlib HTTP server)"]
  S --> E["Engines<br/>indicators · strategies · backtest<br/>harmonics · Darvas · explain"]
  S <--> D[("DuckDB<br/>data/nse.duckdb")]
  S -- "first run / Sync" --> Y["Yahoo Finance<br/>daily history"]
  S -- "on demand" --> F["Screener.in<br/>fundamentals"]
```

- **One process, one dependency.** A standard-library HTTP server and `duckdb`. No NumPy, no Node build, no accounts, no API keys.
- **Everything is computed from your stored bars** when you ask, so the chart, backtests, and readings always agree.
- **No look-ahead.** Pivots, boxes, and breakouts appear only once they're confirmed. Trades fill at the next open.

Read the full [design document](docs/design.md) for the architecture, algorithms, and decisions.

---

## 📚 Documentation

| Guide | What's inside |
| --- | --- |
| 🛠️ [Installation](docs/installation.md) | Linux, macOS, Windows, `pipx`, upgrading, uninstalling, running in the background, troubleshooting |
| 🧑‍💻 [User guide](docs/user-guide.md) | A walkthrough of every panel and button, with screenshots and example links |
| 🧮 [Indicator catalog](docs/indicators.md) | All 146 studies with settings and ranges |
| 🧪 [Strategy catalog](docs/strategies.md) | All 86 strategies with rules and settings |
| 🎥 [Creator strategies](docs/creators.md) | @neurotrader888 and @UnbiasedTradingGoshawk: sources, confidence, adaptations, results |
| 🏗️ [Design](docs/design.md) | Architecture, data, algorithms, decisions, performance, security, testing |
| 🔌 [HTTP API](docs/api.md) | Every route with request and response examples |
| 🧰 [Development](docs/development.md) | Code layout, tests, adding an indicator or strategy, releases |
| 🤝 [Contributing](CONTRIBUTING.md) · 📝 [Changelog](CHANGELOG.md) · 🔐 [Security](SECURITY.md) | Project process |

The same user guide is built into the app: click **Guide** in the top bar.

---

## ⚙️ Configuration

| Setting | Flag | Environment variable | Default |
| --- | --- | --- | --- |
| Bind address | `--host` | `TOP_HOST` | `127.0.0.1` |
| Port | `--port` | `TOP_PORT` | `8000` |
| Database file | `top-sync --db` | `TOP_DB` | `./data/nse.duckdb` (relative to where you start TOP) |
| Download on first start | `--no-sync` turns it off | `TOP_AUTO_SYNC=0` turns it off | on |

```bash
TOP_DB=~/top-data/nse.duckdb top-platform --port 8050
```

> [!WARNING]
> TOP has no login. Keep it on `127.0.0.1` unless you put it behind your own access control.

---

## ❓ FAQ

<details>
<summary><b>Is this a live trading or brokerage app?</b></summary>

No. TOP reads delayed public **daily** bars and never places orders. It is for research, learning, and back-testing ideas.
</details>

<details>
<summary><b>Where does the data come from, and how fresh is it?</b></summary>

Daily OHLCV from Yahoo Finance's public chart endpoint (adjusted for splits and dividends), stored in DuckDB. Click **Sync history** or run `top-sync` after the market closes to refresh. Fundamentals come from Screener.in on demand.
</details>

<details>
<summary><b>Why does it pin <code>duckdb==1.1.3</code> and avoid NumPy?</b></summary>

So it runs on older x86 CPUs without SSE4.2/POPCNT. Newer DuckDB and NumPy 2 builds crash there with "Illegal instruction". TOP includes its own small array helpers instead.
</details>

<details>
<summary><b>Are the swing plan's odds a prediction?</b></summary>

No. They replay the same rule on that stock's own history and report how often it worked. They describe the past, and results near 50% or 0R mean there was no edge.
</details>

<details>
<summary><b>Did you download YouTube videos to build the creator strategies?</b></summary>

No. Rules were re-implemented from public text: video descriptions and chapters, the creators' own open-source code, and the papers or books the videos test. Each strategy shows its sources and a confidence label. See [creators.md](docs/creators.md).
</details>

<details>
<summary><b>Can I add my own indicator or strategy?</b></summary>

Yes. Each is a small Python function registered in a catalog. See [Development → Add an indicator / strategy](docs/development.md).
</details>

---

## 🗺️ Roadmap

- [ ] Walk-forward and Monte-Carlo permutation tests in the UI
- [ ] Saved layouts and watchlists
- [ ] Alerts when a breakout, Darvas, or harmonic signal fires
- [ ] Optional NSE index and F&O data for short-side setups
- [ ] Desktop wrapper (single-click app)

Ideas and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 🙏 Credits

- [TradingView Lightweight Charts™](https://github.com/tradingview/lightweight-charts) (Apache-2.0) for the chart engine
- [DuckDB](https://duckdb.org) for local storage
- [neurotrader888](https://github.com/neurotrader888) and [Unbiased Trading](https://www.youtube.com/@UnbiasedTradingGoshawk) for the published ideas adapted in `top/creators.py`
- Scott M. Carney's harmonic ratios, Nicolas Darvas's box method, and Larry Connors' published rules

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 📄 License

[MIT](LICENSE) © 2026 garv08 and TOP contributors. The bundled chart library keeps its Apache-2.0 license.
