<p align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="TaxRebalance is a Python portfolio rebalancing toolkit with risk, transaction cost, and tax constraints. The right panel shows a synthetic Canadian four-ETF comparison; the package has been tested with 500 securities and 1,500 tax lots.">
</p>

<p align="center">
  <a href="https://garroshub.github.io/taxrebalance/"><img src="assets/readme/button-demo.svg" height="46" alt="Open the interactive demo"></a>
  <a href="#quickstart"><img src="assets/readme/button-quickstart.svg" height="46" alt="Jump to Python quickstart"></a>
  <a href="#model-and-tax-rules"><img src="assets/readme/button-methods.svg" height="46" alt="Read the model and tax rules"></a>
  <a href="#reproduce-the-results"><img src="assets/readme/button-reproduce.svg" height="46" alt="Run the tests"></a>
</p>

<p align="center">
  <strong>Python 3.10+</strong> · CVXPY / Clarabel · Canadian ACB + U.S. tax lots · 500-asset synthetic stress tests
</p>

TaxRebalance calculates proposed portfolio trades for a specified target allocation, weighing estimated tax effects, transaction costs, tracking error, trading restrictions, and cash availability. Use your own positions, prices, target weights, and annual covariance. The Python optimizer supports portfolios beyond the four securities shown in the separate browser demo.

## Scale and trading controls

The default tax-aware solver uses convex relaxation followed by fixed-direction searches. Portfolios with more than 24 assets use a bounded directional search and a reusable CVXPY model. The search budget can be increased when the trade-off between runtime and local search quality warrants it.

| Synthetic workload | Tax lots | Correlated covariance | Computation time |
| :-- | --: | :-- | --: |
| 250 securities | 750 | Four-factor + diagonal | 20.8 seconds |
| 500 securities | 1,500 | Four-factor + diagonal | 58.4 seconds |

These are single-run measurements on the development Windows machine, using synthetic prices, holdings, and tax lots with a 35% gross trading cap and one blocked security. Runtime depends on portfolio structure, available solver, and hardware. Every reported solution met its modeled cash, position, turnover, restricted-security, and tracking-error constraints. These tests do not establish globally optimal trading directions.

**The controls accept:**

- `max_tracking_error`: maximum annualized deviation from the target under the supplied covariance.
- `max_turnover_fraction`: the maximum *combined buy plus sell notional*, divided by starting portfolio equity. For example, `0.20` is a 20% **two-sided** cap.
- `restricted_tickers`: securities that cannot be bought or sold during this rebalance.
- `direction_search_budget`: maximum fixed-direction candidates examined after the relaxed solve. `None` selects an automatic scale-dependent budget.
- `trading_cost_bps`, `loss_utilization`, `future_recapture_fraction`, and `risk_aversion`: explicit model assumptions.

The decision record includes feasibility, actual tracking error, gross turnover, modeled taxes, fees, risk penalty, selected trades, explored patterns, and whether the local search was budget-limited.

## See the decision

The online demo contains 11 synthetic portfolios, with six Canadian ACB cases and five U.S. tax-lot cases. Four configurable assumptions select from 108 individually solved combinations. It illustrates the decision components; large or arbitrary portfolios must use the Python package.

<p align="center">
  <a href="https://garroshub.github.io/taxrebalance/"><img src="assets/readme/pm-decision.png" width="100%" alt="TaxRebalance live synthetic portfolio manager panel showing modeled tax-aware cost difference and tracking error."></a>
</p>

The four-ETF Canadian demo has a 2.5% tracking-error limit.

| Method | Modeled objective (CAD) | Risk feasible |
| :-- | --: | :-- |
| Risk-only | −C$482.99 | Yes |
| Tax-aware heuristic | **−C$969.88** | Yes |
| Small-model enumeration | −C$969.88 | Yes |

The C$486.89 difference is a *modeled objective change*, not an actual tax refund or investment return. The objective combines assumed tax effects, trading fees, and a risk penalty.

## Quickstart

Install the published package:

```bash
python -m pip install --upgrade taxrebalance
```

With tax-lot holdings and annual covariance supplied by the caller:

