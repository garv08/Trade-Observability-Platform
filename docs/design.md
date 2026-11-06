# TOP design document

| | |
| --- | --- |
| Product | TOP — Trade Observability Platform |
| Version | 0.8.0 |
| Status | Working local release |
| Scope | Nifty 50, daily bars, research and backtesting. No order routing |

## 1. Goals

1. **All 50 Nifty stocks in one local database**, filled automatically and fast to read.
2. **A TradingView-like chart** that switches stocks instantly and stacks studies on price or in panes.
3. **Breadth of analysis**: 100+ indicators in sections, Scott Carney harmonics, ~50+ strategies, all backtestable in the browser.
4. **Explain, don't just plot**: every selection gets a plain-English reading, plus a rule-based swing plan with honest historical odds.
5. **Verifiable**: named self-checks in the app and offline tests that start the real server.
6. **Easy to install**: one Python dependency, no build step, no accounts.

### Non-goals

- Live or intraday data, order placement, or live portfolio accounting (portfolio *backtests* are in scope).
- Shorting in backtests. NSE cash-market shorts are intraday only, so strategies are long/flat.
- Certified pattern detection. The harmonics are ratio approximations of Carney's published rules.
- Multi-user hosting. There is no authentication; the server binds to `127.0.0.1` by default.

## 2. Architecture

```mermaid
flowchart LR
  subgraph Browser
    UI["index.html + app.js<br/>Lightweight Charts"]
  end
  subgraph "Python process (top-platform)"
    S["server.py<br/>ThreadingHTTPServer"]
    IND["indicators.py<br/>152 studies"]
    STR["strategies.py<br/>92 rules"]
    BT["backtest.py"]
    HAR["harmonics.py"]
    EX["explain.py"]
    FUN["fundamentals.py"]
    VER["verify.py"]
    ST["store.py"]
  end
  DB[("DuckDB<br/>data/nse.duckdb")]
  Y["Yahoo Finance<br/>chart API"]
  SC["Screener.in<br/>company page"]

  UI -- "GET/POST /api/*" --> S
  S --> IND & STR & BT & EX & FUN & VER
  STR --> IND
  IND --> HAR
  STR --> HAR
  EX --> IND & STR & BT & HAR
  S --> ST
  ST <--> DB
  ST -- "sync (background thread)" --> Y
  FUN -- "on demand, 6h cache" --> SC
```

- **One process.** The standard-library `ThreadingHTTPServer` serves the static web app from `top/web/` and a JSON API under `/api/`.
- **No front-end build.** `app.js` is plain JavaScript. The chart library is vendored, so the app works offline after the first data sync.
- **Computation happens on request.** Studies, strategies, and readings are computed from stored bars for each request. Nothing is precomputed except the bars themselves.

### Request flow: picking a stock

```mermaid
sequenceDiagram
  participant U as User
  participant A as app.js
  participant S as server.py
  participant D as DuckDB
  U->>A: pick "INFY" in Stock dropdown
  A->>S: GET /api/bars?symbol=INFY (cached per symbol in the browser)
  S->>D: SELECT bars
  S-->>A: ~1,240 daily bars
  A->>A: draw candles + volume
  A->>S: POST /api/studies (active studies incl. Carney)
  S-->>A: series, markers, harmonic drawings
  A->>S: POST /api/explain (debounced 250 ms)
  S-->>A: headline, rating, swing plan, readings
  A->>A: render Interpretation pane, draw Entry/Stop/T1/T2
```

Each load carries a request token. A slow response for a previous stock is dropped instead of overwriting the current one. This fixed the earlier "Failed to fetch" race on fast clicks.

## 3. Modules

