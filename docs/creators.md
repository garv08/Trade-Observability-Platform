# Creator strategies

TOP has two sections named after YouTube channels. Each holds strategies and studies adapted from that creator's published work. Each strategy can be backtested on one stock or across a universe (**Backtest universe**), like every other rule.

## How these were built

- **No video or audio was downloaded.** Bulk-downloading YouTube media is against YouTube's terms. Transcribing hundreds of videos would also not have given exact rules. The sources are public text: video titles, descriptions, and chapters, the creators' own GitHub repositories, and papers or books linked from the videos.
- **Every rule is re-implemented from scratch** in `top/creators.py` from the published algorithm. Nothing is copied from the creators' code.
- **Adapted to TOP's constraints:** daily NSE bars, long or flat (no shorting), signal at the close, fill at the next open, with costs. Parameters were rescaled from the creators' mostly hourly crypto settings; tune them in the strategy panel.
- **Confidence labels:**
  - **HIGH**: rules come from the creator's own published code.
  - **MEDIUM**: the video names a public source (a paper or book), but the exact variant used in the video is not public, so TOP uses the original source's published rules.

These are research adaptations. They are not the creators' own results and not an endorsement by them.

## @neurotrader888

Channel: https://www.youtube.com/@neurotrader888 · Code: https://github.com/neurotrader888 (MIT licensed, except `IntramarketDifference`, which has no license; only its idea is used).

The creator automates classic technical analysis and stress-tests it, often reporting weak or negative results. His tests use crypto (BTC/ETH), mostly hourly, long and short.

### Strategies

