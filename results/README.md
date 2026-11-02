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
| [`leaderboard-best-per-script.csv`](leaderboard-best-per-script.csv) | 1,276 | The same filter, keeping only each script's best strategy (ties go to the strategy id that sorts first) |
| [`strategy-ranking-return-dd.csv`](strategy-ranking-return-dd.csv) | 75 | **Strategies ranked** by median total return ÷ \|max drawdown\| across scripts (see below) |
| `top-leaderboard-all.csv.gz` ([v0.3.0 release asset](https://github.com/garv08/Trade-Observability-Platform/releases/tag/v0.3.0)) | 398,278 | Everything, unfiltered (22 MB compressed, 71 MB raw) |

By universe, the best-per-script file has 1,155 BSE stocks, 70 NSE ETFs, 26 NSE indices, and 25 Nifty 50 stocks. BSE indices only have history from about April 2025, so none reach 2 tested years.

## Which strategy gives the most return ÷ max drawdown across stocks?

`strategy-ranking-return-dd.csv` ranks the strategies themselves. For each strategy and script, it computes **total return ÷ |max drawdown|** (drawdown floored at 5%). It then takes the **median across every qualifying script**: at least 3 trades, at least 2 tested years, and at least ₹10 lakh traded a day (indices exempt). There is **no CAGR cut**, so losing scripts count too, and a strategy ranks high only if it works broadly. Strategies with fewer than 50 qualifying scripts are left out (75 of 88 remain).

| # | Strategy | Scripts | Median return ÷ DD | Median return | Median max DD | Profitable | Beat buy & hold |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Donchian 55 break | 270 | **2.31** | +71% | -47% | 77% | 29% |
| 2 | Donchian 20 break | 430 | **1.80** | +74% | -52% | 74% | 25% |
| 3 | MACD zero line | 1,720 | **1.10** | +34% | -43% | 71% | 34% |
| 4 | EMA 12/26 | 1,727 | **1.09** | +35% | -43% | 71% | 36% |
| 5 | AHL-style trend following (EWMAC) | 1,459 | **1.05** | +35% | -42% | 71% | 32% |
| 6 | Above SMA 200 | 1,597 | **1.03** | +35% | -43% | 68% | 32% |
| 7 | SMA cross | 1,709 | **0.98** | +29% | -40% | 69% | 38% |
| 8 | Dual momentum | 1,598 | **0.95** | +31% | -41% | 69% | 30% |
| 9 | ROC momentum | 1,735 | **0.93** | +31% | -43% | 69% | 33% |
| 10 | ATR trail | 1,715 | **0.92** | +29% | -45% | 68% | 31% |

Bottom three: Parabolic SAR (0.01), Inside-bar break (-0.03), Pivot R1 break (-0.21).

The Donchian breakouts top the median but trade rarely (median 4–6 trades), so fewer scripts reach 3 trades. MACD zero line, EMA 12/26, AHL-style trend following, and Above SMA 200 do almost as well across about 1,500–1,700 scripts each. Most strategies beat buy-and-hold on only about a third of scripts.

Other columns: `mean_return_dd`, `p25_return_dd`/`p75_return_dd` (middle half), `median_cagr_pct`, `median_cagr_dd` (median CAGR ÷ DD), `pct_profitable`, `pct_beat_hold`, `median_trades`, `median_years`, and `best_symbol`/`best_return_dd` (the single best script). In the app: **Leaderboard → By strategy**, which you can re-sort by any of these.

## Columns

`rank, symbol, name, universe, exchange, median_value_lakh, strategy, strategy_name, section, ratio, cagr_pct, max_dd_pct, total_return_pct, buy_hold_pct, trades, win_rate_pct, profit_factor, sharpe, exposure_pct, in_position, years, first_day, last_day, computed_at`

- `ratio` = `cagr_pct / max(|max_dd_pct|, 5)`.
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
> These are in-sample results of 88 rules tried on thousands of scripts. Many top rows are BSE small caps that multiplied many times over, where almost any trend rule looks brilliant in hindsight. Selection bias is large. Prefer strategies that pass on many scripts (see *Strategies that pass most often* on the page) and test them out of sample before relying on them. Research only, not investment advice.
