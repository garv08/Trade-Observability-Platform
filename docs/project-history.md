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

**Another crash (v0.6.1):** the laptop rebooted after the 6,900-script leaderboard run. The work was safe: every script had been computed and saved. The final liquidity step had been reading all 7.3 million bars and spilled to disk; it now reads only the last ~14 months. Re-running also showed that an interrupted run left the deflated-Sharpe baselines stale, so they are now refreshed on every run. With NSE stocks included, *Turn of the month* became the top strategy by median return ÷ max drawdown.

## 7. A top-20 portfolio of the best strategy (v0.7.0)

**Asked for:** in the leaderboard, take the first strategy and put ₹1 lakh in each of its top 20 stocks (₹20 lakh in total), compute the growth of the money over time, the overall CAGR ÷ max drawdown, and the final number.

**Built:** a *Top-N portfolio* section on the Leaderboard page, an API, a CLI option and `results/top20-portfolio.csv`.

**Result:** Turn of the month, top 20 stocks, ₹20 lakh → ₹2.13 crore over 4.9 years (CAGR 62%, max drawdown −11.3%, CAGR ÷ |DD| 5.48). Nifty 50 with the same money reached ₹27.4 lakh.

**Caveat:** the stocks are picked with hindsight from the same period, so this is a best case.

## 8. Data on another machine and a fresh-clone review (v0.8.0)

**Reported from a second PC after `git pull`:**
- The 8,000+ scripts were missing.
- On the leaderboard, a layer covered every button.

**Why the data was missing:** the database has never been in git. It is 480 MB of generated data, and GitHub refuses files over 100 MB.

**Fix:** a compressed snapshot (225 MB) is attached to a GitHub release. `top-sync --snapshot`, or a **Download ready-made data** button, installs it in minutes, and Sync history then tops it up.

**Why the buttons were covered:** a global `.empty` CSS rule for the chart's "No bars" overlay also matched the empty-table placeholders on the other pages. With no results, as on every fresh clone, it covered the whole page. On the dev machine the tables were never empty, so it never showed. An automated check now confirms every control on every page is clickable with an empty database. With the old rule, 26 of 28 leaderboard controls were covered.

**Code review:** a full review of fresh-clone, empty-database and Windows behaviour found four more bugs. All are fixed:
- First start downloaded everything.
- Charts opened during the first sync stayed empty.
- The portfolio CSV download landed on an error page.
- The default portfolio strategy could have no stocks.

## 9. Scott Carney's own rules, and the harmonic look-ahead (v0.9.0)

**Ask:** read all @harmonictrader (Scott Carney) posts and charts, tune the harmonic indicators, implement improvements and backtest them all.

**Source:** 3,274 posts (Nov 2021 – Nov 2026), 997 with charts, read for personal research. Only rules are used; no text or images are copied into the repository.

**Rules found in the posts:** structure, then ratio, then confirmation. D is the pattern's XA level, the PRZ runs from D to the HOP (harmonic optimal price), and a close beyond the HOP fails the pattern. Confirmation is a close above the prior 3 highs or two bullish closes. Targets are 0.382 and 0.618 of AD, with a 30-bar time stop. He prefers the Bat, Deep Crab, Shark and Crab, and does not treat the Cypher as one of his patterns.

**Finding:** the old harmonic strategies entered on the D bar, but a zigzag only knows D after price moves Swing % away from it. That look-ahead inflated the median result about four times:

| Variant (271 liquid stocks) | Median return ÷ max DD |
| --- | --- |
| Any Carney, entry on D (old) | 0.99 |
| Any Carney, entry when D is confirmed | 0.26 |
| Carney PRZ, touch | 0.19 |
| Carney PRZ, Carney confirmation | −0.01 |
| Buy and hold | 1.54 |

**Changes:**
- Every harmonic strategy is now causal; tests check that adding future bars never changes a past position.
- New Carney PRZ engine with D/HOP levels per pattern, confirmation modes and AD targets. New strategies: *Carney PRZ, confirmed / reversal bar / touch*. New chart study with live zones.
- Readings show whether D is confirmed, the HOP and AD targets.
- The leaderboard now stores a revision per strategy, so revised strategies are recomputed on every machine without redoing the rest.

**Conclusion:** on daily NSE bars, harmonic patterns have a small edge at best once look-ahead is removed, and Carney's confirmation rule does not help. They remain useful as chart context, not as a stand-alone system.

## 10. Automatic daily data update (v0.10.0)

**Ask:** a cron job that checks the system time and pulls the latest OHLC data for all NSE/BSE scripts.

**Constraint:** DuckDB lets only one program open the store, so a plain cron `top-sync` fails while `top-platform` runs.

**Design:**
- The server has a scheduler thread. Each weekday after 19:00 IST (system clock converted to IST) it runs the full update once, and catches up missed days at start.
- `top-sync --auto` is for cron. It hands the update to a running server through `/api/sync`, or syncs directly when the server is down. A lock file stops overlapping runs. `top-sync --install-cron` adds the line.

**Verified:** on restart the scheduler caught up Monday 9 Nov by itself. The Nifty 50, NSE and BSE stocks and ETFs all received the 9 Nov bar, and the store grew from 8,044 to 8,071 scripts. The cron command handed over to the running server.

## Working rules

- Commit and push as garv08 only, with no co-author trailer.
- The market database (`data/nse.duckdb`) and scraped X data are never committed.
- Tests are offline and use synthetic data; CI runs Python 3.10–3.13 and checks the wheel.
- Results are research only, not investment advice. Backtests are in-sample, and the universe is today's listing (survivorship bias).
