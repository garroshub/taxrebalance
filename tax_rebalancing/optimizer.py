"""US tax-lot rebalancing: convex relaxation, directional heuristic, small exact comparison.

Continuous-share model. Sign disjunction (buy vs harvest a security) is
nonconvex. Each fixed-direction subproblem is convex. Enumerating all 3^N
direction choices is globally optimal only for this simplified continuous-
share model and solver tolerance, not for general tax law or integer lots.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from itertools import product
import cvxpy as cp
import numpy as np
from .models import Scenario

@dataclass
class Decision:
    method: str
    feasible: bool
    objective_dollars: float | None = None
    tracking_error: float | None = None
    estimated_tax_current: float | None = None
    estimated_future_recapture: float | None = None
    estimated_tax_pv: float | None = None
    transaction_cost: float | None = None
    risk_penalty: float | None = None
    post_cash: float | None = None
    trades: list[dict] = field(default_factory=list)
    post_weights: list[float] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    solver_status: str = ""
    explored_patterns: int = 0
    relaxed_lower_bound: float | None = None

    def as_dict(self):
        return vars(self).copy()

def _arrays(s):
    n=len(s.tickers);L=len(s.lots)
    price=np.asarray(s.prices,dtype=float)
    C=np.asarray(s.annual_covariance,dtype=float)
    incidence=np.zeros((n,L))
    lots=np.array([z.shares for z in s.lots])
    cur=np.zeros(L);future=np.zeros(L)
    for j,lot in enumerate(s.lots):
        i=s.tickers.index(lot.ticker)
        incidence[i,j]=1
        gain=price[i]-lot.basis_per_share
        rate=s.long_term_tax_rate if lot.days_held>=365 else s.short_term_tax_rate
        if gain>=0:
            cur[j]=gain*rate
        elif not lot.prior_30d_replacement:
            cur[j]=gain*rate*s.loss_utilization
            future[j]=-gain*rate*s.future_recapture_fraction
        # Prior related replacement buy: assume loss currently unusable.
    return price,C,incidence,lots,cur,future

def evaluate(s,buy,sell,method,status="feasible",patterns=0,lower_bound=None):
    price,C,A,limits,cur,fut=_arrays(s)
    b=np.maximum(0,np.array(buy,dtype=float))
    z=np.maximum(0,np.array(sell,dtype=float))
    shares=s.shares+b-A@z
    w=shares*price/s.equity
    delta=w-np.array(s.target_weights)
    te=float(np.sqrt(max(0,delta@C@delta)))
    value=float(price@b+(price@A)@z)
    fees=value*s.trading_cost_bps/10000
    now=float(cur@z); later=float(fut@z)
    risk=float(s.risk_aversion*s.equity*(delta@C@delta))
    cash=float(s.starting_cash+(price@A)@z-price@b-fees)
    violations=[]
    if te>s.max_tracking_error+0.00002:violations.append("tracking_error")
    if cash< -0.002:violations.append("insufficient_cash")
    if min(shares)< -1e-5:violations.append("short_positions")
    if np.any(z>limits+1e-5):violations.append("tax_lot_oversold")
    if np.any((b>1e-5)&((A@z)>1e-5)):violations.append("same_asset_buy_sell")
    trades=[]
    for i,ticker in enumerate(s.tickers):
        if b[i]>1e-5:
            trades.append({"ticker":ticker,"side":"BUY",
                 "shares":round(float(b[i]),5),"lot_id":None,
                 "notional":round(float(b[i]*price[i]),4)})
    for j,lot in enumerate(s.lots):
        if z[j]>1e-5:
            p=price[s.tickers.index(lot.ticker)]
            trades.append({"ticker":lot.ticker,"side":"SELL","lot_id":lot.lot_id,
                "shares":round(float(z[j]),5),
                "notional":round(float(z[j]*p),4),
                "basis_per_share":lot.basis_per_share,
                "days_held":lot.days_held,
                "realized_gain_loss":round(float((p-lot.basis_per_share)*z[j]),4),
                "tax_current_model":round(float(cur[j]*z[j]),4),
                "tax_future_model":round(float(fut[j]*z[j]),4),
                "recent_replacement_flag":lot.prior_30d_replacement})
    return Decision(method=method,feasible=not violations,
        objective_dollars=round(now+later+fees+risk,5),
        tracking_error=round(te,8),
        estimated_tax_current=round(now,5),
        estimated_future_recapture=round(later,5),
        estimated_tax_pv=round(now+later,5),
        transaction_cost=round(fees,5),
        risk_penalty=round(risk,5),
        post_cash=round(cash,5),trades=trades,
        post_weights=[round(float(x),7) for x in w],
        violations=sorted(set(violations)),solver_status=status,
        explored_patterns=patterns,
        relaxed_lower_bound=round(float(lower_bound),5) if lower_bound is not None else None)

def solve_direction(s,directions=None,tax_aware=True):
    """Buy/sell/hold direction vector fixed, or all relaxed when None."""
    p,C,A,lot_cap,tax0,tax1=_arrays(s)
    n=len(p)
    buys=cp.Variable(n,nonneg=True);sales=cp.Variable(len(lot_cap),nonneg=True)
    remain=s.shares+buys-A@sales
    weight=cp.multiply(p,remain)/s.equity
    diff=weight-np.array(s.target_weights)
    root=np.linalg.cholesky(C+1e-11*np.eye(n)).T
    gross=p@buys+(p@A)@sales
    fees=gross*(s.trading_cost_bps/10000)
    cash=s.starting_cash+(p@A)@sales-p@buys-fees
    cons=[remain>=0,sales<=lot_cap,cash>=0,
          cp.norm(root@diff)<=s.max_tracking_error]
    if directions is not None:
        for i,d in enumerate(directions):
            idx=np.flatnonzero(A[i])
            if d==-1:
                cons.append(buys[i]==0)
            elif d==1:
                for j in idx:cons.append(sales[j]==0)
            else:
                cons.append(buys[i]==0)
                for j in idx:cons.append(sales[j]==0)
    tax=(tax0+tax1)@sales if tax_aware else 0.
    problem=cp.Problem(cp.Minimize(
        s.risk_aversion*s.equity*cp.sum_squares(root@diff)+fees+tax),cons)
    try:
        problem.solve(solver="CLARABEL",max_iter=250,tol_gap_abs=1e-7,
             tol_feas=1e-7,verbose=False)
    except (cp.SolverError,ValueError):
        try:problem.solve(solver="SCS",eps=1e-6,max_iters=16000,verbose=False)
        except (cp.SolverError,ValueError):return None
    if problem.status not in ("optimal","optimal_inaccurate"):
        return None
    return (np.maximum(np.asarray(buys.value).reshape(-1),0),
            np.maximum(np.asarray(sales.value).reshape(-1),0),float(problem.value))

def _dirs(s,b,z):
    _,_,A,_,_,_=_arrays(s)
    net=b-A@z
    return tuple(1 if x>1e-4 else -1 if x< -1e-4 else 0 for x in net)

def _search(s,choices,method,tax_aware=True,lower_bound=None):
    best=None;tested=0
    for dirs in choices:
        tested+=1
        x=solve_direction(s,dirs,tax_aware=tax_aware)
        if x is None:continue
        d=evaluate(s,x[0],x[1],method,"convex_direction_solve",
                   tested,lower_bound)
        if not d.feasible:continue
        score=d.objective_dollars if tax_aware else x[2]
        if best is None or score<best[0]:best=(score,d)
    if best is None:
        return Decision(method,False,solver_status="infeasible",
                        violations=["no_feasible_direction"],explored_patterns=tested)
    best[1].explored_patterns=tested
    return best[1]

def convex_relaxation_heuristic(s):
    loose=solve_direction(s,None,tax_aware=True)
    if loose is None:
        return Decision("two_stage_convex_heuristic",False,
              solver_status="relaxation_infeasible",violations=["relaxation"])
    base=_dirs(s,loose[0],loose[1])
    options=[base]
    for i in range(len(base)):
        for side in (-1,0,1):
            if side!=base[i]:
                q=list(base);q[i]=side;options.append(tuple(q))
    return _search(s,dict.fromkeys(options),"two_stage_convex_heuristic",
                   lower_bound=loose[2])

def exhaustive_small_benchmark(s):
    if len(s.tickers)>4:
        raise ValueError("3^N enumeration benchmark supports at most four assets")
    return _search(s,product((-1,0,1),repeat=len(s.tickers)),
                   "enumerated_global_small_continuous")

def risk_only_rebalance(s):
    loose=solve_direction(s,None,tax_aware=False)
    if loose is None:
        return Decision("risk_only_rebalance",False,
                  solver_status="relaxation_infeasible",violations=["relaxation"])
    base=_dirs(s,loose[0],loose[1]);options=[base]
    for i in range(len(base)):
        for side in (-1,0,1):
            if side!=base[i]:
                q=list(base);q[i]=side;options.append(tuple(q))
    return _search(s,dict.fromkeys(options),"risk_only_rebalance",tax_aware=False)

def greedy_loss_harvest(s):
    """Keep risk-only signed asset trades; sell highest tax-benefit lots first."""
    base=risk_only_rebalance(s)
    if not base.feasible:
        base.method="greedy_loss_harvest";return base
    p,C,A,capacity,now,later=_arrays(s)
    buys=np.zeros(len(p));sales=np.zeros(len(s.lots))
    for t in base.trades:
        if t["side"]=="BUY":
            buys[s.tickers.index(t["ticker"])]+=t["shares"]
        else:
            idx=next(j for j,lot in enumerate(s.lots) if lot.lot_id==t["lot_id"])
            sales[idx]+=t["shares"]
    desired=A@sales
    sales[:]=0
    for i in range(len(p)):
        amount=float(desired[i])
        idx=sorted(np.flatnonzero(A[i]),key=lambda j:now[j]+later[j])
        for j in idx:
            quantity=min(capacity[j],amount)
            sales[j]=quantity;amount-=quantity
            if amount<1e-6:break
    return evaluate(s,buys,sales,"greedy_loss_harvest",
                    status="greedy_lot_reallocation_of_risk_only_trades")

def hold_position(s):
    return evaluate(s,np.zeros(len(s.tickers)),np.zeros(len(s.lots)),"hold")

def compare_methods(s,include_exact=True):
    methods=[hold_position(s),risk_only_rebalance(s),
             greedy_loss_harvest(s),convex_relaxation_heuristic(s)]
    if include_exact and len(s.tickers)<=4:
        methods.append(exhaustive_small_benchmark(s))
    reference=next((d for d in methods if d.method=="enumerated_global_small_continuous"
                    and d.feasible),None)
    if reference:
        for d in methods:
            if d.feasible and d.method=="two_stage_convex_heuristic":
                gap=d.objective_dollars-reference.objective_dollars
                d.solver_status+="; objective gap vs enumeration $"+format(gap,".3f")
    return {"scenario":s.name,"equity":s.equity,
       "initial_weights":[round(float(x),6) for x in s.initial_weights],
       "target_weights":list(s.target_weights),
       "max_tracking_error":s.max_tracking_error,
       "jurisdiction":"US tax-lot research approximation",
       "methods":[d.as_dict() for d in methods]}