| Module | Responsibility | Notes |
| --- | --- | --- |
| `universe.py` | The 50 symbols, names, sectors, index weights, Yahoo tickers | `M&M` → `M&M.NS`; `ETERNAL`, `TMPV` use current tickers |
| `store.py` | DuckDB schema, `session()` lock, Yahoo download with retries, `replace_bars`, coverage, `top-sync` CLI | See §5 |
| `arrays.py` | Minimal NumPy-like `Array` (elementwise math, masks, `where`, `roll`, `nanmean`, …) | Lets TOP run on CPUs where NumPy 2 wheels crash |
| `indicators.py` | Indicator math and the study catalog (`id`, `section`, `pane`, `params`, `outputs`) | `compute()` returns series, plus optional markers and drawings |
| `strategies.py` | Strategy catalog and `signal()` → position array (1 long, 0 flat, NaN warm-up) | Reuses indicator math |
| `backtest.py` | Next-open fills, costs, equity, benchmark, trades, metrics | See §6.1 |
| `harmonics.py` | Zigzag pivots, Carney ratio matcher, study output, strategy positions | See §6.2 |
| `explain.py` | Per-study readings, technical rating, swing plan, historical odds | See §6.3 |
| `creators.py` | Strategies and studies adapted from @neurotrader888 and @UnbiasedTradingGoshawk, with sources and confidence | See [creators.md](creators.md) |
| `patterns.py` | Darvas boxes and the volume breakout / trend detector (studies with markers, plus strategies) | Causal: levels appear only once confirmed |
| `levels.py` | Key levels plan and pattern breakout projector (method inspired by @TradZoo) | Causal; levels apply to the next session |
| `indices.py` | NSE and BSE daily index files → `IDX:` symbols in `nse_index` / `bse_index` | Never split-adjusted; resumable by day |
| `leaderboard.py` | Every strategy on every script in worker processes; `leaderboard` table, ranking query, `top-leaderboard` CLI | See §5 Leaderboard |
| `delivery.py` | NSE security-wise delivery % (5 years, mapped to TOP symbols by ticker/ISIN) and the daily FII/DII snapshot | Resumable by day under `NSE-DELIV` |
| `research.py` | Strategies and studies from the [X research digest](research/x-digest.md): TSMOM, Kalman trend, turn of month, Hurst router; Kalman level, Hurst, Delivery %, Market regime studies | Causal; studies needing extra data declare `needs` |
| `robust.py` | Monte Carlo trade reshuffling and walk-forward re-tuning of one setting | Used by `/api/backtest` and `/api/walkforward` |
| `markets.py` | Split-adjusted bars in SQL, breadth, Nifty volatility regime, sector rotation, eight stock scans | Scan figures cached until the store changes |
| `portfolio.py` | Monthly top-N portfolio backtests (momentum 12-1, low vol, sector rotation, ETF momentum) | Rank at month-end close, trade at next open |
| `snapshot.py` | Make, download, verify (SHA-256, test open) and install a compressed copy of the whole store; GitHub release asset `top-data.duckdb.gz` + `top-data.json` | Swaps the file under the store lock; moves any old WAL aside so it is never replayed onto the snapshot |
| `market.py` | Equal-weight Nifty 50 proxy from the stored bars, cached by store state | Used by the CMMA and contrarian rules |
| `fundamentals.py` | Screener.in fetch, `#top-ratios` and pros/cons parser, 6-hour cache | Standard-library HTML parser |
| `verify.py` | Named checks over catalogs, synthetic pattern, parser, data coverage, every study and strategy, interpretation | In-process, so `/api/verify` never calls itself over HTTP |
| `server.py` | Routing, input validation, JSON encoding, static files, CLI | `build_server()` is used by tests |
| `web/leaderboard.html`, `web/leaderboard.js` | Leaderboard page: run control, filters, ranked table, per-strategy counts, CSV | Polls while a run is active |
| `web/markets.html/.js`, `web/portfolio.html/.js`, `web/pages.css` | Markets and Portfolio pages | Same chart library, no framework |
| `web/app.js` | Chart, searchable dropdowns, studies, harmonics drawing, tester, insight panel, interpretation pane | No framework |

## 4. User interface

```text
┌ top bar: TOP · selected stock · DuckDB 50/50 · Guide · Sync history ───────────────┐
│ Left panel (320px)           │ Chart toolbar: legend · 6M 1Y 2Y 5Y All               │
│  Stock ▾ (search)            │ Price chart (+ oscillator panes)                      │
│  Indicators                  │                                                       │
│   Harmonics ▾  Trend ▾ …     ├───────────────────────────────────────────────────────┤
│   On the chart (params)      │ Interpretation: swing outlook │ what selections say   │
│  Backtest                    ├───────────────────────────────────────────────────────┤
│   Strategy ▾ params capital  │ Output panel (Trend scan, scans, Fundamentals…)       │
│   Run backtest · Scan univ.  ├───────────────────────────────────────────────────────┤
│  Analysis buttons            │ Backtest results (collapsed until first run)          │
└──────────────────────────────┴───────────────────────────────────────────────────────┘
```

