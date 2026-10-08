"""Regenerate real solved demo datasets served by the static GitHub Pages UI.

All inputs synthetic; every displayed quantity is a solver result. UI switches
only between precomputed named scenarios. A changed arbitrary parameter
requires rerunning this generator instead of inventing a live optimum.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tax_rebalancing.optimizer import compare_methods
from tax_rebalancing.scenarios import demonstration
from tax_rebalancing.canada import canadian_demo

OUT=Path(__file__).resolve().parent.parent/"docs"/"data"
OUT.mkdir(parents=True,exist_ok=True)
PRESETS=[
 ("Baseline tax-aware decision",.025,.80,10.,.20),
 ("Tighter tracking error",.012,.80,10.,.20),
 ("Flexible risk tolerance",.040,.80,10.,.20),
 ("High trading costs",.025,.80,40.,.20),
 ("Limited usable tax losses",.025,.20,10.,.20),
]
# Canada is the first/default experience. All inputs are generated locally
# from simulated CAD purchases; there is no brokerage or real investor data.
CANADA_PRESETS=[
 ("Canada / Average ACB baseline",.025,.80,10.,False),
 ("Canada / Strict risk budget",.012,.80,10.,False),
 ("Canada / Flexible risk budget",.040,.80,10.,False),
 ("Canada / Higher trading fees",.025,.80,40.,False),
 ("Canada / Loss utilization limited",.025,.20,10.,False),
 ("Canada / Affiliated recent purchase",.025,.80,10.,True),
]
cases=[]
for name,te,util,cost,affiliate in CANADA_PRESETS:
    ca=canadian_demo(name,max_tracking_error=te,
              loss_utilization=util,trading_cost_bps=cost,
              affiliated_purchase=affiliate)
    result=ca.solve()
    cases.append(result)
    print("CANADA_SOLVED",name,
          [(m["method"],m["feasible"],m["objective_dollars"])
           for m in result["methods"]],flush=True)

for name,te,util,cost,recapture in PRESETS:
    s=demonstration(name,tracking_error=te,
         loss_utilization=util,trading_cost_bps=cost,
         future_recapture_fraction=recapture)
    result=compare_methods(s)
    result["jurisdiction"]="United States (illustrative USD tax lots)"
    result["tax_basis_method"]="US individual tax-lot identification (simplified)"
    result["currency"]="USD"
    result["parameters"]={
        "max_tracking_error_pct":100*s.max_tracking_error,
        "transaction_cost_bps":s.trading_cost_bps,
        "loss_utilization":s.loss_utilization,
        "future_recapture_fraction":s.future_recapture_fraction,
        "short_term_tax_rate":s.short_term_tax_rate,
        "long_term_tax_rate":s.long_term_tax_rate,
        "risk_aversion":s.risk_aversion,
        "starting_cash":s.starting_cash
    }
    result["prices"]=dict(zip(s.tickers,s.prices))
    result["assets"]=list(s.tickers)
    result["tax_lots"]=[{
      "lot_id":z.lot_id,"ticker":z.ticker,"shares":z.shares,
      "basis_per_share":z.basis_per_share,"days_held":z.days_held,
      "recent_replacement_flag":z.prior_30d_replacement,
      "unrealized_gain_loss":round(
        (s.prices[s.tickers.index(z.ticker)]-z.basis_per_share)*z.shares,2)
    } for z in s.lots]
    cases.append(result)
    methods={x["method"]:(x["feasible"],x["objective_dollars"]) for x in result["methods"]}
    print("SCENARIO",name,methods,flush=True)
out={
 "version":"0.2.0-simulation-only",
 "source":"Simulated Canada CAD ACB history and simulated US USD tax-lots; no user, brokerage or live market data",
 "method":"continuous-share convex direction enumeration; exact only in stated simplified model",
 "limitations":[
    "Canada: average ACB pools per identical security, not US specific-tax-lot identification",
    "Canada: 50% illustrative 2026 capital gains inclusion, 42% hypothetical marginal tax rate",
    "Canada: superficial loss depends on +/-30 calendar days, related acquisitions and day+30 substituted-property holdings",
    "US wash sales and Canadian superficial losses are NOT fully legally assessed",
    "Same-ticker buy/sell prohibition is a conservative proxy, not complete tax compliance",
    "Other identical securities, registered accounts, spouse and related accounts require verification",
    "Future tax-liability recapture and usable loss ratios are assumptions, not realized cash",
    "No future tax return, portfolio return or tax-alpha performance is predicted",
    "Continuous simulated shares, no real brokerage data, live market connections, or trade execution",
 ],
 "research_paper":{
    "title":"Tax-Aware Portfolio Construction via Convex Optimization",
    "url":"https://web.stanford.edu/~boyd/papers/tax_aware_portfolio.html"
 },
 "cases":cases
}
path=OUT/"scenarios.json"
path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
print("PRECOMPUTED",len(cases),"SCENARIOS",path,flush=True)
