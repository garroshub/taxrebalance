# TaxRebalance

**Tax-aware portfolio rebalancing in Python.**

TaxRebalance accepts prices, target weights, annual covariance matrices, and taxable position histories supplied by the user. It compares modeled tax costs, trading fees, and tracking-error constraints for Canadian average-cost pools and U.S. specific tax lots. The included browser demonstration uses fictional portfolios and precomputed solver results. The package makes no brokerage connections and does not prepare tax returns.

## Install

```bash
pip install taxrebalance
```

Python 3.10 or later is required. You can also install from this repository with `pip install -e .`.

## Python interface

```python
import numpy as np
from taxrebalance import Portfolio, RebalanceConfig, CanadaACB, rebalance

portfolio = Portfolio.from_transactions(
    "transactions.csv",
    prices={"XIC": 100, "XEF": 100},
    valuation_date="2026-10-08",
    cash=1000,
)
result = rebalance(
    portfolio,
    target_weights={"XIC": 0.50, "XEF": 0.50},
    covariance=np.array([[0.04, 0.01], [0.01, 0.05]]),
    tax_policy=CanadaACB(marginal_rate=0.42, inclusion_rate=0.50),
    config=RebalanceConfig(max_tracking_error=0.025, trading_cost_bps=10),
)
print(result.summary())
result.trades_to_csv("trades.csv")
```

Canadian transactions CSV: `date,ticker,side,shares,price_cad,fee_cad,account`. Date is ISO 8601. The U.S. input is individual tax lots with `lot_id,ticker,shares,basis_per_share,days_held,prior_30d_replacement`. Prices and targets are keyed by ticker; the covariance matrix uses that same ticker order.

The default `tax_aware` method uses a convex relaxation with fixed-direction local search. `risk_only`, `greedy`, and `hold` are also available. `small_exact` enumerates direction patterns for portfolios of up to four assets; it is a benchmark for the continuous-share model. Set `compare=True` to obtain method comparisons. Larger portfolios use the heuristic and require numerical and feasibility checks.

## Command line

```bash
taxrebalance --jurisdiction CA --portfolio transactions.csv \
  --prices prices.json --targets targets.json --covariance covariance.json \
  --valuation-date 2026-10-08 --output decision.json
```

`--jurisdiction US` accepts a tax-lot CSV and does not require a valuation date. `--config` accepts a JSON object of rebalancing parameters. Results include solver status, trades, costs, and risk measurements.

## Browser demonstration

The demonstration uses synthetic inputs only and does not generate prices or trade instructions for live portfolios.

## Two tax jurisdictions

| | Canada (default) | United States |
| --- | --- | --- |
| Currency | CAD | USD |
| Cost basis | **Average adjusted cost base (ACB)** for identical securities across the taxpayer's own taxable accounts | Individual tax lots with specific basis |
| Selling | Sell shares from an averaged pool, not an elective purchase lot | Choose individual lots |
| Modeled tax rates | Illustrative **50% capital gain inclusion × 42% marginal rate** | Illustrative 20% long-term and 35% short-term |
| Loss review | Superficial-loss 30-day windows and affiliated-person watch | Simplified wash-sale flags |
| Presolved scenarios | **6 fictional CAD portfolio cases** | **5 fictional USD cases** |