- **Searchable dropdowns** replace long lists. Typed words must all match name, id, group, or sector. Arrow keys, Enter, and Esc work. Indicator dropdowns are multi-select and stay open.
- **Band shading** uses a Lightweight Charts series primitive (`BandFill` in `app.js`) attached to the candle series with `zOrder: "bottom"`, so the grey fill sits beneath the candles. Any price study with `upper` and `lower` outputs gets it.
- **Study copies.** Each active study is an instance with its own id, so the same study can be on the chart several times with different periods. Only the newest study request draws; older responses from quick clicks are dropped.
- **Shareable links.** On load, `openFromLink()` in `app.js` reads URL parameters (`symbol`, `studies`, `carney`, `strategy`, `range`, `run`, `menu`, `q`) to restore a set-up. The README screenshots use the same mechanism.
- **Nothing overlays the chart.** Scan output and readings live in panels below it, and the chart shrinks to fit.
- Under 1000px wide, the left panel becomes a drawer (**Controls**).

## 5. Data and storage

### Schema

```sql
symbols(symbol PK, name, sector, weight, rank, yahoo, exchange, kind, universe, code, isin, grp)
bars(symbol, interval, ts DATE, open, high, low, close, volume, PRIMARY KEY(symbol, interval, ts))
adjustments(symbol, ex_date, factor, source, note, PRIMARY KEY(symbol, ex_date))
corporate_actions(symbol, isin, ex_date, factor, subject)
bhav_days(exchange, day, rows)
leaderboard(symbol, strategy, cagr_pct, max_dd_pct, ratio, total_return_pct, buy_hold_pct, trades, win_rate_pct,
            profit_factor, sharpe, exposure_pct, in_position, years, first_day, last_day, computed_at, PRIMARY KEY(symbol, strategy))
leaderboard_done(symbol PK, last_day, catalog_key, strategies, computed_at)
delivery(symbol, ts, traded, delivered, pct, PRIMARY KEY(symbol, ts))
fii_dii(day, category, buy, sell, net, PRIMARY KEY(day, category))
market_breadth(ts PK, stocks, advances, declines, above50, base50, above200, base200, new_highs, new_lows, base252)
leaderboard_done(symbol PK, last_day, catalog_key, strategies, computed_at, ids)   -- ids: strategies already run
leaderboard_liquidity(symbol PK, median_value_lakh); leaderboard_trials(symbol PK, trials, sr_std, sr_star)
meta(key PK, value)          -- last_sync, bhav_last_sync, index_last_sync
```

### BSE stocks and ETFs (bhavcopies)

`top/bhav.py` builds the extended universe from the exchanges' daily bhavcopy files: one file per trading day listing every traded security.

| Source | Format | Used for |
| --- | --- | --- |
| `BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV` (from Jul 2024) and `EQddmmyy_CSV.ZIP` (earlier) | BSE equity segment | BSE stocks (ISIN `INE…01…`) and BSE-only ETFs (ISIN `INF…`) |
| `BhavCopy_NSE_CM_…csv.zip` (from Jul 2024) and `cmDDMONYYYYbhav.csv.zip` (earlier) | NSE cash market | NSE ETFs, from the NSE ETF list |
| NSE `corporates-corporateActions` API | JSON | Split, bonus, and consolidation factors |

- **Listing.** The union of the last five trading days. Debt and government securities are excluded, and ETFs listed on both exchanges are kept once, on NSE.
- **History.** Every weekday in the window is fetched once. Non-trading days return an HTML page, which is recognised and skipped. Finished days are recorded in `bhav_days`, so an interrupted sync resumes.
- **Adjustment.** Bhavcopy prices are raw. Factors live in `adjustments(symbol, ex_date, factor, source)` and are applied in `load_bars()` at read time: prices before the ex-date are divided by the cumulative factor, and volume is multiplied by it.
  - `nse_ca`: NSE corporate actions, matched to BSE stocks by ISIN issuer code (first 7 characters) and to NSE ETFs by symbol. Multiple actions on the same ex-date multiply (for example a 2:1 split plus bonus 4:1 gives 10).
  - `gap`: for names without a matching action, an overnight gap of 35% or more that matches a standard ratio (1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 20, 25, 50, 100, or their inverses) on both the open and the close. Most BSE-only stocks have 2–20% price bands, so such gaps are almost always corporate actions.
  - Dividends are not adjusted, unlike the Yahoo-sourced Nifty 50.
