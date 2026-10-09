# TaxRebalance

Tax-aware portfolio rebalancing in Python, with Canadian average adjusted cost base (ACB), U.S. tax-lot accounting, and tracking-error constrained optimization.

The package accepts user-supplied securities, prices, target weights, covariance matrices, and dated taxable holdings. It produces proposed trades with modeled tax effects, transaction fees, risk penalties, post-trade cash, and solver feasibility diagnostics.

**Python 3.10+ · CVXPY and Clarabel · CAD and USD research models**

## Install

```bash
pip install taxrebalance
```

## Quickstart

```python
from datetime import date
from taxrebalance import (
    CADTransaction, CanadaACB, Portfolio, RebalanceConfig, rebalance
)

portfolio = Portfolio(
    jurisdiction="CA",
    prices={"XIC": 100.0, "XEF": 100.0},
    transactions=(
        CADTransaction(date(2025, 1, 10), "XIC", "BUY", 60, 115),
        CADTransaction(date(2025, 2, 12), "XEF", "BUY", 40, 85),
    ),
    valuation_date=date(2026, 10, 8),
)
result = rebalance(
    portfolio,
    target_weights={"XIC": 0.50, "XEF": 0.50},
    covariance=[[0.04, 0.01], [0.01, 0.04]],
    tax_policy=CanadaACB(marginal_rate=0.42, inclusion_rate=0.50),
    config=RebalanceConfig(max_tracking_error=0.015),
)
print(result.summary())
print(result.trades)
```

The default `tax_aware` method uses a convex relaxation and local fixed-direction search. The package also supports `risk_only`, `greedy`, `hold`, and `small_exact`. Exhaustive direction enumeration applies to at most four securities in the continuous-share model.

## Inputs and results

- **Canada:** dated purchase and sale transactions, aggregated into average ACB pools for identical securities across the taxpayer's own taxable accounts.
- **United States:** individual tax lots with acquisition basis, holding period, and limited replacement-purchase flags.
- **Constraints:** target weights, annual tracking-error cap, transaction fees, cash availability, nonnegative holdings, and sale quantities.
- **Results:** per-security trades, modeled current and future tax effects, estimated trading fees, risk penalties, solver status, and risk feasibility.
- **Interfaces:** Python API, CSV and JSON inputs, JSON results, CSV trade export, and a command-line entry point.

This is a continuous-share decision model. Tax-loss eligibility, superficial-loss and wash-sale treatment, and future transactions require review outside the package. No live market feed, trading execution, tax-return filing, or return forecast is provided.

## Links

- Repository and complete documentation: https://github.com/garroshub/taxrebalance
- Interactive synthetic portfolio demo: https://garroshub.github.io/taxrebalance/

MIT License.
