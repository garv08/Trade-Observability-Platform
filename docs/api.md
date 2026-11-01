# TOP HTTP API

Base URL: `http://127.0.0.1:8000`. All responses are JSON unless noted. Errors look like `{"error": "message"}` with status 400 (bad input), 404 (unknown route or symbol), or 500.

Symbols are NSE codes from `/api/symbols`. URL-encode them in query strings: `M&M` becomes `M%26M`.

## GET routes

### `GET /api/health`

```json
{"ok": true, "universe": 50}
```

### `GET /api/status`

Sync state and store coverage.

```json
{
  "sync": {"syncing": false, "done": 50, "total": 50, "errors": [], "last_sync": "2026-10-31T21:40:12+05:30", "message": "ready"},
  "coverage": {"symbols_with_bars": 50, "bars": 61353, "first": "2021-11-01", "last": "2026-10-30"}
}
```

### `GET /api/symbols`

```json
{"symbols": [
  {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy", "weight": 8.49, "rank": 1, "yahoo": "RELIANCE.NS",
   "exchange": "NSE", "kind": "stock", "universe": "nifty50", "code": "RELIANCE", "group": null,
   "last": 1164.9, "change_pct": -0.21, "as_of": "2026-10-30"},
  {"symbol": "BSE:ABB", "name": "Abb India Limited", "sector": "BSE group A", "exchange": "BSE", "kind": "stock",
   "universe": "bse", "code": "500002", "group": "A", "last": 6403.0, "change_pct": -1.94, "as_of": "2026-10-30"},
  {"symbol": "NSE:NIFTYBEES", "name": "NIP IND ETF NIFTY BEES", "sector": "EQUITY", "exchange": "NSE", "kind": "etf",
   "universe": "nse_etf", "code": "NIFTYBEES", "group": "ETF", "last": 262.89, "change_pct": 0.39, "as_of": "2026-10-30"}
]}
```

### `GET /api/bars?symbol=INFY`

Works for any listed symbol, for example `symbol=BSE%3AABB` or `symbol=NSE%3ANIFTYBEES`. Bhavcopy bars are returned split/bonus adjusted.

```json
{"symbol": "INFY", "interval": "1d",
 "bars": [{"time": "2026-10-30", "open": 1149.1, "high": 1185.0, "low": 1147.9, "close": 1185.0, "volume": 13030713}]}
```

### `GET /api/indicators`

The study catalog. `pane` is `price` (overlay) or `osc` (own pane).

```json
{"sections": ["Harmonics", "Moving averages", "..."], "count": 148,
 "indicators": [{"id": "sma", "name": "SMA", "section": "Moving averages", "pane": "price",
                 "params": [{"key": "length", "label": "Length", "type": "number", "default": 20, "min": 2, "max": 400, "step": 1}],
                 "outputs": ["sma"]}]}
```

### `GET /api/strategies`

```json
{"count": 88, "strategies": [{"id": "sma_cross", "name": "SMA cross", "section": "Trend",
  "blurb": "Long when the fast SMA is above the slow SMA.", "params": [{"key": "fast", "default": 20, "...": "..."}]}]}
```

### `GET /api/fundamentals?symbol=INFY`

Fetched from Screener.in on demand and cached for 6 hours.

```json
{"symbol": "INFY", "source": "Screener.in public company page", "url": "https://www.screener.in/company/INFY/consolidated/",
 "ratios": [{"label": "Stock P/E", "value": "15.2"}], "pros": ["Company is almost debt free."], "cons": ["..."],
 "note": "Machine-written pros and cons come from Screener.in. This is not advice and not a filing."}
```

### `GET /api/verify`

Runs every named check in-process.

```json
{"ok": true, "hooks": [{"name": "duckdb universe", "ok": true, "detail": "50/50"}]}
```

## POST routes

Send `Content-Type: application/json`.

### `POST /api/sync`

```json
{"what": "all"}
```

`what` is `nifty` (Yahoo, Nifty 50), `bhav` (BSE stocks and ETFs from bhavcopies), or `all` (default). Starts background downloads and returns the current state immediately; poll `/api/status`, whose `sync.bhav` holds `done`, `total`, `message`, and `last_day` for the bhavcopy sync.

### `POST /api/studies`

```json
{"symbol": "INFY", "studies": [{"id": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}, {"id": "carney", "params": {}}]}
```

Response. Series are aligned to `time`; `null` means no value yet.

```json
{"symbol": "INFY", "time": ["2021-11-01", "..."],
 "studies": [
   {"id": "macd", "name": "MACD", "pane": "osc", "series": {"macd": [null, "..."], "signal": ["..."], "hist": ["..."]}, "markers": [], "drawings": []},
   {"id": "carney", "name": "Carney all harmonics", "pane": "price", "series": {},
    "markers": [{"time": "2022-02-14", "position": "belowBar", "color": "#089981", "shape": "arrowUp", "text": "Bull AB=CD"}],
    "drawings": [{"name": "Gartley", "side": "bull", "color": "#089981", "time": "2026-05-14", "prz": 1462.1,
                  "ratios": {"ab": 0.62, "bc": 0.71, "cd": 1.41, "ad": 0.79},
                  "legs": [{"time": "2026-03-02", "value": 1530.0, "label": "X"}, "..."],
                  "guides": [["X, B, D points (same objects as legs)"], ["A, C points"]]}]}
 ]}
```