| ID | Name | Rule in TOP | Defaults | Source | Confidence |
| --- | --- | --- | --- | --- | --- |
| `nt_dc_trend` | Directional-change trend | Long during zigzag up-legs: a bottom is confirmed when the close rises Sigma % off the low; flat when a top is confirmed | Sigma 5% | `TechnicalAnalysisAutomation/directional_change.py` | HIGH |
| `nt_atr_dc_trend` | ATR directional-change trend | Same, but a reversal must be Mult × ATR(14) | ATR 14, Mult 2 | `market-structure/atr_directional_change.py` | HIGH |
| `nt_trendline_breakout` | Trendline breakout | Fit support and resistance lines to the previous Lookback log closes. The lines pass through the largest-residual point and minimise squared distance without crossing price. Long on a close above projected resistance; flat below projected support | Lookback 30 | `TrendLineAutomation`, `TrendlineBreakoutMetaLabel`, [video](https://www.youtube.com/watch?v=jCBnbQ1PUkE) | HIGH |
| `nt_inverse_hs` | Inverse head and shoulders | Five alternating swing points (order k), head lowest, shoulders below the midpoint of the opposite shoulder and armpit, timing ratio ≤ 2.5. Long on a close through the neckline; exit after the head width or on a close below the right shoulder | Order 6 | `TechnicalAnalysisAutomation/head_shoulders.py` | HIGH |
| `nt_bull_flag` | Bull flag / pennant | Pole from a swing low of at least Pole ATR × ATR; flag no wider than half the pole and no deeper than half its height. Long on a close above the flag's resistance line; exit after the pole width or below the flag low | Order 6, Pole ATR 3 | `TechnicalAnalysisAutomation/flags_pennants.py` | HIGH |
| `nt_hawkes_vol` | Hawkes volatility breakout | Range/ATR through a Hawkes decay filter. When it crosses its rolling 95th percentile after a dip below the 5th, go long if price rose since the dip; flat at the next dip below the 5th | ATR 20, κ 0.1, window 60 | `VolatilityHawkes`, [video](https://www.youtube.com/watch?v=wdsiZBIhAFw) | HIGH |
| `nt_cmma_index` | Intramarket CMMA vs Nifty proxy | CMMA = (log close − SMA) / (ATR × √lookback). The stock's CMMA minus that of an equal-weight Nifty 50 proxy; long when it crosses above Threshold, flat below 0 | 20, ATR 60, 0.25 | `IntramarketDifference` | HIGH |
| `nt_donchian_runs` | Donchian + last-trade filter | 20-day Donchian breakout. Mode 1 takes a breakout only if the previous breakout trade lost (the serial dependence the video found), mode 2 only after a winner, mode 0 all | 20, mode 1 | `TradeDependenceRunsTest` | HIGH |
| `nt_rsi_pca` | RSI-PCA forecast | RSI at lengths 2, 4 … 24 → top 3 principal components → linear forecast of the next 6-day log return. Refit every 63 days on the previous 500 (walk-forward). Long when the forecast is above the 90th percentile of training forecasts | 3 PCs, 90, 500, 63, 6 | `RSI-PCA`, [video](https://www.youtube.com/watch?v=mdncZ034Q7k) | HIGH |

Changes from the originals:

- Short sides are dropped, because NSE cash shorts are intraday only.
- The trendline video's random-forest meta-label filter is left out; it needs an ML library.
- RSI-PCA is walk-forward instead of the video's in-sample fit, and uses even RSI lengths for speed.
- CMMA compares each stock with an equal-weight Nifty 50 proxy (`top/market.py`) instead of ETH vs BTC.

### Studies

| ID | Name | Pane |
| --- | --- | --- |
| `nt_zigzag` | Directional-change zigzag | Price |
| `nt_trendlines` | Auto trendlines (upper, lower) | Price |
| `nt_hawkes` | Hawkes volatility with 5th and 95th percentiles | Own pane |
| `nt_vsa` | VSA range-vs-volume residual | Own pane |
| `nt_cmma` | CMMA difference vs Nifty proxy | Own pane |
| `nt_perm_entropy` | Permutation entropy (d = 3) | Own pane |

### Not implemented

| Idea | Why |
| --- | --- |
| PIP pattern mining (k-means clusters of perceptually important points) | Needs clustering and silhouette selection; heavy without NumPy |
| Trendline meta-labeling (random forest) | Needs an ML library |
| Visibility-graph and time-reversibility indicators | Graph shortest paths and O(n²) counts; low priority, and no trading rule in the repos |
| KDE market-profile support and resistance | Rolling kernel density over a year per bar is too slow in pure Python for universe scans |
| DeFi TVL indicator | Crypto-only data |
| Harmonic patterns | TOP already has a full Scott Carney set (see [@harmonictrader](#harmonictrader-scott-m-carney-x)) |

## @UnbiasedTradingGoshawk

Channel: https://www.youtube.com/@UnbiasedTradingGoshawk (display name "Unbiased Trading", US/global markets).

The channel mostly tests strategies from books, papers, and funds. Its public titles, descriptions, and chapters rarely give exact parameters. TOP includes only ideas whose original source is public and that fit daily long/flat trading, and labels them MEDIUM.

### Strategies

| ID | Name | Rule in TOP | Defaults | Video | Confidence |
| --- | --- | --- | --- | --- | --- |
| `ut_connors_rsi2` | Connors RSI(2) pullback | Above SMA 200, buy when RSI(2) < 10; sell on a close above SMA 5 (Connors' published rules) | 10, 200, 5 | [Larry Connors test](https://www.youtube.com/watch?v=4TTb0f9fk1U) | MEDIUM |
| `ut_double_seven` | Connors Double 7s | Above SMA 200, buy at a 7-day closing low; sell at a 7-day closing high | 7 | same | MEDIUM |
| `ut_ahl_trend` | AHL-style trend (EWMAC) | Average of four volatility-scaled EMA crossovers (8/32, 16/64, 32/128, 64/256), each clipped to ±20; long when the average > Threshold | 0 | [Man AHL paper](https://www.youtube.com/watch?v=54PMBYXA3e0), [ML video](https://www.youtube.com/watch?v=MHCRqXL_mkA) | MEDIUM |
| `ut_lo_contrarian` | Lo–Khandani contrarian | Long for Hold days after the stock's return trails the equal-weight Nifty proxy by more than Threshold % (long-only form of the paper's contrarian portfolio) | 2%, 1 day | [MIT "Sharpe 53" video](https://www.youtube.com/watch?v=elPKLu9cj_I), [paper](https://web.mit.edu/Alo/www/Papers/august07.pdf) | MEDIUM |

### Studies

| ID | Name |
| --- | --- |
| `ut_ewmac` | EWMAC trend forecast (−20 to +20) |
| `ut_rel_return` | Daily return minus Nifty proxy return (%) |

### Not implemented

| Idea | Why |
| --- | --- |
| Toby Crabel opening-range breakout and "stretch" | Intraday entries; daily bars cannot see the intraday path |
| Pairs trading (Tartaglia / Morgan Stanley) and Kalman-filter pairs | Long one stock and short another |
| AI crypto bots, options, futures automation | Different markets or instruments |
| Book and fund videos without public rules | The rules are not stated in public text |

## @TradZoo (X)

Account: https://x.com/TradZoo, Indian price-action analysis.

The account's public posts were studied for method only; no post text or chart is copied into TOP. Most posts are daily "intraday support and resistance levels" for Nifty and Bank Nifty: four horizontal levels, long above the inner resistance and short below the inner support, each with three stepped targets. The rest are stock chart-pattern posts (falling wedges, triangles, channels, inverse head and shoulders) with a buying zone, a stop under support, and a measured-move target.

| ID | Type | What TOP does | Confidence |
| --- | --- | --- | --- |
| `key_levels` | Study (Trend) | Next-session R2 / R1 / S1 / S2 from clustered swings and recent extremes, with stepped targets and a written plan | MEDIUM (method inferred) |
| `pattern_breakout` | Study (Trend) | Trendline-fitted wedge / triangle / channel / range; breakout with buying zone, stop, T1 at the prior swing high, and T2 = breakout + pattern height | MEDIUM (method inferred) |
| `key_level_breakout` | Strategy (Breakout) | Long on a close above yesterday's R1; exit at R2 or below S1 | MEDIUM |
| `pattern_breakout` | Strategy (Breakout) | Long on a pattern breakout; exit at T2, below the stop, or after 40 bars | MEDIUM |

TradZoo's level posts are for intraday trading on 15-minute charts. TOP has daily bars, so its levels apply to the next session.

## @harmonictrader (Scott M. Carney, X)

Account: https://x.com/harmonictrader, the author of the harmonic ratio framework TOP's patterns follow.

All 3,274 public posts (Nov 2021 – Nov 2026) and their charts were studied for rules only; no post text or chart is copied into TOP. Examples of the posts behind each rule: [Bat PRZ](https://x.com/harmonictrader/status/1484511316652044288), [confirmation](https://x.com/harmonictrader/status/1817912593400414711), [Gartley AB=CD](https://x.com/harmonictrader/status/1847629816138232169), [Cypher is not his](https://x.com/harmonictrader/status/1619121135752253442).

| Rule from the posts | What TOP does | Confidence |
| --- | --- | --- |
| Structure, then ratio, then confirmation | `carney_prz` study and `harm_prz*` strategies run the three steps causally | HIGH |
| D at the XA level, failure at the HOP (Bat 0.886/1.13, Butterfly 1.27/1.414, Crab and Deep Crab 1.618) | D and HOP levels per pattern; a close beyond the HOP ends the trade | HIGH |
| Confirmation: close above the prior 3 highs, or two bullish closes; RSI turning up from oversold | Confirm modes 0/1/2 and the RSI filter | MEDIUM (his HSI indicator is proprietary; RSI stands in) |
| Targets 0.382 and 0.618 of AD; 30-bar time limit | Target setting and 30-bar time stop; readings show both targets | HIGH |
| Gartley needs AB=CD (CD/AB 1.0–1.27) | Checked in the PRZ engine | HIGH |
| Preference: Bat, Deep Crab, Shark, Crab, Gartley | One pattern per X-A-B-C, in that order | MEDIUM |

Not implemented: half-position exits at T1 (TOP's backtests are all-in or flat), the bearish side (TOP is long only), and type-II re-entries after T1.

**Result.** The old harmonic backtests entered on the D bar before it could be known; with that removed, the best variants reach a median return ÷ max DD of about 0.26 on 271 liquid stocks. With Carney's confirmation the figure is about 0, against 1.54 for buy and hold. See [design §6.2.1](design.md#621-carney-prz-engine-prz_setups-prz_trades-prz_watch).

## First results on Nifty 50 (2021-11 to 2026-10, 5 bps costs, default settings)

From **Backtest Nifty 50**. "Beat B&H" counts stocks where the strategy's total return beat buy and hold over the same period.

| Strategy | Median return | Beat B&H | Avg trades |
| --- | --- | --- | --- |
| `nt_dc_trend` | +17.7% | 7/50 | 43.8 |
| `nt_atr_dc_trend` | +18.7% | 9/50 | 44.8 |
| `nt_trendline_breakout` | +18.4% | 7/50 | 36.3 |
| `nt_inverse_hs` | 0.0% | 8/50 | 3.5 |
| `nt_bull_flag` | +0.2% | 8/50 | 16.4 |
| `nt_hawkes_vol` | +18.1% | 4/50 | 8.0 |
| `nt_cmma_index` | +9.7% | 9/50 | 41.2 |
| `nt_donchian_runs` | +7.5% | 8/50 | 7.9 |
| `nt_rsi_pca` | −2.4% | 11/50 | 22.2 |
| `ut_connors_rsi2` | +7.2% | 10/50 | 31.5 |
| `ut_double_seven` | +21.6% | 12/50 | 37.6 |
| `ut_ahl_trend` | +33.5% | 8/50 | 6.4 |
| `ut_lo_contrarian` | −5.6% | 5/50 | 61.2 |

Over this mostly rising period, most long/flat rules made money but lagged simply holding most stocks, because they spend time out of the market. The creators themselves warn against trusting raw backtests. Treat these as starting points, check them with walk-forward tests, and rerun **Backtest universe** after you change parameters.
