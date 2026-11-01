# NSE and BSE scope

## Decision

The sample universe must be Indian exchanges only. US sample symbols were removed.

## Current sample watchlist

- NSE: `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`
- BSE: `RELIANCE.BO`, `TCS.BO`

A plain symbol entered in the prototype is normalized to the NSE suffix. `INFY` becomes `INFY.NS`.

## TradingView mapping

The workflow maps local Yahoo-style symbols to TradingView's `EXCHANGE:TICKER` form:

- `RELIANCE.NS` -> `NSE:RELIANCE`
- `RELIANCE.BO` -> `BSE:RELIANCE`

## Data probe

A direct chart request for `RELIANCE.NS` succeeded without installing yfinance:

- Endpoint: `https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?interval=1d&range=6mo`
- Exchange reported: `NSI`
- Bars returned: 126
- Last close observed in that probe: 1164.9000244140625

That probe is not wired into the page. The visible table still uses illustrative sample prices.

## Not done

- No full NSE or BSE security master was downloaded.
- No corporate-action adjustment policy has been verified for Indian symbols.
- No exchange holiday calendar is applied.
