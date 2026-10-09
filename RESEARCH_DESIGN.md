# Research Design — TaxRebalance

## Problem definition

TaxRebalance selects proposed purchases and sales for a specified target portfolio. It models current realized-gain tax effects, assumed future tax recapture, transaction costs, and deviation from target weights. It does not predict returns or select an investment strategy.

For asset `i`, price `p_i`, target weight `w_i*`, purchase quantity `b_i`, and sale quantity `s_j` from tax lot or ACB pool `j`, let `V` be initial portfolio equity and `Sigma` the annual covariance matrix. Posttrade risky holdings are existing shares plus buys minus sales. Tax pools and allowable sale quantities come from the selected jurisdiction.

The objective, expressed in the portfolio currency, is:

```text
estimated current tax effect
+ assumed future tax recapture
+ fees on gross buy and sell notional
+ risk_aversion * V * (posttrade_weights - target_weights)'
                      * Sigma * (posttrade_weights - target_weights)
```

Constraints include:

- Annualized tracking error bounded by `max_tracking_error`.
- Nonnegative positions, cash, and remaining tax-lot quantities.
- Available cash after paying transaction fees; no borrowed funds.
- Buy, sell or hold on each security during one rebalance, not simultaneous purchases and sales.
- Optional total **two-sided** traded notional divided by initial equity bounded by `max_turnover_fraction`.
- Optional `restricted_tickers` with no purchases or sales.
- Fixed provided prices, covariance, tax-rate assumptions and target weights.

These are continuous-share optimization decisions. `gross_turnover_fraction` reports total modeled purchases **plus** sales divided by initial portfolio equity.

## Optimization algorithms

The direction disjunction introduces nonconvexity. Conditional on a fixed buy/sell/hold vector, the modeled subproblem is convex.

- `hold`: evaluates the current holdings and reports risk breaches.
- `risk_only`: solves trading costs and risk deviation without using taxes in the optimization objective, then reports modeled tax consequences.
- `greedy`: keeps risk-only per-security quantities while allocating U.S. sales among lots according to estimated tax cost. Canada has one averaged pool per security and no equivalent lot-choice freedom.
- `tax_aware`: solves a convex relaxation, fixes a direction vector, and searches feasible one-security direction alternatives.
- `small_exact`: enumerates all `3**N` directions for at most four assets. This is a global comparator for the modeled continuous-share optimization problem to numerical tolerance, not for integer execution or tax law.

For more than 24 assets, the two optimization heuristics rank candidate direction changes by portfolio drift and relaxed trade magnitude. The default maximum number of fixed-direction candidates decreases with universe size: 25 for up to 100 assets, 17 for 101–250, and 9 above 250. `direction_search_budget` overrides this heuristic budget. The budget does **not** constrain the security universe. A thread-local reusable CVXPY conic model avoids recompiling the full problem for each candidate. Optimization uses Clarabel with an SCS fallback.

The relaxed objective is a numerical **lower bound** for the modeled tax-aware objective. A heuristic result is not guaranteed to attain that bound and is not a global certificate for large universes. Solver statuses, explored direction counts, `search_limited`, feasibility, and the lower-bound value are available in the output.

The optimization follows the convex modeling approach described in [Moehle et al., Tax-Aware Portfolio Construction via Convex Optimization](https://web.stanford.edu/~boyd/papers/tax_aware_portfolio.html).

## Canadian taxable accounts

Dated purchases and sales are grouped by identical security across the taxpayer's own taxable accounts. Purchases add cash purchase value and fees to the total adjusted cost base. Sales recognize proceeds net of sale fees and subtract the current **average** ACB per unit. Partial sales do not change average basis per remaining share. Holdings belonging to affiliated people are not pooled into the taxpayer's ACB.

Canada uses one average ACB pseudo-pool per security for the optimizer, not electable historic U.S. lots. The illustrative effective capital-gain tax proxy is `capital_gain_inclusion_fraction * marginal_tax_rate`, initially 50% × 42% = 21%. That is a scenario input rather than a personalized tax determination. The 2026 federal capital gains inclusion proposal was cancelled, as reported in [Finance Canada's 2026 tax expenditures report](https://www.canada.ca/en/department-finance/services/publications/federal-tax-expenditures/2026/part-2.html).

A purchase within 30 calendar days before a potential loss sale, including flagged affiliated-person acquisitions, withholds the immediate modeled loss credit conservatively. The separate retrospective quantity screen accepts purchases in the 30 days before and after sale and the remaining substituted shares at day+30. Actual identity, affiliations, denied-loss ACB adjustments, registered accounts and future transactions are not fully adjudicated. See [CRA ACB rules](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/special-rules-other-transactions.html) and [CRA superficial-loss information](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/capital-losses-deductions.html).

## United States taxable accounts

Each purchase lot has its own acquisition cost, age, and available share quantity. The model applies illustrative short- and long-term capital-gain tax rates and an assumed loss utilization fraction. A limited prior replacement-purchase flag suppresses modeled immediate loss benefit. This is incomplete wash-sale handling; see [IRS Publication 550](https://www.irs.gov/publications/p550).

## Evidence and reproducibility

The browser demo uses six Canadian and five U.S. synthetic cases. Its 108 stored combinations are independently computed at discrete tracking-error, fee, loss-utilization, and future-recapture settings. The browser is not an optimizer and does not interpolate new decisions.

A separate repeatable large-universe benchmark uses 4 correlated covariance factors, diagonal idiosyncratic variance, heterogeneous securities and tax lots, a 35% gross turnover cap, and one blocked security. On the development Windows computer:

| Assets | Tax lots | Runtime |
| ---: | ---: | ---: |
| 250 | 750 | 20.8 seconds |
| 500 | 1,500 | 58.4 seconds |

These are single synthetic cases and machine-specific wall-clock times. Both met the modeled constraints. Smaller deterministic comparisons at 50 and 100 assets matched the complete one-direction-neighbor search objective under their tested assumptions. Neither comparison proves reliable optimality on other portfolios.

To reproduce:

```bash
python -m pip install -e ".[test]"
python -m pytest -q test_canadian_rebalancing.py test_tax_rebalancing.py tests_package/
python -m tools.benchmark_scale --assets 500 --lots 3 --seed 19
```

## Implementation boundaries

The package does not reconstruct tradable integer-share orders, enforce lot sizes or minimum notional, model bid/ask spreads, market impact, settlement or broker restrictions, verify live prices, or submit orders. It does not file taxes, evaluate every wash or superficial-loss circumstance, calculate progressive personal tax, determine eligibility for any specific tax refund, or promise financial returns.

The intended use is research and offline decision support with independently validated inputs, sensitivity analysis, and manual review of any resulting trade plan.
