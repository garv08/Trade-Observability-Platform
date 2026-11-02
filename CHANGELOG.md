# 📝 Changelog

All notable changes to TOP. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

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