```python
import json
from taxrebalance import (
    Portfolio, RebalanceConfig, UnitedStatesLots, rebalance
)

with open("prices.json", encoding="utf-8") as f:
    prices = json.load(f)
with open("targets.json", encoding="utf-8") as f:
    targets = json.load(f)
with open("covariance.json", encoding="utf-8") as f:
    annual_covariance = json.load(f)

portfolio = Portfolio.from_tax_lots(
    "tax_lots.csv", prices=prices, cash=5000
)

result = rebalance(
    portfolio,
    target_weights=targets,
    covariance=annual_covariance,
    tax_policy=UnitedStatesLots(),
    config=RebalanceConfig(
        max_tracking_error=0.025,
        trading_cost_bps=10,
        max_turnover_fraction=0.20,
        restricted_tickers=("RESTRICTED_SYMBOL",),
        direction_search_budget=25,
    ),
)

print(result.summary())
result.trades_to_csv("proposed_trades.csv")
```

Replace `RESTRICTED_SYMBOL` with a security in your actual portfolio universe, or omit `restricted_tickers`. The U.S. tax-lot CSV requires `lot_id,ticker,shares,basis_per_share,days_held,prior_30d_replacement`. Canada instead uses `Portfolio.from_transactions(..., valuation_date=...)` with a dated ledger containing `date,ticker,side,shares,price_cad,fee_cad,account`.

The CLI accepts the same market and portfolio inputs:

```bash
python -m taxrebalance --jurisdiction US --portfolio tax_lots.csv \
  --prices prices.json --targets targets.json --covariance covariance.json \
  --config config.json --output decision.json
```

The JSON config accepts `cash` plus the `RebalanceConfig` parameters above.

## Model and tax rules

<p align="center">
  <img src="assets/readme/workflow.svg" width="100%" alt="Diagram of the tax basis, market and target inputs, the tracking-error-constrained optimizer, and the final trades and cost diagnostics.">
</p>

| | Canada | United States |
| :-- | :-- | :-- |
| Cost basis | Average ACB across the taxpayer's own taxable accounts | Individual acquisition lots |
| Selling | Single averaged pool per identical security | Lot-specific sales |
| Loss screening | Conservative superficial-loss lookback flags | Simplified prior-replacement flags |
| Illustrative tax assumptions | 50% capital gain inclusion × 42% marginal rate | 20% long-term and 35% short-term |

Fixed trade directions produce convex subproblems. The default heuristic chooses directions from a relaxed problem, solves feasible candidates and searches selected neighbors. Up to **four securities**, the optional `small_exact` method enumerates all (3^N) directions. That is a small-model benchmark only; it is **not** the portfolio size limit.

The optimizer uses **continuous share quantities** and models a single rebalancing decision. It does not round trades to executable whole shares, enforce minimum order sizes, model bid/ask spreads or market impact, or connect to brokers. The Canadian and U.S. loss-sale flags are simplified screens, not legally exhaustive tax determinations. Tax assumptions and covariance estimates must be verified for the specific decision.

## Reproduce the results

```bash
git clone https://github.com/garroshub/taxrebalance.git
cd taxrebalance
python -m pip install -e ".[test]"
python -m pytest -q test_canadian_rebalancing.py test_tax_rebalancing.py tests_package/
python tools/benchmark_scale.py --assets 100 --lots 3 --seed 19
python tools/verify_dashboard.py
```

Increase `--assets` to 250 or 500 to reproduce the correlated-covariance scale workload. The output includes runtime, solution cost, constraints, trade count and lower bound. The website can be served with `python -m http.server 8000 --directory docs`. Optional browser regression: `python tools/test_browser_dashboard.py`.

<details>
<summary><strong>Research scope and source layout</strong></summary>

- `taxrebalance/`: stable Python API, CLI, result export and configuration.
- `tax_rebalancing/`: tax basis models and CVXPY optimizer.
- `tests_package/`: public API, multi-asset, concurrency and trade-control checks.
- `tools/benchmark_scale.py`: reproducible large-universe synthetic workload.
- `docs/`: separate static four-ETF interactive demo.
- `RESEARCH_DESIGN.md`: objective, assumptions, tax-rule boundaries and algorithmic scope.

Neither tax engine computes a completed tax return. The Canadian model does not calculate all superficial-loss denial quantities or resulting ACB changes. The U.S. model does not determine all wash sales. No live market data, broker execution, integer-share execution plan or return forecast is supplied.

</details>

MIT License.
