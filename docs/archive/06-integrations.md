# Integrations

## Investment system

Repository: `https://github.com/zixuan0104/investment-system`

Integrated as a reference architecture only. The useful boundary is:

- quantitative screening
- historical backtest
- paper-state review
- auditable harness output

Not integrated:

- LLM evidence chain
- supply-chain graph
- A-share trading constraints
- Streamlit dashboard
- any code copied from the repository

## TradingView MCP

Official documentation: `https://www.tradingview.com/mcp/docs`

Server URL: `https://mcp.tradingview.com/mcp`

Authentication is OAuth 2.1 with the user's own TradingView account. No login was performed in this session.

Local connector record: [tradingview-mcp.json](../integrations/tradingview-mcp.json)

Allowed research tools:

- `search_symbols`
- `get_ohlcv`
- `get_symbol_data`
- `run_screener`

Blocked from this design:

- watchlist creation, deletion, and edits
- alerts
- any order or broker action

The unofficial desktop-automation and auto-trading MCP repositories found during search were not integrated.

## REA

REA is the reverse-engineering workflow for shipped binaries, packages, and behavior that cannot be established from source. It was not connected.

Reasons:

- yfinance, QuantJourney Backtester, and the investment system publish their source.
- TradingView MCP has official documentation and an authenticated server.
- Decompiling TradingView's commercial client was not an acceptable integration path.

`rea.connected` is false in the research packet for that reason.

## X scraper files

`completion_agent.py` and `download_media.py` were inspected only far enough to see that they belong to an X scraping workflow. They were not used and are not part of this design.
