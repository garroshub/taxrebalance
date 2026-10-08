# Audited Long–Short Sector Pair Strategy

## Strategy identity (do not change)

At every scheduled signal date, rank all tradable sector ETFs by their **cross-sectional MA Energy score** and **simultaneously**:

- **Buy the strongest-ranked sector** (largest MA Energy score).
- **Short the weakest-ranked sector** (smallest MA Energy score).
- Keep both legs as one coordinated position. Never leave one leg open as the strategy's intentional exposure.
- Use the *spread* between strongest and weakest scores to determine whether the pair is sufficiently differentiated. This is **not** a directional rule that chooses one long *or* one short based on the sign of an absolute signal.

The initial implementation uses a **dollar-neutral target** of **+50% / −50% of portfolio equity** at normal VIX, 100% total target gross. The same 1% short-execution headroom is applied to both legs, making actual initial gross approximately 98% before price/share rounding. This leverage convention is an explicit **working assumption** pending final portfolio sizing requirements; it is not automatically +100% / −100%.

The tradable universe is XLK, XLV, XLE, XLF, XLI, and XLY. SPY is the benchmark. VIX is only a risk-level input, never bought or shorted.

## Signal and trade clock

The MA Energy score is a weighted blend of price distance above/below trailing 10-, 40-, and 140-day averages, normalized by trailing 30-day volatility. The weights are inverse-square-root of horizon length. The strongest and weakest **relative** scores are chosen even when both scores are positive or both are negative. A pair is skipped if their spread is below the preset 0.10 threshold. This definition is frozen for this audit and has not been optimized.

Each close **t** produces the signal using data available through t. **Both** orders are filled at the **next trading close (t+1)**. The backtest uses daily adjusted closing prices; it does **not** claim next-open execution, intraday stops, or knowledge of t+1 prices at decision time.

Normal scheduled ranking is every 21 trading days, with risk-triggered additional decisions. The model closes prior long and short positions before opening a new pair at that same execution close. Fully closing and reopening incurs costs on *both sides*. A gross-risk or maintenance breach, VIX extreme alert, leg-specific trailing stop, or portfolio drawdown limit closes **both** legs on the next available close.

## Pair risk and short accounting

- VIX >25: reduce total gross target to 50% (**+25% / −25%**). VIX >50: flatten both legs.
- At entry: combined gross target ≤100% of equity; net target zero before share rounding and transaction expenses. Long/short gross and net are tracked independently at every close.
- Signed ETF shares are marked to daily prices; NAV equals **cash + marked long holdings − marked short obligations**. Proceeds of securities sold short remain in the account as **restricted collateral** and are excluded from freely available cash.
- Initial short collateral approximation: **150% of current short mark**; maintenance requirement: **30% of short notional** in account equity. These are simplified research guardrails, not complete broker-specific Regulation T or portfolio margin.
- Stock borrow fee: assumed constant **200 bps annually**, charged each day on short notional /252. It is not historical lending-market data. Each purchase, sale, short sale and cover incurs **10 bps** by default plus optional modeled slippage.
- Market gaps can temporarily push *realized* gross above the configured risk target. Such a violation is labeled **gross_limit_exit** and both legs close at the following close, not at the trigger close. **maintenance_margin_call** is tracked separately when equity falls below short maintenance requirements.
- Per-leg trailing-stop rules: if the long's price falls more than 5% below its post-entry peak or the short's price rises more than 5% above its post-entry low, **both legs exit** on the following close. Portfolio drawdown 20% and cooldown 21 sessions apply to the pair.
- The engine does not simulate locating short shares, daily changing borrow rates, borrow recalls, broker financing or broker-default liquidation fills. Yahoo adjusted ETF closing prices approximate corporate-action-aware returns; this is not a tick-accurate implementation.

## Corrected results: actual simultaneous pair

**Replay:** Frozen adjusted Yahoo data, 2000-01-03 through 2026-10-07, 6,731 trading days, and the fixed rules above. No parameter optimization, untouched out-of-sample testing or tradability validation. A different previous *single-direction* 0.66% result is **not this strategy** and must not be presented as such.

| Metric | Actual strongest-long / weakest-short pair | Long-only control | SPY buy and hold |
| --- | ---: | ---: | ---: |
| CAGR | **−2.02%** | 2.40% | 8.37% |
| Sharpe (2% risk-free assumption) | −0.945 | 0.093 | Not calculated in this audit |
| Annualized volatility | 4.18% | 12.72% | Not calculated |
| Maximum drawdown | 45.81% | 30.57% | Not calculated |
| $100k initial → final NAV | **$58,019.06** | $188,356.27 | Not calculated |
| Matched pair entries | 275 | Not applicable | Not applicable |
| Sessions holding both legs | 1,476 | 0 | Not applicable |
| Sessions with only one leg | **0** | Not applicable | Not applicable |
| Transaction fees, total | $37,195.10 | $49,130.32 | Not modeled |
| Borrow fees, total | $4,168.16 | $0 | Not applicable |
| Risk gross-cap breach sessions | 113 | 0 | Not applicable |
| Genuine maintenance-margin breach sessions | 0 | 0 | Not applicable |

Trade ledger records 1,100 execution events: 275 long entries, 275 short entries and their matched exits. Realized gross reached 1.0527× due to adverse post-entry price movement, then risk orders flattened the pair at the next closing execution point. Cash and equity remained positive throughout the replay.

The negative total return is **not evidence that short selling is universally unprofitable**. It demonstrates that this specific cross-sectional MA Energy, monthly decision schedule, stops, VIX cutbacks, cost assumptions, and gross-risk controls did not deliver positive economic performance over the observed data. Do not advertise legacy 18.5% return or 1.45 Sharpe; their execution engine was broken.

## Reproduction

```bash
python -m unittest -v test_execution_engine test_short_engine
python -m unittest -v test_model
streamlit run app.py
```

```python
import model

data = model.download_data("2000-01-01", end_date="2026-10-08")
signals = model.generate_signals(data)

# Project's actual strategy: two legs simultaneously.
pair, shares = model.backtest(data, signals, allow_short=True)
ledger = pair.attrs["trades"]
assert (shares.gt(0).any(axis=1) == shares.lt(0).any(axis=1)).all()

# An intentionally different long-only comparison.
control, _ = model.backtest(data, signals, allow_short=False)
```

Frozen local replay files (daily NAV, signed holdings, executed trade ledger, five-year descriptive windows and JSON metrics) are saved in **runs/pair_strategy_revision/** and ignored by Git. They are not published automatically. The original five-year windows are descriptive partitions, **not** cross-validated out-of-sample evidence.

## Remaining research work

Compare against conventional relative-momentum long–short sector pairs and equal-weight sector benchmarks at matched gross, identical trading times and cost rates. Quantify the impact of the spread threshold, VIX sizing, short-borrow cost, fee drag and the frequent risk-gross exits using **pre-registered ablations**. Lock design and evaluate genuinely future or untouched observations before proposing the strategy as an investable trading system.