### `POST /api/backtest`

```json
{"symbol": "TCS", "strategy": "sma_cross", "params": {"fast": 20, "slow": 50}, "capital": 1000000, "cost_bps": 5}
```

```json
{"symbol": "TCS", "strategy": "sma_cross", "start": "2022-01-12", "end": "2026-10-30",
 "equity": [{"time": "2022-01-12", "value": 1000000.0}], "benchmark": ["..."],
 "trades": [{"entry": "2022-01-13", "exit": "2022-02-09", "entry_px": 1673.91, "exit_px": 1524.53, "shares": 597.106,
             "pnl": -90149.29, "return_pct": -9.01, "bars": 18, "open": false}],
 "metrics": {"total_return_pct": 12.3, "cagr_pct": 2.5, "max_drawdown_pct": -18.1, "sharpe": 0.31, "sortino": 0.44,
             "win_rate_pct": 41.2, "profit_factor": 1.18, "trades": 17, "closed_trades": 16, "avg_trade_pct": 0.9,
             "exposure_pct": 58.3, "buy_hold_pct": 20.4, "ending_equity": 1123000.0},
 "methodology": "Signal at the close. Fill at the next session open. ..."}
```

### `POST /api/trend`

Every Trend, Breakout, and Trend reversal strategy on one stock.

```json
{"symbol": "INFY", "capital": 1000000, "cost_bps": 5}
```

```json
{"symbol": "INFY", "note": "...", "rows": [{"id": "pullback_ema", "name": "Pullback to EMA 20", "section": "Trend", "blurb": "...",
  "in_position": true, "return_pct": 16.39, "max_drawdown_pct": -13.38, "trades": 38, "buy_hold_pct": -28.17}]}
```

### `POST /api/scan`

One strategy across a universe, sorted by return. `universe` is `nifty50` (default; all 50), `etf`, `bse`, or `all`. The larger universes scan the `limit` (default 200, max 1000) most traded names over the last ~45 days; `note` says so.

```json
{"strategy": "harm_gartley", "params": {}, "capital": 1000000, "cost_bps": 5, "universe": "bse", "limit": 200}
```

```json
{"strategy": "harm_gartley", "rows": [{"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ", "in_position": false,
  "return_pct": 15.48, "max_drawdown_pct": -1.89, "trades": 1, "buy_hold_pct": 154.93}]}
```

### `POST /api/explain`

Plain-language readings and a swing plan. `focus` puts that item first.

```json
{"symbol": "ICICIBANK", "studies": [{"id": "rsi", "params": {}}], "strategy": {"id": "supertrend", "params": {}},
 "capital": 1000000, "cost_bps": 5, "focus": "rsi"}
```

```json
{
  "symbol": "ICICIBANK",
  "headline": "ICICIBANK closed at ₹1,398.00 (+0.8%) on 2026-10-30. Overall it looks like an uptrend: ...",
  "snapshot": {"close": 1398.0, "day_pct": 0.82, "date": "2026-10-30", "atr": 24.9, "atr_pct": 1.8, "rsi": 57.0,
               "sma50": 1370.2, "sma200": 1301.5, "ema20": 1376.5, "hi52": 1500.0, "lo52": 1180.0, "vol_ratio": 0.9},
  "rating": {"ma": {"score": 0.86, "label": "Strong buy", "buy": 13, "sell": 1, "neutral": 0},
             "osc": {"score": 0.11, "label": "Buy", "buy": 3, "sell": 2, "neutral": 4},
             "overall": {"score": 0.49, "label": "Buy"}},
  "plan": {"bias": "Bullish", "score": 4, "setup": "Pullback long in an uptrend", "reasons": ["..."], "trigger": "...",
           "entry": 1406.15, "stop": 1356.4, "t1": 1480.77, "t2": 1555.39, "risk": 49.75, "risk_pct": 3.54, "r1": 1.5, "r2": 3.0,
           "shares": 201, "exposure": 282636.15, "capital_risk": 9999.75,
           "odds": {"n": 94, "win": 44.7, "expectancy": 0.01},
           "base": {"n": 224, "horizon": 10, "up": 53.6, "median": 0.41, "p25": -1.57, "p75": 2.22},
           "steps": ["Wait for ...", "Entry around ...", "..."]},
  "harmonic": {"kind": "harmonic", "title": "Carney all harmonics", "now": "...", "pattern": {"side": "bull", "d": 1290.0, "t1": 1330.0, "t2": 1355.0, "stop": 1265.0, "bars": 40, "fresh": false}},
  "items": [{"kind": "study", "id": "rsi", "title": "RSI", "section": "Momentum", "what": "...", "now": "RSI reads 57.0 (rising) ...", "tone": "bull"}],
  "disclaimer": "Rule-based reading of delayed daily data. ... Not investment advice."
}
```

`tone` is one of `bull`, `bull-hot` (bullish but stretched), `bear`, `bear-cold`, or `neutral`. `plan.entry` and the levels after it are absent for "No long setup".

## Static routes

| Path | Content |
| --- | --- |
| `/` | The app (`top/web/index.html`) |
| `/guide.html` | User guide |
| `/app.js`, `/styles.css`, `/vendor/…` | Front-end assets |

Paths outside `top/web/` return 404.