- **NSE stocks.** Every NSE row in series EQ, BE or BZ with an `INE` ISIN becomes `NSE:<TICKER>` (universe `nse`), except Nifty 50 tickers, which stay on Yahoo data. Daily rows are matched to symbols by ticker, then ISIN, so renames keep their history (a split changes the ISIN but not the ticker, and a rename the reverse). The five-year backfill is tracked in `bhav_days` as `NSE-EQ`. Adjustments match NSE corporate actions by ISIN issuer or symbol, as for BSE.
- **Universes.** `symbols.universe` is `nifty50`, `nse`, `nse_index`, `bse_index`, `nse_etf`, `bse_etf`, or `bse`. The market proxy (`market.py`) uses only the Nifty 50.

### Indices

`top/indices.py` reads NSE's `ind_close_all_DDMMYYYY.csv` (every NSE index, OHLC and constituent volume, available for the whole five-year window) and BSE's `INDEXSummary_DDMMYYYY.csv` (Sensex, BSE 100/500, sectoral; OHLC only). BSE keeps only about 18 months of these files and its history API refuses scripts, so the BSE walk goes backwards from today and stops after 15 missing weekdays. Symbols are `IDX:<NAME>` (NSE, name upper-cased with spaces removed, for example `IDX:NIFTYBANK`) and `IDX:BSE:<ID>` (for example `IDX:BSE:SENSEX`), with `kind = 'index'`. Days are tracked in `bhav_days` under `NSE-IDX` and `BSE-IDX`; missing days older than four days are recorded so they are not retried. Indices are never adjusted.

### Leaderboard

`top/leaderboard.py` backtests every strategy (default parameters, ₹10 lakh, 5 bps per side) on every symbol with at least 250 bars and stores one row per (symbol, strategy).

- **Process model.** The server thread reads bars in batches of 12 symbols and hands them to a `spawn` process pool (up to 2 workers, `nice 10`). Workers never open DuckDB: the Nifty proxy used by CMMA and the contrarian rules is computed once in the parent and pinned in each worker with `market.pin()`. Results come back as tuples and are bulk-loaded with `COPY`.
- **Resume.** `leaderboard_done` records each symbol's last bar and a catalogue key (strategy ids, capital, cost, version). A run skips symbols whose stored results match, so after a daily sync only symbols with new bars are recomputed.
- **Order.** Nifty 50, NSE indices, BSE indices, NSE ETFs, BSE ETFs, then BSE stocks by recent traded value, so the most useful rows appear first.
- **Data-quality gate.** In the worker, on the split-adjusted series: skip a symbol if it has bars on fewer than 50% of the weekdays in its span, or any close-to-close ratio outside 0.5–2.0. Such series (thin BSE listings, bad ticks, unmatched corporate actions) otherwise produce CAGRs in the thousands of percent. Skipped symbols are recorded with zero strategies so they are not retried until new bars arrive. Dividend Points and VIX indices are excluded by name.
- **Ranking.** `ratio = cagr_pct / max(|max_dd_pct|, 5)` (MAR with a 5% drawdown floor). `years` is the time tested after the strategy's warm-up, not the listing's age; older rows are converted in place from `(1 + total) = (1 + cagr) ^ years`. `leaderboard_liquidity` holds each symbol's median daily traded value (₹ lakh, last 250 bars), refreshed after each run, for the traded-value filter (indices exempt). The query filters (`cagr > min`, trades, years, universe, strategy, search) before ranking, `QUALIFY row_number()` keeps the best row per symbol when asked, and a second aggregate counts how many scripts each strategy passes on.
- **Strategy ranking.** `strategy_ranking()` aggregates per strategy over the same filtered rows, without the CAGR cut: median/mean/quartiles of `total_return_pct / max(|max_dd_pct|, 5)`, hit rates, and the best script, keeping strategies with ≥ 50 scripts. `write_results()` writes the three committed CSVs from fixed `RESULT_FILTERS`/`STRATEGY_FILTERS`. All orderings have name tie-breakers, so the same database gives byte-identical files.
- **Incremental.** `leaderboard_done.ids` lists the strategies already run for each script. Adding strategies to the catalogue computes only the new ones (partial updates run first); new bars or a change of capital, cost or version recompute the script.
- **Probabilistic and deflated Sharpe.** For each row, PSR = Φ((SR − 0)·√(n−1) / √(1 + SR²/2)) with SR the daily Sharpe and n the tested days; DSR uses SR\* instead of 0, the expected best Sharpe among the script's N strategy trials, SR\* = σ·((1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e))) with σ the spread of those trials' Sharpes (Bailey and López de Prado). Normal returns are assumed, so both are optimistic for fat-tailed stocks.
- **Cost.** A list-based `backtest.metrics()` (same rules as `run()`, checked by a test for every strategy) skips the equity, benchmark, and trade output. All 92 strategies take 2–4 s per symbol, so the full run (~4,750 symbols) takes 2–4 hours on two cores. DuckDB is capped at 768 MB and 2 threads (`TOP_DB_MEMORY`) so a long run leaves room for the browser.

