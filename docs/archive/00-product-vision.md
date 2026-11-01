# Product vision

## Requested outcome

Build a research workstation around public market-data and backtesting projects, then make every major part testable in a browser.

The requested scope grew in this order:

1. Review `https://github.com/ranaroussi/yfinance` and write an HTML design with SVG block and sequence diagrams.
2. Turn that design into a desktop app with the features named in the HTML.
3. Limit the symbol universe to NSE and BSE.
4. Add backtesting for more than one strategy.
5. Use repositories in the same class as QuantJourney Backtester as the research frame.
6. Include `https://github.com/zixuan0104/investment-system`.
7. Stitch the shared repositories into one workflow.
8. Integrate the investment system, TradingView MCP, and REA.

## Product boundary

The app is a historical research tool. It is not a broker, an order router, or a promise of future returns.

Kept out of the product:

- Live order placement
- Broker connections
- X scraping and the unrelated scraper files that appeared in the session
- Copying third-party repository source into this project
- Decompiling TradingView or any other shipped commercial client
- Applying A-share settlement rules to Indian symbols without an explicit adaptation

## Intended system

```text
NSE/BSE universe
  -> history and quality gate
  -> factor screen
  -> parameter screen
  -> allocation
  -> auditable backtest
  -> single-name check
  -> paper review
  -> audit packet
```

External systems stay behind adapters:

- yfinance for history and symbol lookup
- QuantJourney Backtester for the auditable research contract
- vectorbt, backtesting.py, bt, and Backtrader for specialized research roles
- investment-system for screening, backtest, paper, and audit patterns
- official TradingView MCP for authenticated read-only context

## Gap

The current build is a design prototype and a local sample workflow. It does not yet run the external engines, authenticate TradingView, or provide the desktop application. That is much less than the requested system.
