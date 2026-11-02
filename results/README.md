# 🏆 Leaderboard results

Snapshots of the [strategy leaderboard](../docs/user-guide.md#strategy-leaderboard): every one of TOP's 88 long/flat strategies, with default settings, backtested on every stock, ETF, and index in the local store.

| | |
| --- | --- |
| Data up to | 30 Oct 2026 (Nifty 50 to 2 Nov 2026) |
| Computed | 2 Nov 2026 |
| Scripts | 4,526 (Nifty 50, NSE indices, BSE indices, NSE/BSE ETFs, BSE stocks with at least 250 bars) |
| Backtests | 398,278 |
| Skipped | 208 scripts with thin trading or impossible one-day moves; Dividend Points and VIX indices |
| Settings | ₹10 lakh, 5 bps per side, long/flat, signal at the close, fill at the next open |

## Files

| File | Rows | What it holds |
| --- | ---: | --- |
| [`leaderboard-cagr15.csv`](leaderboard-cagr15.csv) | 24,822 | Every backtest with **CAGR > 15%**, ≥ 3 trades, ≥ 2 tested years, and ≥ ₹10 lakh median daily traded value (indices exempt), ranked by CAGR ÷ \|max drawdown\| |
| [`leaderboard-best-per-script.csv`](leaderboard-best-per-script.csv) | 1,276 | The same filter, keeping only each script's best strategy |
| `top-leaderboard-all.csv.gz` ([v0.3.0 release asset](https://github.com/garv08/Trade-Observability-Platform/releases/tag/v0.3.0)) | 398,278 | Everything, unfiltered (22 MB compressed, 71 MB raw) |

By universe, the best-per-script file has 1,155 BSE stocks, 70 NSE ETFs, 26 NSE indices, and 25 Nifty 50 stocks. BSE indices only have history from about April 2025, so none reach 2 tested years.

## Columns

`rank, symbol, name, universe, exchange, median_value_lakh, strategy, strategy_name, section, ratio, cagr_pct, max_dd_pct, total_return_pct, buy_hold_pct, trades, win_rate_pct, profit_factor, sharpe, exposure_pct, in_position, years, first_day, last_day, computed_at`

- `ratio` = `cagr_pct / max(|max_dd_pct|, 5)`.
- `years` = years tested after the strategy's warm-up; `first_day` is the first tested day.
- `in_position` = the rule was long on the last bar.
- `median_value_lakh` = median daily traded value over the last 250 bars, in ₹ lakh (index values reflect constituent volume on NSE and zero on BSE).

## Reproduce or refresh

In the app, open **Leaderboard** → **Run / resume**, then **Download CSV**. Or, with the server stopped:

```bash
top-leaderboard                       # compute (resumable)
top-leaderboard --export all.csv      # everything
top-leaderboard --export cagr15.csv --min-cagr 15 --min-trades 3 --min-years 2 --min-value 10
top-leaderboard --export best.csv --min-cagr 15 --min-trades 3 --min-years 2 --min-value 10 --best
```

> [!CAUTION]
> These are in-sample results of 88 rules tried on thousands of scripts. Many top rows are BSE small caps that multiplied many times over, where almost any trend rule looks brilliant in hindsight. Selection bias is large. Prefer strategies that pass on many scripts (see *Strategies that pass most often* on the page) and test them out of sample before relying on them. Research only, not investment advice.