### Sync

- Source: `query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}.NS?interval=1d&range=5y`, with adjusted close.
- OHLC are scaled by `adjclose / close`, so splits and dividends do not create false gaps.
- Each symbol is retried 5 times with back-off. A failure is recorded and the sync moves on to the next symbol.
- Runs in a background thread on first start or on **Sync history**. `top-sync` runs it in the foreground.

### Concurrency and write path

- DuckDB connections are serialized by a process-wide lock (`session()`). The lock is never held during network calls.
- `replace_bars` deletes the symbol's rows, then `COPY`s a CSV into a temp table and inserts from it. Row-by-row inserts took about 18 s per symbol on the reference machine; `COPY` takes well under a second. DuckDB 1.1 also rejects deleting and re-inserting the same primary key with parameterised inserts in one transaction, which this path avoids.
- `ensure_schema` upserts symbols and is cached per process.

## 6. Algorithms

### 6.1 Backtest

- **Signal at the close, fill at the next session's open.** No look-ahead.
- Long or flat, fully invested when long, fractional shares.
- Cost in basis points on entry and on each closed exit (default 5 bps).
- Benchmark: buy and hold from the same first tradable bar, without costs.
- Metrics: total return, CAGR, max drawdown, Sharpe, Sortino, win rate, profit factor, trades, average trade, exposure, ending equity.

### 6.2 Scott Carney harmonics

1. **Zigzag.** A pivot is confirmed when price reverses by at least *Swing %* (default 3%) from the running extreme.
2. **XABCD windows.** Every five consecutive alternating pivots are tested, both bullish (X low) and bearish (X high, mirrored).
3. **Ratios.** AB/XA, BC/AB, CD/BC, AD/XA, XC/XA, and for Cypher CD/XC. Each is matched against the pattern's ranges within *Tolerance* (default ±0.05).

| Pattern | Key rules |
| --- | --- |
| Gartley | AB 0.618, BC 0.382–0.886, CD 1.272–1.618, AD 0.786 |
| Bat | AB 0.382–0.50, BC 0.382–0.886, CD 1.618–2.618, AD 0.886 |
| Alternate Bat | AB 0.382, CD 2.0–3.618, AD 1.13 |
| Butterfly | AB 0.786, CD 1.618–2.618, AD 1.272 |
| Crab | AB 0.382–0.618, CD 2.24–3.618, AD 1.618 |
| Deep Crab | AB 0.886, CD 2.0–3.618, AD 1.618 |
| Cypher | AB 0.382–0.618, XC 1.272–1.414, D 0.786 of XC |
| Shark | AB 1.13–1.618, BC 1.618–2.24, AD 0.886–1.13 |
| 5-0 | AB 1.13–1.618, BC 1.618–2.24, CD 0.50 |
| AB=CD | CD ≈ AB, BC 0.382–0.886 |
| Three Drives | Six pivots; retracements 0.618–0.786, extensions 1.272–1.618 |

4. **Output.** Each completion produces a marker at D. The latest 12 patterns are also drawn as X-A-B-C-D legs, with dashed X-B-D and A-C guides.
5. **Strategy.** A bullish completion is long for *Hold bars* (default 10), filled at the next open.

