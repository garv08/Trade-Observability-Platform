# 🗒️ Project history

How TOP was built: each request, what was delivered, and the decisions and problems along the way. This was written from the working sessions and is kept up to date with each release. For exact changes per version, see the [changelog](../CHANGELOG.md).

## 1. A real Nifty 50 desk (v0.1.0)

**Asked for:** all 50 NSE stocks in a database (DuckDB), smooth data fetching, a TradingView-like GUI, pick any stock and backtest any of ~50 strategies with a good UI/UX, then 100+ sectioned indicators.

**Built:**
- A local Python server (standard library only) with DuckDB 1.1.3 and TradingView's open-source Lightweight Charts, instead of reverse engineering the commercial TradingView client.
- Five years of adjusted Nifty 50 history from Yahoo.
- 136 indicators in searchable, sectioned dropdowns, with duration presets and "+ another" copies of moving averages.
- Light grey fill inside every band.
- Long/flat backtests that fill at the next open, with costs.

**Follow-ups in the same period:**
- Verify hooks across front end, back end and data.
- Scott Carney harmonics: 11 patterns plus "all", drawn and backtestable.
- One-click Trend scan.
- Screener.in fundamentals.
- A fix for "Failed to fetch" when switching stocks.
- Darvas boxes and a breakout-and-trend detector.
- An Interpretation pane with a swing plan and historical odds.
- Strategies from two YouTube creators, @neurotrader888 and @UnbiasedTradingGoshawk.

**Packaging:** published as the `top` package (`pip install git+https://github.com/garv08/Trade-Observability-Platform.git`) with README, guides, five screenshots and shareable links.

**Commit rule:** all commits are in **garv08**'s name with no co-author trailer. The first two commits were rewritten to follow it.

## 2. All BSE stocks and ETFs, and TradZoo's method (v0.2.0, v0.2.1)

**Asked for:** data for all BSE stocks and ETFs. Then study @TradZoo's scraped X posts (daily stock descriptions and trend analysis) and build a similar indicator.

**Built:**
- **Data:** five years of BSE and NSE bhavcopies (four file formats), giving about 4,700 BSE stocks, 355 NSE ETFs and 34 BSE ETFs. Splits and bonuses are adjusted from NSE corporate actions plus a price-gap rule, and the sync resumes where it stopped.
- **Universe chips:** Nifty 50, ETFs, BSE and All, plus a "Backtest universe" button.
- **TradZoo-style studies and strategies:** *Key levels plan* (next-session triggers with stepped targets) and *Pattern breakout* (wedges, triangles and channels with a measured target).
- **TradZoo's posts:** used only to learn the method. No text or images were copied, per the dataset notice.
- **Search fix (0.2.1):** searching more than 5,000 names was slow and hid other universes. Search is now cached and debounced, covers every universe, and picking a name switches the chip.

## 3. The strategy leaderboard and indices (v0.3.0, v0.3.1)

**Asked for:** a web page with every strategy backtested on all 5,000+ scripts, sorted by CAGR ÷ max drawdown, with CAGR above 15%. Add NSE and BSE indices. Save the leaderboard as CSV and push.

**Built:**
- **Indices:** 173 NSE indices with five years of history, and 82 BSE indices from April 2025 (BSE keeps only about 18 months of daily index files).
- **Leaderboard page:** a background job runs every strategy on every script in worker processes and can resume.
  - A fast list-based metrics path, about 2.5× quicker, tested against the full backtest.
  - A data-quality gate for thin or glitchy series, and Dividend Points and VIX excluded.
  - A 5% drawdown floor in the ratio.
  - "Tested years" counted after each strategy's warm-up.
  - A traded-value filter.
- **CSV snapshots:** saved in `results/`, with the full file attached to the release.
- **Laptop hang during the run:** the run resumed without losing work. DuckDB was then capped at 768 MB (`TOP_DB_MEMORY`).
- **Windows fix (0.3.1):** the Run button was grey because Python on Windows reads file types from the registry, which can label `.css` and `.js` as plain text. The server now sends fixed file types. If worker processes can't start, the run continues in-process. Errors are shown on the page.

