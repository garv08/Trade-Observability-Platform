# 📝 Changelog

All notable changes to TOP. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.10.1] - 2026-11-10

### Fixed
- **The automatic update could mark a day done before the exchange files were out.** At 19:30 the cron run found no new NSE/BSE bars and would still have recorded the day as updated. A day now counts only once its exchange-file bars are in the store. Until then it retries every 30 minutes, and gives up at 23:30 IST (exchange holiday).
- **A cron update could keep the server from starting for hours.** It ran the leaderboard refresh while holding the database, so after a reboot `top-platform` could not open the store. Cron now updates the data only, and `top-platform` catches the leaderboard up when it starts.

## [0.10.0] - 2026-11-10

### Added
- **Automatic daily data update.** `top-platform` reads the system clock and, once per weekday after 19:00 IST, updates every script: Nifty 50, NSE and BSE stocks, ETFs, indices and delivery %, then the leaderboard rows. Missed days (PC off, server stopped) are caught up at the next start; the machine's time zone does not matter. `--no-auto-update`, `--update-at` and `TOP_AUTO_UPDATE`, `TOP_AUTO_UPDATE_AT` control it.
- **Cron support:** `top-sync --auto` updates when due. If `top-platform` is running it asks the server, because DuckDB allows only one program on the store; otherwise it syncs directly. Overlapping runs are skipped through a lock file. `top-sync --install-cron [--at HH:MM]` adds a crontab line that checks every 30 minutes.
- `/api/status` reports `sync.auto`, and the DuckDB pill's tooltip shows the last and next update.

### Fixed
- The installation guide's example cron line ran `top-sync` while the server held the store, which fails. It now uses `--install-cron`.

## [0.9.0] - 2026-11-08

### Fixed
- **Harmonic look-ahead.** The harmonic strategies entered on the D bar, but a zigzag only confirms D after price has moved Swing % away from it. They now enter on the confirmation bar. On 271 liquid stocks the median return ÷ max drawdown of *Any Carney bullish* falls from 0.99 to 0.26; the old figures were optimistic.
- Harmonic readings measured past hit rates from D; they now measure from the confirmation bar.

### Added
- **Carney PRZ engine**, built from Scott Carney's (@harmonictrader) published process: structure, ratio, confirmation.
  - D and HOP (failure) levels per pattern, Gartley CD/AB check, Carney's pattern preference.
  - Confirmation modes (touch, reversal bar, Carney), optional RSI filter, AD targets, HOP stop and 30-bar time stop.
  - Strategies: *Carney PRZ, confirmed*, *reversal bar* and *touch* (95 in total).
  - Study *Carney PRZ (causal trades + live zones)* (153 in total).
- The Harmonics list and readings show the confirmation date, HOP, and 0.382/0.618 AD targets, plus any live PRZ.
- **Per-strategy revisions in the leaderboard.** Revised strategies are recomputed on every machine on the next leaderboard run, without redoing the others.

