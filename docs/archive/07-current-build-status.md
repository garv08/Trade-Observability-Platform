# Current build status

Recorded after the browser prototype, framework catalog, workflow packet, and integration notes.

## Working now

The live desk is no longer the static mock. Run `.venv/bin/python -m terminal.server` and open `http://127.0.0.1:8000`.

- DuckDB history for the Nifty 50 at `data/nse.duckdb` (pin `duckdb==1.1.3`; newer wheels crash on this CPU)
- Daily adjusted bars from Yahoo public chart data, synced into the local database
- TradingView Lightweight Charts (MIT), vendored at `vendor/lightweight-charts.standalone.production.js`
- 124 sectioned indicators and 55 long/flat strategies with an in-browser next-open backtest
- The earlier static page is kept in `prototype/`

Still not a broker, not a live NSE feed, and not the commercial TradingView client. Prices are delayed public data.

- Static research page with SVG architecture and sequence diagrams
- NSE/BSE sample watchlist and symbol normalization
- Browser-side quality labels, CSV download, and JSON snapshot download
- Framework catalog with external repository links
- Nine-stage local workflow animation and research packet
- TradingView connector JSON with a read-only tool policy
- One successful direct history probe for `RELIANCE.NS`

## Not working

- PySide6 desktop application
- Installed yfinance, pandas, or PySide6 environment
- Live history in the visible table
- Real factor screening across an NSE/BSE master list
- Execution of QuantJourney, vectorbt, backtesting.py, bt, or Backtrader
- Authenticated TradingView MCP calls
- Paper ledger, trade blotter, drawdown, or walk-forward results
- REA runtime or evidence bundle

## Environment blockers already observed

- `python3 -m venv` failed because `ensurepip` was unavailable.
- System package installation required a sudo password.
- System pip was absent, and Debian's externally managed environment blocked a user install.
- Workspace attachment to `/home/dell/projects/finance-desktop` failed once because the directory was not present at that moment. The directory was created afterward and the prototype files were written there.

## Next build, if continued

1. Add a standard-library research server that uses the verified Yahoo chart probe for `.NS` and `.BO` symbols only.
2. Replace sample table rows with that server's history, quality result, and error state.
3. Implement transparent local strategies and report trades, equity, and drawdown without calling a broker.
4. Keep external engines as optional adapters after their licenses and installs are confirmed.
5. Leave TradingView calls unauthenticated until the user completes OAuth.
6. Do not add order placement or REA decompilation to close the product gap.
