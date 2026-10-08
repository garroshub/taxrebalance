"""Deterministic, auditable assumption-grid solver for static GitHub Pages.

Controls are discrete and every displayed result is a full fresh CVXPY solve.
No interpolation, client-calculated pseudo optimization, account upload or API.
The compact result payload is computed under fixed synthetic US/Canadian holdings.
"""
import sys
from pathlib import Path
from itertools import product
import json
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tax_rebalancing.canada import canadian_demo
from tax_rebalancing.scenarios import demonstration
from tax_rebalancing.optimizer import compare_methods

TRACKING_ERROR=(0.012,0.025,0.04)
TRADING_FEE=(5.0,10.0,40.0)
LOSS_UTILIZATION=(0.2,0.8)
FUTURE_RECAPTURE=(0.0,0.2)
CA_AFFILIATE=(False,True)
outdir=ROOT/"docs"/"data"
outdir.mkdir(parents=True,exist_ok=True)
rows=[]
started=time.perf_counter()
for country in ("CA","US"):
    affiliate_flags=CA_AFFILIATE if country=="CA" else (False,)
    for affiliate,te,fee,util,recapture in product(
        affiliate_flags,TRACKING_ERROR,TRADING_FEE,LOSS_UTILIZATION,FUTURE_RECAPTURE):
        if country=="CA":
            s=canadian_demo(name="Canada ACB simulation",max_tracking_error=te,
                  trading_cost_bps=fee,loss_utilization=util,
                  affiliated_purchase=affiliate,
                  future_recapture_fraction=recapture)
            result=s.solve()
        else:
            s=demonstration(name="U.S. tax-lot simulation",
                     tracking_error=te,trading_cost_bps=fee,
                     loss_utilization=util,
                     future_recapture_fraction=recapture)
            result=compare_methods(s)
        key=f"{country}:{int(affiliate)}:{te:.3f}:{fee:g}:{util:.1f}:{recapture:.1f}"
        methods=result["methods"]
        exact=next((m for m in methods if m["method"]=="enumerated_global_small_continuous"),None)
        heur=next((m for m in methods if m["method"]=="two_stage_convex_heuristic"),None)
        if exact and exact["feasible"] and heur and heur["feasible"]:
            assert heur["objective_dollars"]+0.05>=exact["objective_dollars"],key
        assert len(methods)==5,key
        rows.append({
            "key":key,
            "country":country,
            "affiliated":affiliate,
            "tracking_error":te,
            "trading_cost_bps":fee,
            "loss_utilization":util,
            "future_recapture_fraction":recapture,
            "methods":methods,
        })
        print("GRID_SOLVED",len(rows),key,
              "BEST",heur["objective_dollars"] if heur else "none",
              "ELAPSED",round(time.perf_counter()-started,1),flush=True)
payload={
    "version":"2026-10-08.1",
    "data_type":"precomputed_solver_grid",
    "models":"Synthetic Canadian pooled ACB and U.S. specific tax-lot models",
    "assumptions":{
        "tracking_error":list(TRACKING_ERROR),
        "trading_cost_bps":list(TRADING_FEE),
        "loss_utilization":list(LOSS_UTILIZATION),
        "affiliate_canada":list(CA_AFFILIATE),
        "future_recapture_fraction":list(FUTURE_RECAPTURE)
    },
    "disclaimer":"Every grid point was solved independently with CVXPY. Continuous shares, approximate tax rules, synthetic portfolios, modeled tax utilization and future recapture. No live accounts.",
    "cases":rows
}
path=outdir/"assumption_grid.json"
path.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),
                encoding="utf-8")
print("GRID_COMPLETE",len(rows),"SECONDS",round(time.perf_counter()-started,2),
      "BYTES",path.stat().st_size,flush=True)
