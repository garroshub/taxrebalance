# TaxRebalance

Tax-aware portfolio rebalancing in Python with Canadian average adjusted cost base (ACB), U.S. tax-lot accounting, and tracking-error constrained optimization.

**Python 3.10+ · CVXPY / Clarabel · Public API and CLI · Scalable local search**

The Python optimizer supports portfolios larger than the four-ETF website example. Synthetic tests have covered **500 securities with 1,500 individual tax lots**, correlated annual covariance, gross turnover limits, and restricted securities. The large-universe solver uses bounded local search with a reusable conic model; results are not globally optimality-certified.

## Install

```bash
python -m pip install taxrebalance
```

## Example

```python
import json
from taxrebalance import Portfolio, RebalanceConfig, UnitedStatesLots, rebalance

with open("prices.json", encoding="utf-8") as f:
    prices = json.load(f)
with open("targets.json", encoding="utf-8") as f:
    targets = json.load(f)
with open("covariance.json", encoding="utf-8") as f:
    covariance = json.load(f)

portfolio = Portfolio.from_tax_lots(
    "tax_lots.csv", prices=prices, cash=5000
)
result = rebalance(
    portfolio,
    target_weights=targets,
    covariance=covariance,
    tax_policy=UnitedStatesLots(),
    config=RebalanceConfig(
        max_tracking_error=0.025,
        trading_cost_bps=10,
        max_turnover_fraction=0.20,
        direction_search_budget=25,
    ),
)
print(result.summary())
result.trades_to_csv("proposed_trades.csv")
```

`max_turnover_fraction` caps the **combined** buy and sell notional relative to starting equity. Set `restricted_tickers=("SYMBOL",)` in `RebalanceConfig` to prohibit trades in a security included in the portfolio universe. Additional parameters include risk aversion, usable capital loss fraction, and assumed future tax recapture.

Canadian portfolios use dated `CADTransaction` events or `Portfolio.from_transactions()`, and `CanadaACB` as the tax policy. United States portfolios use individual `TaxLot` entries and `UnitedStatesLots`.

## Main features

- Custom portfolio universes, holding histories, current prices, target weights and covariance inputs.
- Canadian averaged ACB pools and U.S. lot-specific sale options.
- Convex-relaxation tax-aware optimizer with adaptive direction search on larger portfolios.
- Maximum tracking error, available cash, nonnegative holdings, gross turnover limits and blocked securities.
- Hold, risk-only and greedy comparison methods. Enumeration of all directions is available for at most four assets as a **small-model benchmark**, not as the maximum package universe size.
- JSON result export, CSV trade export, feasibility flags, turnover accounting, solver status and bounded-search diagnostics.
- A CLI reading CSV tax lots or transactions, plus JSON risk and target inputs.

## Measured scale

In a synthetic U.S. study with four-factor correlated covariance and 35% two-sided gross turnover:

| Securities | Tax lots | Observed runtime |
| ---: | ---: | ---: |
| 250 | 750 | 20.8 seconds |
| 500 | 1,500 | 58.4 seconds |

These are single-run development-machine timings. Reproduce the workload using `python tools/benchmark_scale.py --assets 500 --lots 3` after cloning the repository. Runtime and trade quality depend on input structure and solver hardware.

## Scope

This is a **single-period, continuous-share decision model**, not executable trade routing. It omits whole-share reconstruction, minimum order values, bid/ask spreads, real-world market impact and brokerage integration. Canadian superficial-loss and U.S. wash-sale handling remain conservative, incomplete screening logic. It does not prepare tax returns, determine legal tax-loss eligibility or predict financial returns. User-supplied prices, covariance and tax parameters must be validated independently.

Repository: https://github.com/garroshub/taxrebalance

Interactive synthetic demo: https://garroshub.github.io/taxrebalance/

MIT License.
