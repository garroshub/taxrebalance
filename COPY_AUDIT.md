# Website copy review

Reviewed on 2026-10-08 using the local **ai-slop-checker** rubric and its latest short-label calibration. Scope: the public page's static text in `docs/index.html`, dynamically rendered PM, scenario and trade text in `docs/app.js`, and the repository's primary README. This is an editorial wording audit, not a statistical AI-authorship detector.

Each phrase was evaluated in its section context. Ordinary financial chart labels, tax terminology and necessary compliance warnings are retained even when brief. The following flagged examples were rewritten.

| Previous wording | Issue under rubric | Current wording |
| --- | --- | --- |
| Make the rebalance. Account for the tax. | Slogan-like phrasing | Portfolio trades and their tax costs |
| Portfolio Manager Decision Desk / Optimization Model | Redundant headline decoration | Removed; section begins with the decision problem |
| Presolved scenario | Unnatural technical wording | Simulated account |
| All available combinations have their own stored solver output | Wordy and indirect | Each setting loads a separate optimization result |
| Candidate algorithms: 05 | Low-information KPI for a PM | Trades in selected method, computed from the displayed trades |
| Selected method meets the risk limit | Generic conclusion without a concrete action | Buy [actual tickers], sell [actual tickers]; show realized TE vs limit |
| Model objective ($) | Currency and economic measure unclear | Modeled cost (CAD) or Modeled cost (USD) |
| No known flag | Could imply broader compliance than the synthetic data support | None in simulation |
| 3⁴ convex direction patterns | Dense table sublabel | 81 direction combinations |
| This combination was solved independently. Nothing on this page estimates an optimizer result by interpolation. | Defensive, repetitive formulation | Results were computed for the four settings shown |
| Cost–risk trade-off | Abstract header | Cost and tracking error |
| Tax-lot inventory (Canadian case) | Wrong jurisdiction-specific object | Canadian ACB inventory |
| '·' separators in navigation and transaction copy | AI-style dot punctuation | Plain phrases and sentence punctuation |
| Combined objective | Undefined without context | Total modeled cost, explicitly defined as tax, fees and risk penalty |

**Result:** the primary PM headings, cards, chart captions, controls, tooltips and simulated trade descriptions now describe a measurable object or a specific action. Structural metric labels and external-link indicators remain when they serve a real UI function. Compliance caveats state the particular limitations of the Canada and U.S. models.

The checker review does **not** certify the legal accuracy of a tax-loss claim, or that every future generated sentence will always satisfy the rubric. Numerical calculations and trading restrictions are covered by the separate optimizer and browser tests.