## 4. Ranking strategies and reproducible results (v0.4.0, v0.4.1)

**Asked for:** which strategy gives the most return ÷ max drawdown across stocks, sorted, reproducible on another machine after `git pull`. Also a "Most return ÷ Max DD" option in Sort by.

**Built:**
- **By strategy view:** ranks strategies by the median of total return ÷ max drawdown across qualifying scripts, with no CAGR cut.
- **Reproducible results:** `top-leaderboard --results results` rebuilds all committed CSVs with fixed settings and tie-breakers, so the same database gives byte-identical files.
- **Return ÷ DD:** a sortable column and Sort by option; *Best strategy per script* follows the chosen sort.

## 5. Ideas from 13 X accounts (v0.5.0)

**Asked for:** read every scraped HTML/JSON of the X handles, digest it, and add strategies or improve the charting and framework. Then CI-test everything from earlier conversations and push.

**Built:** about 42,000 posts were read, with three accounts studied in depth (@quantscience_, @stockmarket8058, and the quant/AI group). The summary, in our own words with links only, is in [research/x-digest.md](research/x-digest.md).

- **Portfolio page:** monthly top-N backtests for momentum 12-1, low volatility, sector rotation, and ETF momentum with a trend filter, with an N sweep and a market filter.
- **Markets page:** Nifty volatility regime, breadth, sector rotation, FII/DII flows, and eight scans (Bloodbath, multi-year breakout, 52-week breakout, breakout soon, leaders, multibaggers, near 52-week low, delivery surge).
- **Robustness:** Monte Carlo trade reshuffling, walk-forward re-tuning, probabilistic and deflated Sharpe on the leaderboard, and a Kelly fraction in every backtest.
- **Sizing:** volatility target and half Kelly.
- **New strategies:** TSMOM 12-month, Kalman trend, turn of the month, and a Hurst regime router.
- **New studies:** Kalman level, Hurst exponent, Delivery %, and Market volatility regime.
- **Data:** five years of NSE delivery % (about 1.24 million rows for ~2,800 names) and a daily FII/DII snapshot.
- **Leaderboard:** new strategies are added per script without recomputing old ones.

**Testing:** the full suite (91 tests) passes on Python 3.10, 3.12 and 3.13 (3.10 and 3.12 installed with `uv`), and the wheel was checked to contain every new file.

**Problems along the way:**
- Internet outages interrupted downloads.
- The server was killed for running out of memory. The root cause was `/tmp`: on this laptop it is a 1.7 GB RAM-backed filesystem, and the test helper had left 272 temporary databases there (1.2 GB) since the project began. The test helper now deletes its temporary folders when a run ends. Every job resumes after a crash; long runs use one worker, and screenshots are taken only when nothing else is running.

## 6. Every NSE stock (v0.6.0)

**Asked for:** make sure all NSE stocks are present.

**Found:** NSE lists about 3,038 stocks. 2,465 were already in TOP through their BSE listing, and the Nifty 50 as NSE symbols. 573 were missing entirely: 130 main-board and 443 SME/Emerge.

**Chosen:** add every NSE main-board stock as its own `NSE:` symbol, including those already on BSE, but not SME. Scans count each company once.

**Built:**
- About 2,600 `NSE:` stocks with five years of history, matched by ticker or ISIN, with split and bonus adjustments.
- NSE delivery %.
- An NSE chip on the desk and leaderboard.

**Also fixed:** the RAM-backed `/tmp` problem described in section 5.

## Working rules

- Commit and push as garv08 only, with no co-author trailer.
- The market database (`data/nse.duckdb`) and scraped X data are never committed.
- Tests are offline and use synthetic data; CI runs Python 3.10–3.13 and checks the wheel.
- Results are research only, not investment advice. Backtests are in-sample, and the universe is today's listing (survivorship bias).