The [GitHub Pages site](https://garroshub.github.io/taxrebalance/) opens with the Canadian portfolio. It shows the modeled cost difference against risk-only rebalancing, the tax, fee and risk contributions to that difference, tracking-error usage, and before/after allocations. Selecting a method updates its exact tax-pool trades and cash balance.

The site has **four editable assumptions**: annual tracking-error cap (1.2%, 2.5%, 4%), trading fee (5, 10, 40 bps per traded side), usable capital losses (20%, 80%), and the future tax recapture fraction (0%, 20%). Canada also includes a separate simulated account history with an affiliated recent purchase. Each available combination uses its own numerical optimization output.

There are **11 preset examples** and **108 independently computed combinations** in \`docs/data/assumption_grid.json\`. The static browser only selects stored results. New arbitrary assumptions require generating more cases with the Python solver.

### Run locally

```bash
python -m pip install -r requirements.txt
python -m unittest -v test_canadian_rebalancing test_tax_rebalancing
python tools/build_demo_data.py
python tools/build_assumption_grid.py
python tools/verify_dashboard.py
python -m http.server 8000 --directory docs
```

Open http://localhost:8000. The repository currently uses the **master** branch; for deployment choose **Settings → Pages → Deploy from a branch → master → /docs** after committing and pushing the files.

Browser regression testing is optional. Install Playwright with \`python -m pip install playwright\`, run \`python -m playwright install chromium\` if Chrome is unavailable, then execute \`python tools/test_browser_dashboard.py\`. The browser test verifies that each assumption update matches its stored numerical solution and checks the desktop and mobile layouts.

## Why this optimization is nonconvex

The portfolio target is given. The optimizer chooses which positions to rebalance, balancing transaction fees, tax effects, and deviation from the target subject to an annualized tracking-error limit. Each ticker is constrained to **BUY, SELL, or HOLD** in a particular rebalance. Fixed-direction subproblems are convex; the direction choice is discrete.

The shared solver requires available shares, nonnegative positions and cash, no funding leverage, and a specified TE cap. Its objective is **estimated current tax liability + hypothetical future tax recapture + explicit trading costs + risk-deviation penalty**. Usable tax losses are multiplied by an explicitly assumed fraction; they are **not guaranteed immediate refunds**.

The tax-accounting engine is jurisdiction-specific. Canada's historical simulated CAD buys are aggregated into an average ACB pool for each security. The U.S. engine instead can choose specific tax lots.

| Alternative | Method |
| --- | --- |
| Hold | No trade, reports infeasibility when existing risk exceeds the cap |
| Risk-only | Rebalance considering risk and fees, then report resulting taxes |
| Greedy | Same risk-only asset trades; U.S. selects advantageous lots; Canada has only averaged ACB pools |
| Two-stage convex heuristic | Relax buy/sell disjunction, freeze directions, re-solve, then locally explore alternatives |
| Small continuous optimum | Enumerate **3⁴ = 81** directions and solve each convex subproblem |

The 81-pattern minimum is a global reference **only for the modeled continuous-share 4-asset optimization problem, to solver tolerance**. It is not a global certificate for real tax law or integer-share execution. Methods are inspired by [Moehle et al., Tax-Aware Portfolio Construction via Convex Optimization](https://web.stanford.edu/~boyd/papers/tax_aware_portfolio.html).

## Canadian simulation: ACB-based rebalancing

A synthetic **C$100,000** taxable portfolio holds XIC, XEF, XBB, XRE with a 2.5% annual tracking-error budget. XIC was bought in two fictional taxable accounts: 200 shares at **C$145**, plus 200 shares at **C$119**. Those taxpayer-owned identical securities average to **C$132 ACB per share**. A sale of XIC cannot designate either historical purchase.

| Method | Risk-feasible | Modeled combined objective (CAD) |
| --- | --- | ---: |
| Hold | No | Exceeds tracking-error budget |
| Risk-only | Yes | −C$482.99 |
| Greedy ACB | Yes | −C$482.99 |
| **Tax-aware convex heuristic** | Yes | **−C$969.88** |
| Enumerated small-model optimum | Yes | **−C$969.88** |

The other five Canadian simulations vary TE limits (1.2%, 4%), trading cost (40 bps), loss utilization (20%), and a **fictional affiliated person's purchase** of identical property inside the lookback period. A flagged potential superficial loss receives **zero modeled immediate credit** pending review. The system does not certify the actual treatment of that loss, and future day+30 ownership cannot be known at trade-decision time.

## Separate U.S. simulation

On a distinct synthetic **US$100,000, four-ETF, ten-lot** portfolio with a 2.5% TE cap:

| Method | Risk-feasible | Modeled combined objective (USD) |
| --- | --- | ---: |
| Hold | No | Exceeds tracking-error budget |
| Risk-only | Yes | +US$149.49 |
| Greedy tax-lot selection | Yes | −US$357.37 |
| **Tax-aware convex heuristic** | Yes | **−US$719.48** |
| Enumerated small-model optimum | Yes | **−US$719.48** |

**Lower is better**, but this target combines *modeled* tax benefit/cost, transactions, and risk penalties. Negative values are **not investment profits, realized tax refunds or expected portfolio returns**. Risk penalty 1.0 is selected solely for illustrative frontier analysis, not calibrated to an investor.

## Source, tests and reproduction

- tax_rebalancing/canada.py — simulated CAD transactions, pooled average ACB, independent Canadian scenarios, partial-sale logic and 30-day superficial-loss review
- tax_rebalancing/models.py, tax_rebalancing/scenarios.py — distinct fictional U.S. tax-lot model
- tax_rebalancing/optimizer.py — shared CVXPY/Clarabel optimization, directional heuristic, greedy and small enumeration
- test_canadian_rebalancing.py — Canadian ACB, chronological transactions, affiliate screening, 30-day rule windows, conservation and optimizer checks
- test_tax_rebalancing.py — U.S. lots, tax/risk feasibility and objective checks
- tools/build_demo_data.py — generates **6 Canada + 5 U.S.** actually solved synthetic cases
- tools/build_assumption_grid.py — precomputes **108 combinations** of four editable assumptions using actual optimization
- tools/test_browser_dashboard.py — runs Chrome/Playwright interaction checks at desktop and mobile widths
- docs/ — static Canada-first decision desk reading both presolved data files
- RESEARCH_DESIGN.md — method, scope, legal limitations and research verification

## Tax law boundaries

Canada: the CRA generally averages the ACB of identical securities within the taxpayer's holdings. A superficial loss may involve acquisition of identical property **30 calendar days before/after a loss sale**, including acquisitions by affiliated persons, plus ownership at the end of the 30-day post-sale period. The simulation screens these features conservatively but cannot make a full legal determination, quantify all partial denials, or carry out real denied-loss ACB adjustments. See [CRA average ACB rules](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/special-rules-other-transactions.html) and [CRA capital losses](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/capital-losses-deductions.html). The Canadian proposal to increase the capital gains inclusion rate was cancelled, per [Canada Finance 2026 Tax Expenditures](https://www.canada.ca/en/department-finance/services/publications/federal-tax-expenditures/2026/part-2.html). The **50% inclusion** is still a transparent scenario assumption, not personalized tax advice.

U.S.: wash-sale rules may involve substantially identical securities, IRAs and linked persons and accounts. The simulation provides only limited exclusion flags, not tax compliance; see [IRS Publication 550](https://www.irs.gov/publications/p550).

Both countries: simulated future tax utilization, rates, covariance and transaction fees create model uncertainty. No real investor data, tax filing, market forecasts, brokerage execution, or claim of tax alpha. Future studies will use **additional fictional portfolios and simulation stress tests**, not real brokerage uploads.

## License

MIT, see LICENSE.
