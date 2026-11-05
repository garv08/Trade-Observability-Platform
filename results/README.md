# 🏆 Leaderboard results

Snapshots of the [strategy leaderboard](../docs/user-guide.md#strategy-leaderboard): every one of TOP's 92 long/flat strategies, with default settings, backtested on every stock, ETF, and index in the local store.

| | |
| --- | --- |
| Data up to | 4 Nov 2026 |
| Computed | 5 Nov 2026 |
| Scripts | 6,643 (Nifty 50, other NSE stocks, NSE/BSE indices, NSE/BSE ETFs, BSE stocks with at least 250 bars; a company listed on both exchanges is tested on both) |
| Backtests | 611,146 |
| Skipped | 254 scripts with thin trading or impossible one-day moves; Dividend Points and VIX indices |
| Settings | ₹10 lakh, 5 bps per side, long/flat, signal at the close, fill at the next open |

## Files

| File | Rows | What it holds |
| --- | ---: | --- |
| [`leaderboard-cagr15.csv`](leaderboard-cagr15.csv) | 46,686 | Every backtest with **CAGR > 15%**, ≥ 3 trades, ≥ 2 tested years, and ≥ ₹10 lakh median daily traded value (indices exempt), ranked by CAGR ÷ \|max drawdown\| |
| [`leaderboard-best-per-script.csv`](leaderboard-best-per-script.csv) | 2,672 | The same filter, keeping only each script's best strategy (ties go to the strategy id that sorts first) |
| [`strategy-ranking-return-dd.csv`](strategy-ranking-return-dd.csv) | 82 | **Strategies ranked** by median total return ÷ \|max drawdown\| across scripts (see below) |
| `top-leaderboard-all.csv.gz` ([v0.6.1 release asset](https://github.com/garv08/Trade-Observability-Platform/releases/tag/v0.6.1)) | 611,146 | Everything, unfiltered |

By universe, the best-per-script file has 1,325 NSE stocks, 1,211 BSE stocks, 73 NSE ETFs, 33 NSE indices, 30 Nifty 50 stocks. BSE indices only have history from about April 2025, so none reach 2 tested years.

## Which strategy gives the most return ÷ max drawdown across stocks?

`strategy-ranking-return-dd.csv` ranks the strategies themselves. For each strategy and script, it computes **total return ÷ |max drawdown|** (drawdown floored at 5%). It then takes the **median across every qualifying script**: at least 3 trades, at least 2 tested years, and at least ₹10 lakh traded a day (indices exempt). There is **no CAGR cut**, so losing scripts count too, and a strategy ranks high only if it works broadly. Strategies with fewer than 50 qualifying scripts are left out (82 of 92 remain).

| # | Strategy | Scripts | Median return ÷ DD | Median return | Median max DD | Profitable | Beat buy & hold |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Turn of the month | 3,311 | **2.15** | +70% | -36% | 85% | 56% |
| 2 | Donchian 55 break | 439 | **1.44** | +49% | -51% | 69% | 29% |
| 3 | Donchian 20 break | 770 | **0.98** | +44% | -57% | 67% | 25% |
| 4 | Any Carney bullish | 3,111 | **0.84** | +12% | -18% | 71% | 34% |
| 5 | Gartley long | 102 | **0.82** | +7% | -12% | 64% | 20% |
| 6 | Connors Double 7s | 3,101 | **0.79** | +21% | -30% | 69% | 36% |
| 7 | RSI reversion | 3,252 | **0.76** | +19% | -29% | 71% | 37% |
| 8 | TSMOM 12-month | 2,876 | **0.73** | +28% | -45% | 67% | 36% |
| 9 | CCI extreme reversal | 3,311 | **0.73** | +22% | -34% | 69% | 35% |
| 10 | Connors RSI(2) pullback | 3,090 | **0.73** | +13% | -20% | 70% | 34% |

Bottom three: Parabolic SAR (-0.13), Inside-bar break (-0.14), Pivot R1 break (-0.23).

**Turn of the month**, new in 0.5.0 from the X research digest, ranks first across 3,311 scripts: 85% were profitable and 56% beat buy-and-hold. Much of that comes from being invested only about 8 sessions a month, which keeps drawdowns small. One caveat: the rule needs to know which session ends each month. For liquid stocks that is the published exchange calendar, but for a thinly traded stock the last day it actually traded is only known afterwards. The Donchian breakouts come next but trade rarely (median 4–6 trades), so fewer scripts reach 3 trades. With the NSE stocks added in 0.6.0, mean-reversion rules (Connors Double 7s, RSI reversion, CCI, Connors RSI(2)) moved into the top ten, ahead of the moving-average trend rules. Most strategies beat buy-and-hold on only about a third of scripts.

**Deflated Sharpe.** With 92 strategies tried on each script, a high Sharpe is often luck. Of the 46,686 rows in `leaderboard-cagr15.csv`, only 185 (on 107 scripts) have a deflated Sharpe of at least 95%, the chance their Sharpe beats the best expected from 92 lucky tries (`dsr_pct` column; normal returns assumed, so even this is optimistic). The `pct_dsr95` column in the strategy ranking shows how rarely any single strategy clears it.

Other columns: `mean_return_dd`, `p25_return_dd`/`p75_return_dd` (middle half), `median_cagr_pct`, `median_cagr_dd` (median CAGR ÷ DD), `pct_profitable`, `pct_beat_hold`, `median_trades`, `median_years`, and `best_symbol`/`best_return_dd` (the single best script). In the app: **Leaderboard → By strategy**, which you can re-sort by any of these.

## Columns

`rank, symbol, name, universe, exchange, median_value_lakh, strategy, strategy_name, section, ratio, return_dd, psr_pct, dsr_pct, cagr_pct, max_dd_pct, total_return_pct, buy_hold_pct, trades, win_rate_pct, profit_factor, sharpe, exposure_pct, in_position, years, first_day, last_day, computed_at`

- `ratio` = `cagr_pct / max(|max_dd_pct|, 5)`; `return_dd` = `total_return_pct / max(|max_dd_pct|, 5)`.
- `psr_pct` / `dsr_pct` = probabilistic and deflated Sharpe: the chance the true Sharpe is above 0, and above the best expected by luck from the script's strategy trials.
- `years` = years tested after the strategy's warm-up; `first_day` is the first tested day.
- `in_position` = the rule was long on the last bar.
- `median_value_lakh` = median daily traded value over the last 250 bars, in ₹ lakh (index values reflect constituent volume on NSE and zero on BSE).

## Reproduce or refresh

On any machine, after `git pull`, with `top-platform` stopped:

```bash
pip install -e .                       # pick up new code and commands
top-sync                               # Nifty 50, all BSE stocks, ETFs, and indices (first run about an hour)
top-leaderboard --results results      # every strategy on every script (resumable; hours the first time), then rewrite all three CSVs
```

`--results` writes `leaderboard-cagr15.csv`, `leaderboard-best-per-script.csv`, and `strategy-ranking-return-dd.csv` with exactly the settings above (`RESULT_FILTERS` and `STRATEGY_FILTERS` in `top/leaderboard.py`). Ties are broken by name, so the same database always gives byte-identical files. Numbers will differ from these snapshots only because your data runs to a different date.

In the app: **Leaderboard** → **Run / resume**, then **Download CSV** in either view. Individual exports:

```bash
top-leaderboard                       # compute (resumable)
top-leaderboard --export all.csv      # everything
top-leaderboard --export cagr15.csv --min-cagr 15 --min-trades 3 --min-years 2 --min-value 10
top-leaderboard --export best.csv --min-cagr 15 --min-trades 3 --min-years 2 --min-value 10 --best
top-leaderboard --strategies ranking.csv   # strategy ranking (defaults: 3 trades, 2 tested years, ₹10 lakh)
```

> [!CAUTION]
> These are in-sample results of 92 rules tried on thousands of scripts. Many top rows are BSE small caps that multiplied many times over, where almost any trend rule looks brilliant in hindsight. Selection bias is large. Prefer strategies that pass on many scripts (see *Strategies that pass most often* on the page) and test them out of sample before relying on them. Research only, not investment advice.
