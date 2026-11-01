# 📝 Changelog

All notable changes to TOP. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-11-01

### Added
- **All BSE stocks and ETFs**: ~4,700 BSE equities, ~355 NSE ETFs, and ~35 BSE-only ETFs from the exchanges' daily bhavcopies, five years deep, resumable, and refreshed by **Sync history** or `top-sync --bhav`.
- **Split and bonus adjustment** for bhavcopy data, from NSE corporate actions plus a price-gap rule, applied at read time.
- **Universe chips** (Nifty 50 · ETFs · BSE · All) on the stock picker. The dropdown caps at 300 visible matches.
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
