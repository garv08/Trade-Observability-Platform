# yfinance findings

Source reviewed: `https://github.com/ranaroussi/yfinance`

The first deliverable was [yfinance-design-review.html](/home/dell/.copilot/chats/80f0a91d-a9ca-4bce-9373-f75a11b4a112/yfinance-design-review.html). It contains the SVG architecture, sequence diagrams, quality gates, and the original build roadmap.

## Role in this system

yfinance is the market-data adapter, not the application. The app should own watchlists, run status, validation, snapshots, and exports.

## Public package boundaries observed

- `ticker.py`, `base.py`: single-symbol access
- `multi.py`: batch download
- `scrapers/`: history and related dataset scrapers
- `data.py`, `cache.py`: request coordination and cache
- `search.py`, `lookup.py`, `screener/`: discovery
- `live.py`: streaming
- `calendars.py`: calendar data

## Design consequences

- Treat provider failure and empty history as explicit states.
- Record interval, date range, row count, missing-data rate, and generation time with every snapshot.
- Do not hide partial failures inside a successful batch result.
- Keep streaming behind a later supervisor. It was not part of the first workflow.
- Do not depend on undocumented Yahoo behavior beyond what the adapter already encapsulates.

## Version context

The review snapshot used for the original HTML was yfinance 1.7.0. The later browser prototype did not install or call that package.
