# NSE research desk

Local charting desk for the 50 Nifty names. It is not the commercial TradingView product and it does not place orders.

## Run

```bash
cd /home/dell/projects/finance-desktop
.venv/bin/python -m terminal.server
```

Open `http://127.0.0.1:8000`. The first start fills `data/nse.duckdb` from Yahoo Finance public daily chart data. Use **Sync history** to refresh.

## What you can do

- All controls sit in the left panel as searchable dropdowns: Stock, one dropdown per indicator section (Harmonics first, then Trend and the rest), the backtest strategy, and the analysis buttons. The chart fills the rest of the screen. The full user guide is at `/guide.html` (**Guide** in the top bar).
- Pick any of the 50 names by symbol, company, or sector, and move the chart range.
- Add studies from the section dropdowns (136 indicators, grouped in sections, including a Harmonics section). Overlays sit on price; oscillators open their own pane. Harmonic studies mark completions on the candles.
- Pick a strategy, set capital and cost, and run a backtest. Fills are the next session open. **Backtest 50** runs that rule on every name.
- **Trend scan** runs the trend, breakout, and reversal rules on the selected name in one click.
- **Fundamentals** reads the public Screener.in company page for that symbol.
- Harmonics are Scott Carney ratio rules (Gartley, Bat, Alternate Bat, Butterfly, Crab, Deep Crab, Cypher, Shark, 5-0, AB=CD, Three Drives). They are research approximations, not the Harmonic Trader product. Each pattern can be backtested.
- **Carney all harmonics** is on by default for every stock you pick. The latest 12 patterns are drawn as X-A-B-C-D legs, with dashed X-B-D and A-C lines and an arrow at D. Every completion gets a marker. **Harmonics** lists date, pattern, side, PRZ, and ratios. Defaults are a 3% zigzag swing and 0.05 ratio tolerance. Remove the study from the active list to turn it off for the session.

- **Interpretation** pane under the chart: plain-English reading of every selected study and strategy, a technical rating, a swing plan (entry, stop, targets, size) drawn on the chart, and how the same plan did on the stock's own history. Served by `POST /api/explain` (`terminal/explain.py`).

## Checks

`Verify` on the desk, or:

```bash
.venv/bin/python -m terminal.verify
```

## Notes

- DuckDB is pinned to 1.1.3. Newer DuckDB and current NumPy wheels are not usable on this CPU.
- Chart drawing uses TradingView Lightweight Charts, MIT, vendored under `vendor/`.
- Adjusted prices. This is research output, not a live NSE feed and not a broker.
