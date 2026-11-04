# 🧭 Research digest: ideas from 13 X accounts

In November 2026 we read about 42,000 public posts from 13 X accounts, collected for private research. This page summarises, **in our own words**, the methods that carry over to daily-bar research on Indian equities, and where each one lives in TOP. No post text or media is reproduced; links point to the original posts, so follow the authors there. Dates are UTC.

> [!NOTE]
> The ideas belong to their authors. Performance figures quoted by the accounts are their own claims; TOP re-tests ideas on its own data. The scraped dataset is not part of this repository.

## Accounts at a glance

| Account | Posts read | What it mostly covers | Useful for TOP |
| --- | ---: | --- | --- |
| [@quantscience_](https://x.com/quantscience_) | 5,606 | Systematic trading in Python: momentum, volatility targeting, Kelly, regimes, backtest hygiene (with heavy course promotion) | **High** |
| [@stockmarket8058](https://x.com/stockmarket8058) | 8,234 | Indian stocks: drawdown-from-high lists, multi-year and weekly breakouts, FII/DII/promoter stake changes, results | **High** (price-based scans) |
| [@RuOnChain1](https://x.com/RuOnChain1) | 3,009 | Pointers to papers and lectures: HMM regimes, Kalman filters, cointegration, Sharpe corrections | Medium–High |
| [@RohOnChain](https://x.com/RohOnChain) | 4,568 | LLM trading bots, plus a few solid threads on backtesting, regimes and sizing | Medium |
| [@Dipper_pol](https://x.com/Dipper_pol) | 907 | Two strong threads on position sizing and drawdown control | Medium |
| [@TradZoo](https://x.com/TradZoo) | 988 | Daily Nifty levels and pattern breakouts | Already in TOP (*Key levels*, *Pattern breakout*) |
| @sopersone, @recogard, @51bodila | 13,778 | Prediction markets and bots; a few posts on Kelly, base rates and statistical edge | Low–Medium |
| @Shelpid_WI3M, @RetroChainer, @cryptotrice | 3,860 | AI and crypto product posts | Low |
| @brewmarkets | 1,080 | Market news and headline statistics | Low |

## Ideas built into TOP

### Portfolio strategies (the *Portfolio* page)

TOP used to test one stock at a time. Several accounts make the same point: rank a whole universe and hold the best names, rather than timing a single asset.

| Idea | Rule in TOP | Sources |
| --- | --- | --- |
| **Cross-sectional momentum (12-1)** | Each month, rank by the return from 12 months ago to 1 month ago and hold the top *N* equally weighted. *N* changes results the most, so the page sweeps it | [@quantscience_ 2025-12-24](https://x.com/quantscience_/status/2003872379815010544), [2026-01-18](https://x.com/quantscience_/status/2012932087402176607); [@RohOnChain 2026-10-06](https://x.com/RohOnChain/status/2107509847692599642) |
| **Sector rotation** | Rank NSE sectoral indices by momentum; hold the top 3 | [@quantscience_ 2026-09-10](https://x.com/quantscience_/status/2098079864712532268) |
| **Low volatility** | Hold the lowest-volatility names, rebalanced monthly | [@quantscience_ 2026-09-10](https://x.com/quantscience_/status/2098079855266992349) (same thread) |
| **ETF momentum with a trend filter** | Hold the best ETFs by momentum, only while each is above its 10-month average | [@quantscience_ 2026-09-10](https://x.com/quantscience_/status/2098079844533698638) (same thread) |

### Single-stock strategies and sizing

| Idea | In TOP | Sources |
| --- | --- | --- |
| **Time-series momentum** (Moskowitz, Ooi and Pedersen, 2012) | *TSMOM 12-month*: long while the 252-day return is positive | [@quantscience_ 2025-11-29](https://x.com/quantscience_/status/1994755555613696413); [@sopersone 2026-07-10](https://x.com/sopersone/status/2075693614588657846) |
| **Kalman trend** | Local-level Kalman filter on price; long while price is above the filtered level and that level is rising | [@RuOnChain1 2026-06-24](https://x.com/RuOnChain1/status/2069779422367146180) |
| **Turn of the month** | Long over the last sessions of a month and the first sessions of the next | [@quantscience_ 2025-11-30](https://x.com/quantscience_/status/1995175057639805124) |
| **Hurst routing** | A trend rule when the Hurst exponent says the stock trends, RSI reversion when it says the stock mean-reverts | [@RuOnChain1 2026-07-26](https://x.com/RuOnChain1/status/2081397093919236257) |
| **Volatility targeting** | Backtest *Sizing → Vol target*: exposure = target volatility ÷ 20-day realised volatility, capped at 100% | [@quantscience_ 2026-03-22](https://x.com/quantscience_/status/2035691288163414463); [@Dipper_pol 2026-09-22](https://x.com/Dipper_pol/status/2102473675605733572) |
| **Half Kelly** | The backtest reports the Kelly fraction from the strategy's own trades. *Sizing → Half Kelly* applies it using earlier trades only | [@quantscience_ 2025-11-23](https://x.com/quantscience_/status/1992582219232117005); [@RohOnChain 2026-09-11](https://x.com/RohOnChain/status/2098417461804884234) |

### Robustness checks

With 88 strategies tried on about 5,000 scripts, some of the best results are luck. The quant accounts keep returning to the same checks.

| Check | In TOP | Sources |
| --- | --- | --- |
| **Probabilistic and deflated Sharpe** | Leaderboard columns: the chance the Sharpe ratio is really above zero, and above the best Sharpe expected by luck from that script's 88 trials | [@RuOnChain1 2026-07-22](https://x.com/RuOnChain1/status/2079982719480840671), [2026-09-20](https://x.com/RuOnChain1/status/2101723317476696541) |
| **Monte Carlo trade shuffling** | Backtest results show the range (5th–95th percentile) of max drawdown over 1,000 reshuffles of the trades | [@RohOnChain 2026-09-11](https://x.com/RohOnChain/status/2098486986583757043); [@quantscience_ 2026-03-17](https://x.com/quantscience_/status/2033936721851695334) |
| **Walk-forward** | Re-picks the strategy's main setting each year using only earlier data, and reports the joined out-of-sample result | [@RohOnChain 2026-09-11](https://x.com/RohOnChain/status/2098486986583757043), [2026-10-07](https://x.com/RohOnChain/status/2107871472471748836) |

### Market breadth, regimes and scans (the *Markets* page)

| Idea | In TOP | Sources |
| --- | --- | --- |
| **Breadth** | New 52-week highs vs lows, % of stocks above their 50- and 200-day averages, advancers vs decliners | Indirect: [@stockmarket8058 2025-12-02](https://x.com/stockmarket8058/status/1995820095382454643), on Nifty near its high while most stocks were far below theirs |
| **Volatility regime** | Nifty's 20-day realised volatility, ranked against its own past year: calm, normal or stressed | [@quantscience_ 2026-10-16](https://x.com/quantscience_/status/2111068435023085672); [@RohOnChain 2026-09-12](https://x.com/RohOnChain/status/2098745427554353512) |
| **Sector rotation table** | 1-, 3- and 6-month returns of sectoral indices relative to Nifty | [@stockmarket8058 2026-02-26](https://x.com/stockmarket8058/status/2026988725335728487) |
| **"Bloodbath" scan** | Liquid stocks 30–60% below their 52-week high, still at least 10% above their 52-week low | [@stockmarket8058 2026-08-22](https://x.com/stockmarket8058/status/2091061537360560496) (the account's most-liked series) |
| **Multi-year breakout** | Close above the highest high of the previous 2+ years on above-average volume | [@stockmarket8058 2026-09-27](https://x.com/stockmarket8058/status/2104163120604438545) |
| **Weekly breakout / breakout soon** | Close above the prior 52-week high on volume, or within 5% below it | [@stockmarket8058 2026-07-09](https://x.com/stockmarket8058/status/2075231179264197085) |
| **Leaders in a falling market** | Stocks within 3% of their high while Nifty is at least 5% below its own | [@stockmarket8058 2026-03-16](https://x.com/stockmarket8058/status/2033405172261818381) |
| **Delivery %** | Five years of NSE security-wise delivery data, as a study and a delivery-surge scan | NSE's public daily file (a standard Indian-market signal; the account rarely uses it) |
| **FII/DII cash flows** | A daily snapshot of NSE's provisional figures, kept from the first sync onwards | NSE's public endpoint (latest day only) |

## Not built, and why

- **Shareholding, promoter and insider-buying trackers** (@stockmarket8058's largest series) need quarterly shareholding filings and SEBI insider-trading disclosures, which TOP doesn't collect.
- **P/E and "quality" filters** need results data. Screener.in ratios remain available one stock at a time in the desk.
- **HMM regimes** are possible but heavy without NumPy. The volatility-percentile regime covers most of the use and is easier to trust.
- **Pairs trading** needs a short leg; Indian cash markets don't allow holding a short overnight.
- **Hype we skipped:** 24/7 "AI agent" bots, next-candle forecasting, wallet-copying stories, and one-prompt backtests with a few dozen trades.

## Hypotheses to test with TOP

1. Stocks 30–60% below their 52-week high but above their 52-week low beat the market over 3–12 months, or (momentum) keep lagging.
2. Multi-year breakouts on high volume beat ordinary breakouts.
3. When Nifty is near its high but fewer than half of stocks are above their 200-day average, the next three months are weaker than usual.
4. Stocks that hold near their highs while Nifty falls 5% lead the next rally.
5. High delivery % together with a volume surge marks accumulation that comes before gains.
