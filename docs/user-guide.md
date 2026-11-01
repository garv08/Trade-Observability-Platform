# 🧑‍💻 User guide

A walkthrough of every part of TOP. The same guide is built into the app: click **Guide** in the top bar, or open `http://127.0.0.1:8000/guide.html`.

- [The screen](#the-screen)
- [Pick a stock](#pick-a-stock)
- [Indicators and durations](#indicators-and-durations)
- [Scott Carney harmonics](#scott-carney-harmonics)
- [Darvas boxes and breakouts](#darvas-boxes-and-breakouts)
- [Interpretation and swing plan](#interpretation-and-swing-plan)
- [Backtesting](#backtesting)
- [YouTube creator strategies](#youtube-creator-strategies)
- [Analysis buttons](#analysis-buttons)
- [Shareable links](#shareable-links)
- [Keyboard and tips](#keyboard-and-tips)

---

## The screen

![Main screen](images/overview.png)

| Area | What it holds |
| --- | --- |
| **Top bar** | Selected stock, price and day change, `DuckDB 50/50` coverage, **Guide**, **Sync history** |
| **Left panel** | Every control, as searchable dropdowns: **Stock**, one dropdown per **indicator section**, **On the chart** (active studies and their settings), **Backtest** (strategy, settings, capital, cost), **Analysis** buttons |
| **Chart** | Candles, volume, overlays on price, oscillator panes, range buttons 6M · 1Y · 2Y · 5Y · All |
| **Interpretation** | Plain-English reading of your selections and a swing plan |
| **Output panel** | Results of Harmonics list, Trend scan, Backtest universe, Fundamentals, Verify; **Close** returns the space to the chart |
| **Backtest results** | Metrics, equity curve, and trades; collapsed until your first backtest |

Nothing is drawn over the chart; panels stack below it. In windows narrower than 720 px the left panel becomes a drawer opened with **Controls**.

---

## Pick a stock

**Universe chips** above the Stock box choose what the dropdown and **Backtest universe** cover:

| Chip | What's in it | Source |
| --- | --- | --- |
| **Nifty 50** | The 50 index stocks | Yahoo, adjusted for splits and dividends |
| **ETFs** | ~355 NSE ETFs and ~35 BSE-only ETFs | Exchange bhavcopies, split adjusted |
| **BSE** | ~4,700 BSE equities, grouped by BSE group (A, B, T, X, …) | BSE bhavcopies, split and bonus adjusted |
| **All** | Everything | |

The ETF, BSE, and All chips appear once you've run **Sync history** (or `top-sync --bhav`). Symbols for these universes carry an exchange prefix, for example `BSE:ABB` or `NSE:NIFTYBEES`.

1. Click the **Stock** box, or press <kbd>/</kbd> anywhere.
2. Type a symbol, a company name, or a sector, for example `infy`, `mahindra`, `pharma`, `energy`, or `financ bank`. Every word must match.
3. Use <kbd>↑</kbd> <kbd>↓</kbd> and <kbd>Enter</kbd>, or click. The list is grouped by sector, ETF type, or BSE group, and shows each stock's last price and day change. Typing searches every universe by name, symbol, or BSE code (for example `suzlon` or `500325`), whichever chip is on; exact symbol matches come first, and picking a name from another universe switches the chip. Long lists show the first 150 matches; keep typing to narrow them.

Your studies stay on when you switch stocks.

---

## Indicators and durations

There are **148 studies** in 10 searchable dropdowns: Harmonics, @neurotrader888, @UnbiasedTradingGoshawk, Moving averages, Bands and channels, Trend, Momentum, Volatility, Volume, and Price statistics. They are listed in full in the [indicator catalog](indicators.md).

- **Add or remove**: pick a study in its dropdown. The list stays open so you can add several, and ✓ marks the ones that are on.
- **Overlay or Pane**: overlays draw on price; panes open below the chart.
- **Change the period**: under **On the chart**, click a preset (5 · 9 · 10 · 14 · 20 · 21 · 30 · 50 · 100 · 150 · 200) or type any value.
- **Same average, several periods**: **+ Another** adds a copy at the next classic period (9 → 20 → 50 → 100 → 200). For example, SMA 20 + SMA 50 + SMA 200. Each copy has its own line, colour, settings, and Interpretation card.
- **Bands are shaded**: any study with upper and lower lines (Bollinger, Keltner, Donchian, envelopes, ATR bands, StdDev channel, Darvas box, breakout range, auto trendlines) is filled light grey beneath the candles.
- **EMA ribbon**: five adjustable lengths (default 8, 13, 21, 34, 55).

---

## Scott Carney harmonics

![Harmonics](images/harmonics.png)

**Carney all harmonics** is on by default for every stock. It finds swings with a zigzag (Swing %, default 3) and matches each run of X-A-B-C-D pivots against Carney's ratios (Tolerance, default ±0.05).

| On the chart | Meaning |
| --- | --- |
| Solid green or red legs | X-A-B-C-D of the latest 12 patterns (green bullish, red bearish) |
| Dashed lines | X-B-D and A-C ratio guides |
| Letters | Pivot labels |
| Arrow at D | Completion: the potential reversal zone (PRZ) |

**Harmonics list** (under Analysis) shows each pattern's D date, name, side, PRZ, and measured AB/BC/CD/AD ratios. To show one pattern only, pick it from the Harmonics dropdown and remove *Carney all harmonics*.

Patterns: Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab, Cypher, Shark, 5-0, AB=CD, and Three Drives.

---

## Darvas boxes and breakouts

![Darvas and breakouts](images/darvas-breakout.png)

**Darvas box** (Bands and channels)
- Top: a high not exceeded for 3 sessions. Bottom: a low not undercut for 3 sessions after the top.
- The box is drawn and shaded from the day it is confirmed.
- Markers: **Darvas breakout** (close above the top) and **Box broken** (close below the bottom).

**Breakout & trend detector** (Trend)
- Shades the prior 20-session range.
- **Breakout** / **Breakdown**: a close beyond the range on at least 1.5× average volume.
- **Failed breakout**: back inside the range within 3 sessions.
- After a breakout, a trailing stop (best close − 3 ATR) follows the trend; **Trend ended** marks where it was hit.

Matching strategies: **Darvas box breakout** and **Volume breakout trend** in the Breakout group.

---

## Key levels and pattern breakouts

Two **Trend** studies follow the way the X account [@TradZoo](https://x.com/TradZoo) writes its daily chart posts. Only the method was studied; TOP computes every level itself.

![Infosys with key levels and a falling wedge breakout](images/key-levels.png)

**Key levels plan (next session)** draws today's four levels as flat lines across the last 30 sessions (*Draw over*): outer resistance R2 and inner resistance R1 in red, inner support S1 and outer support S2 in green. The Interpretation pane writes the plan for the next session, for example:

> Long above 1,175–1,178, targets 1,185 1,195 1,205+. Below 1,152 the bias turns weak, downside 1,135 1,118 1,098−. Outer resistance 1,204, outer support 1,099.

- **R1 and S1** are the nearest support and resistance levels just around the close. They come from clustered swing highs and lows plus the last few sessions' extremes.
- **R2 and S2** are the next levels out.
- The three targets step from the trigger to the outer level and are rounded to a sensible price step (about 0.2% of price).
- Markers show where price closed through a trigger in the last 10 sessions.

**Pattern breakout projector** fits support and resistance lines over the last 60 bars, shades the pattern grey, and names it: falling or rising wedge, ascending, descending, or symmetrical triangle, channel, range, or broadening wedge. On a daily close through resistance it writes:

> Falling wedge breakout on 2026-10-14 above 1,084. Buying zone 1,084–1,098, stop below 990, target 1 1,195, target 2 1,300 (pattern height 217 projected from the breakout). Status: in play.

It also reports how often this stock's past breakouts reached target 2.

Matching strategies in the Breakout group: **Key level breakout** and **Pattern breakout (measured move)**.

## Interpretation and swing plan

The pane under the chart refreshes whenever you change anything on the left.

**Left half: swing outlook**
- **Headline**: close, day change, and why the stock reads as an uptrend, range, or downtrend.
- **Badges**: swing bias, a technical rating (votes from 14 moving averages and 9 oscillators), and the MA and oscillator sub-ratings.
- **Swing plan**: one of *harmonic reversal*, *breakout*, *pullback in an uptrend*, *extended — wait*, *range*, or *no long setup*. It gives a trigger, entry, stop, T1 (~1.5R), T2 (~3R), position size for 1% risk of your capital, and a time stop. The levels are drawn on the chart as dashed lines.
- **Same plan on this stock's past**: how often T1 was hit before the stop, and the average R.
- **Base rate**: how often the stock was higher 10 sessions after similar conditions.

**Right half: what your selections say**: one card per study and the selected strategy, with the latest change highlighted. **What is this?** explains each tool.

> [!NOTE]
> The odds describe this stock's own history. They are not a forecast or advice.

---

## Backtesting

![Backtest](images/backtest.png)

1. Pick a stock.
2. In **Backtest**, search a strategy (for example `gartley`, `darvas`, `breakout`, `rsi`, or `@neuro`). There are 86, listed in the [strategy catalog](strategies.md).
3. Adjust its settings, **Capital** (default ₹10,00,000), and **Cost bps** (default 5).
4. Click **Run backtest**.

| Rule | Detail |
| --- | --- |
| Positions | Long or flat; never short |
| Fills | Signal at the close, fill at the next session's open |
| Costs | Basis points on entry and on each exit |
| Benchmark | Buy and hold from the same first bar |

Results show Return, CAGR, Max DD, Buy & hold, Sharpe, Sortino, Win rate, Profit factor, Trades, Avg trade, Exposure, and Ending equity, plus the equity curve and every trade.

**Backtest universe** (labelled *Backtest Nifty 50*, *Backtest ETFs*, *Backtest BSE*, or *Backtest all*) runs the selected strategy on the current universe and ranks the results. For ETFs, BSE, and All, it uses the 200 most traded names over the last ~45 days, so a scan takes 1–2 minutes.

---

## YouTube creator strategies

![Creator strategies and Backtest universe](images/creators-scan.png)

| Group | Strategies | Indicators |
| --- | --- | --- |
| **@neurotrader888** | Directional-change trend, ATR zigzag, trendline breakout, inverse head and shoulders, bull flag/pennant, Hawkes volatility breakout, CMMA vs Nifty proxy, Donchian + last-trade filter, RSI-PCA forecast | Zigzag, auto trendlines, Hawkes volatility, VSA, CMMA, permutation entropy |
| **@UnbiasedTradingGoshawk** | Connors RSI(2), Connors Double 7s, AHL-style EWMAC trend, Lo–Khandani contrarian | EWMAC forecast, return vs Nifty proxy |

Picking one shows its creator, a confidence label (HIGH = from the creator's own code; MEDIUM = from the original public source), source links, and how it was adapted. Details and first results are in [creators.md](creators.md).

---

## Analysis buttons

| Button | What it does |
| --- | --- |
| **Harmonics list** | Lists the drawn Carney patterns with ratios |
| **Trend scan** | Runs every Trend, Breakout, and Trend reversal rule on the selected stock; rules that are long now are listed first |
| **Fundamentals** | Screener.in ratios (market cap, P/E, ROCE, ROE, …) and pros/cons, cached for 6 hours. BSE stocks are looked up by scrip code; ETFs have no fundamentals |
| **Verify** | Runs every browser and server self-check and lists Pass/Fail |

---

## Shareable links

Any set-up can be opened from a URL, which is handy for bookmarks and sharing:

| Parameter | Example | Meaning |
| --- | --- | --- |
| `symbol` | `symbol=INFY`, `symbol=BSE:ABB`, `symbol=NSE:NIFTYBEES` | Stock or ETF to open |
| `universe` | `universe=bse` | `nifty50`, `etf`, `bse`, or `all` |
| `studies` | `studies=sma:20,sma:50,sma:200,bbands` | Studies to add; `id:period` sets the period |
| `carney` | `carney=0` | Turn off the default harmonics |
| `strategy` | `strategy=darvas_breakout` | Pre-select a strategy |
| `range` | `range=252` | 126 (6M), 252 (1Y), 504 (2Y), 1260 (5Y), or `all` |
| `run` | `run=backtest` | Also `trend`, `scan`, `harmonics`, `fundamentals`, `verify` |
| `menu` + `q` | `menu=stock&q=bank` | Open a dropdown with a search |

Examples:

```text
http://127.0.0.1:8000/?symbol=ICICIBANK&studies=sma:20,sma:50,sma:200,bbands&range=252
http://127.0.0.1:8000/?symbol=INFY&carney=0&studies=darvas,breakout_trend&range=126
http://127.0.0.1:8000/?symbol=TCS&strategy=ut_ahl_trend&run=backtest
http://127.0.0.1:8000/?strategy=harm_gartley&run=scan
```

Study and strategy IDs are listed in the [indicator](indicators.md) and [strategy](strategies.md) catalogs.

---

## Keyboard and tips

| Key | Action |
| --- | --- |
| <kbd>/</kbd> | Jump to the Stock search |
| <kbd>↑</kbd> <kbd>↓</kbd> <kbd>Enter</kbd> | Move and pick in any dropdown |
| <kbd>Esc</kbd> | Close a dropdown |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd> | Hard-reload after an update |

- **Hide** on the Interpretation pane or Backtest results gives the chart more room.
- If the chart looks busy, remove *Carney all harmonics* or pick a single pattern.
- Refresh data after market close with **Sync history** or `top-sync`.