### Research
- Backtest of every variant in [design §6.2.1](docs/design.md#621-carney-prz-engine-prz_setups-prz_trades-prz_watch). No causal harmonic variant beats buy and hold, and Carney's confirmation lowers results on daily NSE bars.

## [0.8.0] - 2026-11-06

### Added
- **Ready-made data snapshot.** The database is not in git (about 480 MB; GitHub refuses files over 100 MB), so a fresh clone had only the Nifty 50.
  - `top-sync --snapshot` and a **Download ready-made data** button on the desk install the newest snapshot attached to a GitHub release (`top-data.duckdb.gz`, about 225 MB).
  - The snapshot contains every NSE and BSE stock, ETFs, indices, delivery % and the computed leaderboard.
  - It is checked by SHA-256 and test-opened before replacing the store. The old store is kept as `.bak`.
  - `top-sync --make-snapshot DIR` creates one, and `--snapshot FILE|URL` installs your own copy.
- An *Only the Nifty 50 is loaded* box on the desk explains the two ways to get the rest of the data.

### Fixed
- **Leaderboard, Markets and Portfolio pages unusable on a fresh install.** A global `.empty` CSS rule meant for the chart's "No bars" overlay turned every empty table placeholder into a full-page layer. That covered 26 of the 28 controls on the leaderboard whenever there were no results, as on every fresh clone. The overlay is now `.chart-empty`, and table placeholders can't become overlays.
- First start downloaded everything (hours of BSE/NSE files) instead of just the Nifty 50, contrary to the docs. It now fetches only the Nifty 50.
- Charts opened during the first sync stayed empty until a page reload. Empty answers are no longer cached, and the symbol list refreshes as soon as the Nifty sync ends.
- The top-N portfolio's **Download CSV** replaced the page with a raw error when there were no results. It now shows the message in place.
- On a partly computed leaderboard, the default top-N portfolio strategy could have no qualifying stocks. The fallback now ranks with the same filters it then uses to pick stocks.

## [0.7.0] - 2026-11-05

### Added
- **Top-N portfolio of one strategy** on the Leaderboard page (`GET /api/leaderboard/portfolio`, `.csv`, `top-leaderboard --portfolio`): put ₹1 lakh into each of the #1 strategy's top 20 stocks (or any strategy, N and amount) and follow the combined money over time. Shows final value, CAGR, max drawdown and CAGR ÷ |max DD| against Nifty 50, a growth chart and each stock's result. Stocks only, one listing per company.
- `results/top20-portfolio.csv`, written by `top-leaderboard --results`: Turn of the month, top 20 stocks, ₹20 lakh → ₹2.13 crore from Dec 2021 to Nov 2026 (CAGR 62.0%, max DD −11.3%, CAGR ÷ |DD| 5.48; Nifty 50 with the same money: ₹27.4 lakh, 6.7%, −16.5%, 0.40). The stocks are picked with hindsight, so this is an in-sample best case.

## [0.6.1] - 2026-11-05

### Fixed
- The end-of-run liquidity step computed a 250-day median over all 7.3 million bars and spilled to disk; on a small laptop this ran out of memory after the leaderboard had finished. It now reads only the last ~14 months.
- A leaderboard run interrupted before its final step left the deflated-Sharpe baselines stale, so new scripts showed an inflated DSR. Any run, even one with nothing left to compute, now refreshes them.

### Changed
- `results/` regenerated with every NSE stock: 611,146 backtests on 6,643 scripts. **Turn of the month** now ranks first by median return ÷ max drawdown (profitable on 85% of 3,311 scripts), and mean-reversion rules moved into the top ten.

## [0.6.0] - 2026-11-04

### Added
- **Every NSE main-board stock**: about 2,600 stocks in the EQ, BE and BZ series beyond the Nifty 50, as `NSE:<TICKER>` (universe `nse`), with five years of history.
  - **Data:** backfilled from the NSE bhavcopies the sync already downloads, and resumable (days are recorded as `NSE-EQ`).
  - **Renames:** names are matched by ticker, then ISIN, so history survives renames.
  - **Adjustments:** NSE corporate actions and the gap rule apply as for BSE.
  - **Not included:** SME/Emerge stocks.
- **NSE** universe chip on the desk and the leaderboard. *Backtest NSE* covers the Nifty 50 plus every other NSE stock.
- Delivery % for NSE stocks. A company listed on both exchanges gets NSE delivery % on both symbols. Delivery is re-read once to fill the new names.
- Scans include NSE stocks that have no BSE listing (for example CDSL, BSE Ltd), so every company appears exactly once.
- `TOP_WORKERS` sets the number of leaderboard worker processes.

### Fixed
- Tests left a temporary database in `/tmp` for every test class and never removed them. On Linux systems where `/tmp` is RAM-backed this slowly used up memory (1.2 GB here) and led to crashes. Test runs now delete their temporary folders.

## [0.5.0] - 2026-11-04

Ideas from about 42,000 public posts of 13 X accounts, re-implemented in TOP's own code. See [docs/research/x-digest.md](docs/research/x-digest.md).

### Added
- **Portfolio page** (`/portfolio.html`, `POST /api/portfolio`): monthly top-N backtests that rank a whole universe. Strategies: momentum 12-1, low volatility, sector rotation, and ETF momentum with a trend filter. Universes: Nifty 50, BSE group A, NSE sector indices, NSE ETFs. Ranks at the month-end close and trades at the next open with costs. Optional absolute-momentum or Nifty-200-day market filter. Shows the equity curve against Nifty 50, an underwater chart, holdings, rebalances, and an N sweep.
- **Markets page** (`/markets.html`, `GET /api/markets/*`):
  - Nifty volatility regime (calm, normal, stressed) shaded on a Nifty chart.
  - Breadth over BSE group A/B stocks: % above 50/200-day averages, new highs − new lows, advances/declines.
  - Sector rotation with relative-rotation quadrants.
  - FII/DII cash flows.
  - Eight scans: Bloodbath, multi-year breakout, 52-week breakout, breakout soon, leaders while Nifty falls, 1-year multibaggers, near 52-week low, delivery surge.
- **Robustness:**
  - Monte Carlo trade reshuffling in every backtest.
  - **Walk-forward** button that re-picks the main setting each year from earlier data (`POST /api/walkforward`).
  - Probabilistic and **deflated Sharpe** columns, filter and sort on the leaderboard, and a "% passing DSR 95" column in the strategy ranking.
  - A Kelly fraction in backtest metrics.
- **Sizing:** backtests can size entries to a **volatility target** or **half Kelly** (from earlier trades only).
- **Quant research strategies:** TSMOM 12-month, Kalman trend, turn of the month, and a Hurst regime router (92 strategies in total).
- **Studies:** Kalman level, Hurst exponent, Delivery %, and Market volatility regime (152 in total), each with a plain-English reading.
- **Data:**
  - Five years of NSE security-wise **delivery %**, mapped to TOP symbols by ticker or ISIN.
  - A daily **FII/DII** snapshot.
  - `top-sync --delivery`, also part of Sync history.
- Verify checks for research strategies, delivery and FII/DII, breadth and regime.
- `tests/test_research.py`: causality of new signals, sizing, Monte Carlo, walk-forward, split-adjusted SQL, breadth, scans, portfolio look-ahead, and parsers.
- Docs: [research digest](docs/research/x-digest.md), [project history](docs/project-history.md), and user-guide, API and design sections for the new pages.

### Changed
- The leaderboard now tracks which strategies each script has run, so new strategies are added without recomputing old ones.
- Split-adjusted bars are available in SQL (`markets.adjusted_sql`), 25× faster than a per-bar lookup and identical to `load_bars`.

## [0.4.1] - 2026-11-02

### Added
- Leaderboard **Sort by → Most return ÷ |Max DD|** (total return ÷ worst drawdown, 5% floor), a sortable **Return ÷ DD** column, `sort=return_dd` in the API, and a `return_dd` column in the CSVs.

### Changed
- **Best strategy per script** picks each script's best row by the chosen sort (it was always CAGR ÷ DD).
- `results/` regenerated with the new column; 44 Nifty 50 scripts were recomputed after their Yahoo bars updated.

## [0.4.0] - 2026-11-02

### Added
- **By strategy** view on the Leaderboard page: strategies ranked by the **median of total return ÷ |max drawdown|** across every qualifying script (≥ 3 trades, ≥ 2 tested years, ≥ ₹10 lakh a day, no CAGR cut, ≥ 50 scripts). Also shows the mean, middle half, median return/DD/CAGR, % profitable, % beating buy-and-hold, median trades, and best script. Re-sortable, CSV download, click through to the strategy's scripts.
- `GET /api/leaderboard/strategies` (+ `.csv`), `top-leaderboard --strategies FILE`.
- `top-leaderboard --results DIR`: compute (resuming), then write all committed snapshots with fixed settings, so any machine can reproduce `results/` after `git pull` + `top-sync`.
- `results/strategy-ranking-return-dd.csv` and a README section with the top strategies.

### Fixed
- Leaderboard orderings break ties by name (best strategy per script, best script per strategy), so exports are byte-identical for the same database.

## [0.3.1] - 2026-11-02

### Fixed
- **Windows: leaderboard button grey / pages unstyled.** Static files are served with fixed content types instead of `mimetypes`, which on Windows reads the registry and often maps `.css` and `.js` to `text/plain`. The leaderboard page also carries its own colour palette, so it stays usable even if `styles.css` can't load.
- The leaderboard run checks that its worker processes start (within 2 minutes) and otherwise continues inside the server, instead of hanging with the button disabled.
- "Running" is reported only while the run thread is alive, so the button can't stay disabled after a crash.
- A run with nothing to compute now says so ("no script has 250+ daily bars yet … click Sync history"), and the status includes the database path.
- Page errors (including an un-restarted server after an update) are shown under the progress bar and leave **Run backtests** usable; the page retries every 15 seconds.

### Docs
- Windows upgrade steps, and why `top-platform` must be restarted after `git pull`.

## [0.3.0] - 2026-11-02

### Added
- **Strategy leaderboard** page (`/leaderboard.html`, **Leaderboard** in the top bar): all 88 strategies backtested on every stock, ETF, and index with at least a year of data, ranked by **CAGR ÷ |max drawdown|**, with CAGR above 15% by default. Filters for universe, strategy, minimum trades and history, and script search; best strategy per script; sortable columns; per-strategy pass counts; CSV export; rows open the script and strategy on the chart.
- Resumable background leaderboard job across worker processes (`POST /api/leaderboard`, `GET /api/leaderboard`, `GET /api/leaderboard/status`, `top-leaderboard`). After a daily sync only scripts with new bars are recomputed.
- **NSE and BSE indices**: ~170 NSE indices for five years and ~80 BSE indices from April 2025, from the exchanges' daily index files (`top-sync --indices`, `POST /api/sync {"what": "indices"}`; also part of **Sync history**). An **Indices** universe chip in the desk and in Backtest universe.
- The ratio floors drawdown at 5%; `years` means years tested after warm-up; a traded-value filter (₹10 lakh a day by default on the page) keeps illiquid listings out.
- A data-quality gate keeps thinly traded or glitchy series out of the ranking, and non-price indices (Dividend Points, VIX) are excluded.
- A full CSV export of any filtered view (`GET /api/leaderboard.csv`, **Download CSV**, `top-leaderboard --export`), and saved snapshots in `results/`.
- Verify checks for indices and the leaderboard; offline tests for index parsing, index sync, and leaderboard ranking and resume.

### Changed
- `bhav_days` now also tracks index files, under `NSE-IDX` and `BSE-IDX`; the bhavcopy sync only looks at its own rows.
- Fundamentals refuse indices with a clear message.
- DuckDB connections are capped at 768 MB and 2 threads (`TOP_DB_MEMORY` to change). The default of 80% of RAM could starve a 3 GB laptop during a leaderboard run.

## [0.2.1] - 2026-11-01

### Fixed
- Stock search is fast with ~5,100 names: rows are built once and cached, typing is debounced, and each search renders in milliseconds instead of about a second.
- Typing searches every universe, whichever chip is on. Exact symbol or BSE-code matches come first, then symbol and name prefixes. Picking a name from another universe switches the chip.
- The stock search placeholder shows the selected universe and says you can search by name, symbol, or BSE code.

## [0.2.0] - 2026-11-01

### Added
- **All BSE stocks and ETFs**: ~4,700 BSE equities, ~355 NSE ETFs, and ~35 BSE-only ETFs from the exchanges' daily bhavcopies, five years deep, resumable, and refreshed by **Sync history** or `top-sync --bhav`.
- **Split and bonus adjustment** for bhavcopy data, from NSE corporate actions plus a price-gap rule, applied at read time.
- **Universe chips** (Nifty 50 · ETFs · BSE · All) on the stock picker. The dropdown shows the best matches first.
- **Backtest universe** replaces Backtest 50. Large universes scan the 200 most traded names.
- `top-sync --nifty | --bhav | --years`, `POST /api/sync {"what": …}`, and `universe`/`limit` on `/api/scan`.
- Fundamentals for BSE stocks via Screener.in scrip-code pages; ETFs are refused with a clear message.
- **Key levels plan** and **Pattern breakout projector** (Trend), method inspired by @TradZoo: next-session triggers with stepped targets, and wedge, triangle, or channel breakouts with measured-move targets, plus matching Breakout strategies and written plans in the Interpretation pane.
- Studies can declare line colours and step drawing.
- A Verify check for BSE and ETF coverage, plus offline tests for parsers, adjustments, and universe scans.

### Changed
- The market proxy used by CMMA and the contrarian rules uses only the Nifty 50.
- `coverage` reports per-universe counts; `symbols_with_bars` still counts the Nifty 50.

## [0.1.0] - 2026-11-01

First public release.

### Added
- **Data**: all 50 Nifty stocks, about five years of adjusted daily bars from Yahoo Finance in DuckDB; **Sync history** and the `top-sync` command.
- **Chart**: TradingView Lightweight Charts with candles, volume, overlays, oscillator panes, and range buttons.
- **Controls**: a left panel of searchable dropdowns for stock, 10 indicator sections, and strategy.
- **148 indicators**, including:
  - 12 Scott Carney harmonic studies, drawn as X-A-B-C-D legs and on by default;
  - Darvas box and a volume-confirmed breakout and trend detector;
  - 8 studies adapted from @neurotrader888 and @UnbiasedTradingGoshawk.
- **Durations**: period presets, free entry, **+ Another** for several copies of a study, and adjustable EMA-ribbon lengths.
- **Band shading**: a light grey fill between upper and lower lines, drawn beneath the candles.
- **88 long/flat strategies**: next-open backtests with costs and full metrics, plus **Backtest 50** across all stocks.
- **Creator strategies**: 13 rules adapted from @neurotrader888 and @UnbiasedTradingGoshawk, with sources and confidence labels.
- **Interpretation pane**: plain-English readings, a technical rating, and a rule-based swing plan with historical odds and base rates.
- **Analysis**: Trend scan, Screener.in fundamentals, Harmonics list, and in-app Verify.
- **Shareable links**: URL parameters for stock, studies, strategy, range, action, and open dropdown.
- **Packaging**: the `top-platform` and `top-sync` commands, `python -m top`, and configuration via `TOP_HOST`, `TOP_PORT`, `TOP_DB`, and `TOP_AUTO_SYNC`.
- **Quality**: offline unit and HTTP integration tests, and GitHub Actions CI on Python 3.10–3.13 with a wheel smoke test.
- **Docs**: README, installation guide, user guide, indicator and strategy catalogs, creators, design, API, and development docs.

[0.2.0]: https://github.com/garv08/Trade-Observability-Platform/releases/tag/v0.2.0
[0.1.0]: https://github.com/garv08/Trade-Observability-Platform/releases/tag/v0.1.0