Pivots are confirmed only after the reversal threshold is crossed. D is therefore known a few bars after it prints, and the strategy enters on the completion bar as detected in hindsight. This makes harmonic backtests optimistic; the user guide states this limit.

### 6.3 Interpretation and swing plan (`explain.py`)

**Per-study readings.** Each study belongs to a family, and each family has a reader:

| Family | Reading |
| --- | --- |
| Moving average | Distance from close (%, ATR), 5-session slope, uptrend/pullback/downtrend wording |
| Band/channel | Position in band (%), squeeze from one-year width percentile |
| Trailing stop | Above/below, distance in ATR, used as an exit level |
| Bounded oscillator | Zone (e.g. RSI 30/70), direction, signal cross, one-year percentile |
| Zero-line oscillator | Sign, zero or signal crosses, momentum building or fading (MACD has its own wording) |
| Volatility | One-year percentile: compression or expansion, plus ATR in rupees |
| Cumulative volume | 20-session direction against price: confirmation or divergence |
| Money flow / volume | Accumulation or distribution; volume against its 20-day average |
| Trend tools | ADX/DI, Aroon, Vortex, Choppiness, Mass, Ichimoku cloud, EMA ribbon stack, pivots |
| Harmonics | Latest pattern, ratios, status (fresh, working, played out, failed, stale), 0.382 and 0.618 CD targets, invalidation 1 ATR beyond D, and this stock's past hit rate |

**Technical rating.** A vote in the style of TradingView's public technical-ratings method. Moving averages (SMA and EMA 10/20/30/50/100/200, Ichimoku base, HMA 9) vote buy when price is above. Oscillators (RSI, Stochastic, CCI, ADX/DI, Awesome, Momentum, MACD, Williams %R, Ultimate) vote buy, sell, or neutral by their usual rules. The scores average to Strong sell … Strong buy.

**Bias score.** Points for close vs SMA 50, SMA 50 vs SMA 200, RSI ≥55 or ≤45, MACD histogram sign and direction, the technical rating, and a fresh harmonic. A score ≥ 2 is Bullish and ≤ −2 is Bearish.

**Setup selection.**

```mermaid
flowchart TD
  A{Fresh bullish harmonic<br/>and bias not bearish?} -- yes --> H[Harmonic reversal long]
  A -- no --> B{Bias}
  B -- Bearish --> N[No long setup: stand aside]
  B -- Neutral --> R[Range: buy near 20-day low]
  B -- Bullish --> C{Close > EMA20 + 2 ATR?}
  C -- yes --> W[Extended: wait for pullback]
  C -- no --> D{Within 0.5 ATR of 20-day high?}
  D -- yes --> K[Breakout long]
  D -- no --> P[Pullback long]
```

Every long plan has an entry, a stop, T1 ≈ 1.5R and T2 ≈ 3R (or pattern targets), a 1%-risk position size, and a 10–15 session time stop.

**Historical odds.** The same plan is replayed on every past bar of that stock where the trend state matched. Pullback and breakout plans also require RSI within ±8; every plan also requires its own setup condition. Each replay enters at the close, uses the same stop in ATR multiples and the same target in R, and looks up to 15 sessions ahead. A bar that touches both stop and target counts as a loss. Replays are spaced at least five bars apart. The pane reports the count, hit rate, and average R. A **base rate** adds the 10-session forward-return distribution after sessions in the same trend state with RSI within ±5.

These are descriptive statistics about one stock's own past. They are not out-of-sample forecasts and do not account for regime change.

### 6.4 Fundamentals

`GET https://www.screener.in/company/{SYMBOL}/consolidated/`, with a polite user agent and a 6-hour in-memory cache. The parser reads `#top-ratios` name/value pairs and the `.pros` and `.cons` lists. No login or scraping beyond the public page.

## 7. Key decisions

