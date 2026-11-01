# Desktop app design

## Chosen stack

Python plus PySide6 was selected for the desktop application, with yfinance as the adapter and pandas for tabular history.

The confirmed folder was `/home/dell/projects/finance-desktop`, used directly rather than as a Git worktree.

## Intended first slice

- Watchlist
- Date range and interval
- History fetch
- Validation and quality status
- Snapshot metadata
- CSV export
- Later: comparison, fundamentals, alerts, and supervised streaming

## What was created

The runnable result is a browser prototype, not the PySide6 application.

| Path | Purpose |
| --- | --- |
| `index.html` | Research page with diagrams, workflow, catalog, and pilot |
| `styles.css` | Dark research-workbench styling |
| `app.js` | Sample watchlist, quality display, workflow runner, exports |
| `design-review.html` | Earlier standalone design page |
| `requirements.txt` | Planned Python dependencies: PySide6, yfinance, pandas |
| `app/` | Package directory created for the desktop app; no working UI was completed there |

## Why the desktop app stopped

The machine Python is 3.13.3. `python3-venv` and `pip` were not available, `ensurepip` was missing, and package installation required root access that was not available. No PySide6 process was started.

## Browser substitute

`python3 -m http.server 8000` was used so the HTML could be opened at `http://localhost:8000/`. The pilot table uses embedded sample rows. Its fetch, snapshot, and CSV actions are browser-local. They do not call yfinance.
