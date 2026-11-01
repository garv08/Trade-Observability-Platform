# Third-party notices

## TradingView Lightweight Charts™ v4.2.3

- File: `top/web/vendor/lightweight-charts.standalone.production.js` (unmodified)
- Copyright (c) 2025 TradingView, Inc.
- License: Apache License 2.0. The full text is in `top/web/vendor/LICENSE-lightweight-charts.txt`.
- Source: https://github.com/tradingview/lightweight-charts

The chart shows the "Charting by TradingView" attribution link, as the library's license notice requests. TOP is not affiliated with or endorsed by TradingView.

## Ideas from YouTube creators

`top/creators.py` re-implements, from scratch, algorithms published by:

- **neurotrader888**: https://github.com/neurotrader888 (repositories under the MIT License, Copyright (c) neurotrader888; `IntramarketDifference` has no license, so only its published idea is used). No source code is copied.
- **Unbiased Trading (@UnbiasedTradingGoshawk)**: ideas from public sources tested in the channel's videos (Larry Connors' published rules, an EWMAC trend signal, and Khandani & Lo (2007), "What Happened to the Quants in August 2007?").

- **@TradZoo** (X): the key-levels and pattern-breakout method in `top/levels.py` was inferred from the account's public chart posts. No post text or chart image is included.

TOP is not affiliated with or endorsed by any of these creators. See `docs/creators.md`.

## Data sources

- Daily prices: Yahoo Finance public chart endpoint, fetched at run time. No market data is shipped in this repository.
- Fundamentals: public Screener.in company pages, fetched on demand and cached for six hours. TOP is not affiliated with Screener.in. Respect each site's terms of use.
