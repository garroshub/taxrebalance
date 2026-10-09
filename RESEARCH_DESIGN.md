# Research Design — TaxRebalance (Simulation Only)

## Research question

For a **given target allocation**, can tax-aware trading directions and sales improve modeled after-tax portfolio implementation value over risk-only or greedy rebalancing, without violating tracking error, cash and position constraints? This work is **not a trading strategy**, does not predict returns, and uses **synthetic portfolios only**.

## Two independently defined tax-accounting inputs

### Canadian CAD / average ACB (the default project scenario)

All trades are generated in a fictitious Canadian account history. Transactions have date, account label, security, BUY/SELL direction, shares, CAD price and CAD fee. The taxpayer's own holdings of an identical security across its fictional taxable accounts are pooled to compute total adjusted cost base. A purchase increases total ACB by shares × price + purchase fee. A partial sale subtracts **the previous averaged ACB per share × shares sold**, and reports capital gain/loss as sale proceeds less selling fee and that averaged ACB. Partial sales do not change the surviving shares' ACB per unit. Affiliated-person holdings are NOT pooled with the taxpayer's ACB.

The optimizer sees **one ACB pseudo-pool for each ticker**, not selectable U.S.-style purchase lots. Its reported sells have ID ACB-TICKER for audit. The independent tax-rate input is *capital gains inclusion fraction × illustrative marginal income tax rate*. The default simulation assumes **50% × 42% = 21%** as a synthetic marginal realized capital-gain cost proxy. Changes to the Canadian capital gains inclusion proposal were cancelled according to [Finance Canada's 2026 tax expenditure report](https://www.canada.ca/en/department-finance/services/publications/federal-tax-expenditures/2026/part-2.html). This project deliberately does not implement progressive income taxes, net capital-loss carryback/carryforward computations, year-by-year inclusion-rate adjustments, AMT, provincial filing or foreign currency conversion.

Superficial-loss screening is separate from ACB:
- A flagged acquisition of identical property by the taxpayer or an affiliated person during the **30 calendar days before** a proposed loss sale causes the optimizer to withhold its immediate *modeled* tax benefit as a conservative approximation.
- A separate scenario-review function examines **both 30-day sides** and shares of substituted property held on day+30, using synthetic hypothetical future transactions. It returns a potential affected-share count (the minimum of sold, acquired and retained), **not an authoritative Canadian tax-law determination**.
- Post-sale purchases, related holdings, identity classes, partial-denial rules, RRSP/TFSA-related effects and actual disallowed-loss ACB adjustments are not automatically resolved. A proposed future tax loss benefit may become unavailable, and an affiliated person's ACB is not merged into the taxpayer's cost pool.
- Sources: [CRA identical properties / ACB](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/special-rules-other-transactions.html) and [CRA superficial losses](https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/capital-losses-deductions.html).

### U.S. USD / elective tax lots

The existing U.S. model retains a purchase-specific cost basis, holding age, short-/long-term tax assumptions and a limited prior-replacement flag for each fictional tax lot. Its wash-sale screen is incomplete; the U.S. model is **not a tax-lot implementation to be reused in Canada**. See [IRS Publication 550](https://www.irs.gov/publications/p550).

## Shared optimization structure

For security i, let p_i be the simulated price, w_i* the manager-specified target, b_i the buy shares, s_j the number of units sold from simulated U.S. lot j or Canadian averaged pool j, V current modeled portfolio equity, and Sigma the assumed annual covariance.

Posttrade shares = old shares + purchases − sales, and w_i+ = p_i × posttrade shares / V.

The objective is:

    modeled current tax effect
    + discounted proxy for future recapture
    + trading fees on total buy and sell notional
    + risk_aversion × V × (posttrade_weights − target_weights)'
        × annual_covariance × (posttrade_weights − target_weights)

Constraints are:
- annualized tracking error at most epsilon
- sales never exceed existing lots/ACB pools
- nonnegative stock shares and posttrade cash (no margin financing)
- a security may BUY, SELL or HOLD on one modeled rebalancing date, but not buy and sell simultaneously

The direction disjunction makes this simplified model **nonconvex**; conditional on directions each problem is convex.

### Algorithm set

1. Hold portfolio, even if not risk-feasible (infeasible cases flagged).
2. Risk-only: minimize tracking-error penalty and trading costs, measure modeled taxes afterward.
3. Greedy: preserve risk-only per-security trade quantities and select best U.S. tax lots; for Canada, each ticker has a single average ACB and greedy offers **no tax-lot selection freedom**.
4. Two-stage heuristic: solve relaxed convex problem (a lower bound), choose buy/sell/hold directions, re-solve with feasible constraints and search one-security direction neighbors.
5. Small global benchmark: for 4 assets enumerate all 3^4 = 81 direction vectors; solve each convex subproblem. This is a global comparator only for the **continuous-share** toy model to numerical tolerances, not integer trading or legal tax compliance.

Inspired by [Moehle et al., Tax-Aware Portfolio Construction via Convex Optimization](https://web.stanford.edu/~boyd/papers/tax_aware_portfolio.html). Implemented with CVXPY/Clarabel and fallback SCS.

## Synthetic experiment design

### Canada (six solved scenarios)

4 Canadian-listed ETFs (XIC, XEF, XBB, XRE), fictional C$100,000 account, target 25% per sector, synthetic 2024–2025 CAD purchases in fictitious SIM-A and SIM-B taxable accounts, 2026-10-08 simulated valuation date and CAD price C$100 for each. XIC has 200 shares at C$145 and another 200 at C$119, pooled into **400 units at C$132 average ACB**.

Six predetermined cases: 2.5% TE baseline, 1.2% TE strict budget, 4% TE flexible budget, 40bps higher trading fee, 20% usable-loss assumption, and a simulated affiliated person's recent acquisition of identical property.

Base-case model objectives (not refunds): Risk-only **−C$482.99**, Greedy ACB **−C$482.99**, Two-stage heuristic **−C$969.88**, 81-direction global comparator **−C$969.88**. No-trade breaches TE cap.

### U.S. (five solved scenarios)

A different US$100,000 synthetic account with 4 ETFs and 10 elective purchase lots. Cases vary TE, trading fee, loss-use assumptions. Baseline Risk-only +US$149.49, Greedy −US$357.37, heuristic −US$719.48 and enumerated comparator −US$719.48.

**Modeled objective values combine tax assumptions, trading fees and risk penalty, so neither country result is a dollar saving guaranteed to the investor.** The risk penalty weight of 1.0 is deliberately illustrative, not calibrated.

## Tests and reproducibility

Run:

```bash
python -m unittest -v test_canadian_rebalancing test_tax_rebalancing
python tools/build_demo_data.py
python -m http.server 8000 --directory docs
```

The 11 complete solved outputs live in docs/data/scenarios.json and are consumed by the static webpage. Changing a scenario parameter requires re-running the numerical optimizer. The page defaults to Canada, offering a separate switch to the U.S. model and correct CAD/USD currency.

Tests cover Canadian ACB averaging across own fictional accounts, acquisition/sale fees, loss on partial sale, dated ±30-day review windows and remaining-substituted-share screen, affiliate watch, clear avoidance of U.S. elective lot choice, 4-asset feasible optimization, cash/position/TE accounting and the exact small-model comparator. Legacy U.S. regression tests remain separate.

## Boundaries and planned simulation-only research

The prototype omits legally exhaustive wash/superficial-loss rulings, adjusted ACB treatment of a denied loss, actual historical tax returns, option/deemed dispositions, foreign exchange, bid/ask liquidity, real prices, whole-share reconstruction and brokerage execution. **There will be no brokerage or personal investment data connection.**

Next evaluations will use **only simulated** portfolios with 20/50/100 securities, randomized ACB and tax basis histories, loss-use rates, compliance-review stress cases, risk budgets and solver runtimes. Compare algorithm gaps, lot/cash infeasibility, trade volume and risk deviation, rather than portfolio CAGR or claimed alpha.
