# Backtesting frameworks

The invalid URL `https://github.com/QuantJourneyOrg/quantjourney-btm` returns 404. The matching public project is `https://github.com/QuantJourneyOrg/quantjourney-bt`.

These repositories are references. Their code was not copied into this project.

| Engine | Repository | Role here | License note |
| --- | --- | --- | --- |
| QuantJourney Backtester | https://github.com/QuantJourneyOrg/quantjourney-bt | Primary auditable research contract | Apache-2.0 license file observed |
| vectorbt | https://github.com/polakowo/vectorbt | Fast parameter screening | Apache-2.0 plus Commons Clause observed; not treated as unrestricted |
| backtesting.py | https://github.com/kernc/backtesting.py | Single-symbol prototypes | License must be rechecked before reuse |
| bt | https://github.com/pmorissette/bt | Portfolio allocation and rebalancing | License must be rechecked before reuse |
| Backtrader | https://github.com/mementum/backtrader | Legacy reference only | License must be rechecked before reuse |
| A-share investment system | https://github.com/zixuan0104/investment-system | Screening, backtest, paper, and audit pattern | README states MIT; no root `LICENSE` file was found |

## QuantJourney contract used for the design

```text
Data -> Features -> Signals -> Target weights or orders
  -> Simulated fills -> Portfolio state -> Metrics and run metadata
```

Public package areas observed: `backtester/core.py`, `engines/`, `execution/`, `portfolio/`, `metrics/`, `walkforward/`, `universe.py`, and `strategies/`.

## Investment-system areas used for the design

- `src/quant`: factor screen and universe
- `src/backtest`: historical simulation and reporting
- `src/paper`: paper state and recovery
- `src/harness`: fusion, risk checks, and audit log
- `src/subjective`: LLM and supply-chain reasoning; not integrated

Its A-share constraints, including T+1, price limits, lot size, stamp duty, and commission, are documented as foreign market rules. They are not applied to NSE or BSE.

## Strategy work not built

No strategy from those repositories has been executed. The local page can rank sample closes and assign equal weights. That is not a backtest.