| Decision | Why | Trade-off |
| --- | --- | --- |
| DuckDB file, not a server database | Zero setup, fast columnar reads, single file | One writer at a time, so writes are serialized |
| Pin `duckdb==1.1.3` | Newer builds and NumPy 2 crash with `Illegal instruction` on CPUs without SSE4.2/POPCNT (the reference machine) | Misses newer DuckDB features; no Python 3.14 wheels |
| Own `arrays.py` instead of NumPy | Same reason; keeps the dependency list to one package | Slower than NumPy, but fine for ~1,250 bars per stock |
| Standard-library HTTP server | No framework to install; easy to test with `build_server()` | No HTTP/2, no auth, single host |
| Vendored Lightweight Charts | Looks and feels like TradingView; Apache-2.0; no CDN needed | Library upgrades are manual |
| Compute on request | Always consistent with stored bars; no cache invalidation | A universe scan takes seconds (Nifty 50) to about two minutes (200 BSE names) |
| Long/flat only | Matches NSE cash-market delivery rules | No short strategies |
| REA not used to clone TradingView | Reverse engineering a commercial product was out of scope and unnecessary given an open-source chart library | — |

## 8. Performance (reference machine, older x86 laptop)

| Operation | Time |
| --- | --- |
| `/api/bars` for one stock | ~70 ms |
| All 152 studies on one stock | ~6 s total |
| Backtest Nifty 50 for a creator strategy | 4–13 s (RSI-PCA ~35 s) |
| `/api/explain` with a few studies | ~0.6 s |
| Backtest Nifty 50 (one harmonic strategy) | ~6 s |
| Full `python -m top.verify` | ~15 s |
| Breadth over ~2,300 BSE A/B stocks (first time after new bars) | ~11 s |
| All eight scans (first time after new bars, then cached) | ~23 s, then < 0.1 s |
| Portfolio backtest, BSE group A (704 names, first load, then cached) | ~8 s, then ~1 s |
| Walk-forward (5 settings) | ~0.5–3 s |
| All 92 strategies on one symbol (leaderboard) | ~7 s; ~5 h for every script on 2 cores |
| First full sync (network bound) | 1–2 min |

## 9. Security

- Binds `127.0.0.1` by default. There is no authentication, so do not expose it publicly without a proxy that adds access control.
- Static file serving resolves paths and refuses anything outside `top/web/`; this is covered by tests.
- Symbol and strategy inputs are checked against the catalogs before any computation or database access. Bar queries are parameterized.
- Outbound calls go only to Yahoo Finance, the NSE and BSE archives, and Screener.in.
- Front-end text from the server and from Screener.in is HTML-escaped before rendering.

## 10. Testing and verification

| Layer | What runs | Where |
| --- | --- | --- |
| Unit | Catalog sizes; every study has a latest value; EMA seeding regression; every strategy backtests; next-open fill; synthetic Gartley; harmonic drawings ordered; parser; rating labels; readings for every family; swing plan for all 50 | `tests/test_engine.py` |
| Research | New strategies are causal; sizing modes; Kelly; Monte Carlo; walk-forward; split-adjusted SQL equals `load_bars`; breadth, regime, sectors and every scan; portfolio month ends, holdings and no look-ahead; delivery and FII/DII parsers; ticker map | `tests/test_research.py` |
| Leaderboard | Index parsing and sync; fast metrics equal `run()` for every strategy; ratio floor; PSR/DSR maths; ranking, filters, CSV; incremental strategy additions; data-quality gate | `tests/test_leaderboard.py` |
| Integration | Real server on a free port: static files, path traversal, health, status, symbols, `M&M` bars, catalogs, studies with drawings, backtest, trend, scan, explain, verify | `tests/test_api.py` |
| Self-check | Named hooks on live data | **Verify** button, `/api/verify`, `python -m top.verify` |
| CI | Python 3.10–3.13 tests; wheel contents check; installed-wheel server smoke test | `.github/workflows/ci.yml` |

The tests are offline. They seed a temporary DuckDB with deterministic synthetic bars for all 50 names.

## 11. Known limits and future work

- Daily bars only. Intraday data would need a different source and storage layout.
- Harmonic detection confirms pivots in hindsight (see §6.2), so harmonic backtests are optimistic.
- No slippage model, taxes, or position-sizing variants in backtests.
- Screener.in layout changes would break the parser; the parser test and Verify will flag it.
- The leaderboard tests 92 strategies on thousands of scripts in-sample, so the top rows are inflated by selection bias. Walk-forward or out-of-sample ranking would be the next step.
- BSE index history starts in April 2025 because older BSE index files are not published.
- Possible next steps: walk-forward testing, saved layouts, alerts, F&O data for short setups, and a desktop wrapper.
