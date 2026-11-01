# Stitched workflow

## Decision

REA was not used to stitch the repositories. They are public source projects, so their published structure was used instead of decompilation.

## Stage map

| Stage | Owner | Current behavior |
| --- | --- | --- |
| Universe | yfinance search/ticker boundaries plus TradingView symbol mapping | Filters the embedded sample to `.NS` and `.BO` |
| TradingView context | Official TradingView MCP read-only tools | Named in the packet; not called |
| Investment-system adapter | `src/quant`, `src/backtest`, `src/paper`, `src/harness` | Named in the packet; modules are not imported |
| History contract | yfinance history plus local quality gate | Sample row count and missing-data display |
| Factor screen | investment-system screener pattern | Ranks sample closes by first-to-last change |
| Parameter screen | vectorbt role | Recorded as a separate stage; no sweep runs |
| Allocation | bt role | Equal weight across the top three sample names |
| Auditable backtest | QuantJourney core, engines, execution, portfolio | Assumptions recorded; engine not executed |
| Single-name check | backtesting.py role | Stage label only |
| Paper review | investment-system paper module | Stage label only; no broker |
| Audit packet | QuantJourney run metadata plus harness audit pattern | Browser JSON download |

## Packet rules

- `market` is `NSE_BSE_ONLY`
- `mode` is `historical_research`
- `liveOrders` is false
- `copiedRepositoryCode` is false
- Sample prices are labeled illustrative
- A 10 bps cost note is an assumption, not a broker quote

## Page location

`http://localhost:8000/#workflow`

The run button advances the stage labels locally and then writes the packet. It does not call the external engines.
