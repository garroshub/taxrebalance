"""Canadian ACB-based taxable rebalancing using only simulated CAD transactions.

Canadian positions are grouped by identical security across the taxpayer's
own taxable accounts. Each has ONE moving-average adjusted cost base (ACB)
pool. A sale cannot elect specific historic purchase lots. Distinct from the
US tax-lot method. Affiliated accounts are watched for superficial-loss
risks, but their holdings/basis are NOT pooled into the taxpayer's ACB.

The optimization model is an explicitly limited educational proxy: future
purchases must be monitored 30 days after any proposed loss sale. The conservative
lookback flag suppresses modeled current loss benefit, and does not determine
tax filing consequences or ACB adjustments from a disallowed superficial loss.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np
from .models import Scenario, TaxLot
from .optimizer import compare_methods


@dataclass(frozen=True)
class CADTransaction:
    date: date
    ticker: str
    side: Literal["BUY", "SELL"]
    shares: float
    price_cad: float
    fee_cad: float = 0.0
    account: str = "SIM-TAXABLE-1"

    def __post_init__(self):
        if not self.ticker or not self.account or self.side not in ("BUY", "SELL"):
            raise ValueError("Invalid simulated Canadian transaction")
        if self.shares <= 0 or self.price_cad <= 0 or self.fee_cad < 0:
            raise ValueError("Shares and prices positive, fees nonnegative")


@dataclass(frozen=True)
class ACBPool:
    ticker: str
    shares: float
    total_acb_cad: float
    acb_per_share_cad: float
    historical_realized_gain_cad: float
    acquisition_count: int


def replay_acb(transactions: tuple[CADTransaction, ...], as_of: date) -> dict[str, ACBPool]:
    """Average ACB for identical properties in own taxable accounts, in CAD.

    Purchases increase total ACB inclusive of acquisition fees. Sales realize
    gain from sale proceeds net of fees and average ACB immediately before
    the sale; selling does not change per-unit ACB of remaining units.
    """
    if not transactions:
        raise ValueError("A simulated transaction ledger is required")
    if list(transactions) != sorted(transactions, key=lambda t: t.date):
        raise ValueError("Canadian ACB events must be chronological")
    holdings: dict[str, list[float]] = {}
    for tx in transactions:
        if tx.date > as_of:
            continue
        q,basis,gains,count = holdings.get(tx.ticker,[0.,0.,0.,0.])
        if tx.side == "BUY":
            basis += tx.shares*tx.price_cad+tx.fee_cad
            q += tx.shares
            count += 1
        else:
            if tx.shares>q+1e-7:
                raise ValueError(f"Cannot sell more {tx.ticker} shares than owned")
            acb_per_share=basis/q if q else 0
            gains += tx.shares*(tx.price_cad-acb_per_share)-tx.fee_cad
            basis -= tx.shares*acb_per_share
            q -= tx.shares
            if q < 1e-8:
                q,basis=0.,0.
        holdings[tx.ticker]=[q,basis,gains,count]
    return {
       t:ACBPool(t,round(a[0],8),round(a[1],8),
            round(a[1]/a[0],8) if a[0]>1e-8 else 0.,
            round(a[2],8),int(a[3]))
       for t,a in holdings.items() if a[0]>1e-8
    }


@dataclass(frozen=True)
class CanadianScenario:
    name: str
    valuation_date: date
    tickers: tuple[str, ...]
    prices_cad: tuple[float, ...]
    target_weights: tuple[float, ...]
    annual_covariance: tuple[tuple[float, ...], ...]
    simulated_transactions: tuple[CADTransaction, ...]
    affiliated_recent_purchases: tuple[str, ...] = ()
    starting_cash_cad: float = 0.0
    max_tracking_error: float = 0.025
    transaction_cost_bps: float = 10.0
    marginal_tax_rate: float = 0.42
    capital_gain_inclusion_fraction: float = 0.50
    loss_utilization: float = 0.80
    future_recapture_fraction: float = 0.20
    risk_aversion: float = 1.0
    max_turnover_fraction: float | None = None
    restricted_tickers: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.tickers or set(self.affiliated_recent_purchases)-set(self.tickers):
            raise ValueError("Tickers/affiliated flags are invalid")
        if not (0 <= self.marginal_tax_rate <= 1 and
                0 <= self.capital_gain_inclusion_fraction <= 1):
            raise ValueError("Tax rates and inclusion must be within [0,1]")
        if any(t.date>self.valuation_date for t in self.simulated_transactions):
            raise ValueError("Future hypothetical purchases are scenario watches, not history")
        pools=replay_acb(self.simulated_transactions,self.valuation_date)
        if set(pools)!=set(self.tickers):
            raise ValueError("Every scenario asset needs a positive ACB pool")
        # Validate portfolio geometry with a deliberately separate CA adapter.
        self.to_solver_scenario()

    @property
    def pools(self) -> dict[str, ACBPool]:
        return replay_acb(self.simulated_transactions,self.valuation_date)

    @property
    def recent_buy_flags(self) -> dict[str, bool]:
        """Conservative 30-day lookback: a prior buy is a review flag if a
        loss sale is proposed; affiliation and day+30 ownership require
        subsequent verification in a real superficial-loss determination.
        """
        earliest=self.valuation_date-timedelta(days=30)
        recent={t for t in self.affiliated_recent_purchases}
        recent.update(tx.ticker for tx in self.simulated_transactions
            if tx.side=="BUY" and earliest<=tx.date<=self.valuation_date)
        return {t:t in recent for t in self.tickers}

    def to_solver_scenario(self) -> Scenario:
        """Map each ACB pool to ONE indivisible cost-basis representation.

        This is an optimization adapter, not an elective historic tax lot.
        Model US short/long tax rates are intentionally set equal so all CA
        holdings use the assumed CA inclusion fraction × marginal rate.
        """
        pools=self.pools
        flags=self.recent_buy_flags
        records=tuple(TaxLot(lot_id="ACB-"+t,ticker=t,shares=pools[t].shares,
               basis_per_share=pools[t].acb_per_share_cad,
               days_held=400,prior_30d_replacement=flags[t])
               for t in self.tickers)
        effective=self.marginal_tax_rate*self.capital_gain_inclusion_fraction
        return Scenario(
          name=self.name,tickers=self.tickers,prices=self.prices_cad,
          target_weights=self.target_weights,lots=records,
          annual_covariance=self.annual_covariance,
          starting_cash=self.starting_cash_cad,
          max_tracking_error=self.max_tracking_error,
          trading_cost_bps=self.transaction_cost_bps,
          short_term_tax_rate=effective,long_term_tax_rate=effective,
          loss_utilization=self.loss_utilization,
          future_recapture_fraction=self.future_recapture_fraction,
          risk_aversion=self.risk_aversion,jurisdiction="US",
          max_turnover_fraction=self.max_turnover_fraction,
          restricted_tickers=self.restricted_tickers)

    def solve(self) -> dict:
        solver=self.to_solver_scenario()
        results=compare_methods(solver)
        results["jurisdiction"]="Canada (illustrative CAD / average ACB)"
        results["tax_basis_method"]="Canadian pooled average adjusted cost base (ACB)"
        results["currency"]="CAD"
        results["tax_lots"]=[{
          "lot_id":"ACB-"+t,
          "ticker":t,
          "shares":self.pools[t].shares,
          "basis_per_share":self.pools[t].acb_per_share_cad,
          "total_acb_cad":self.pools[t].total_acb_cad,
          "days_held":None,
          "recent_replacement_flag":self.recent_buy_flags[t],
          "unrealized_gain_loss":round(
              (self.prices_cad[i]-self.pools[t].acb_per_share_cad)*self.pools[t].shares,2)
        } for i,t in enumerate(self.tickers)]
        results["assets"]=list(self.tickers)
        results["prices"]=dict(zip(self.tickers,self.prices_cad))
        results["parameters"]={
          "max_tracking_error_pct":self.max_tracking_error*100,
          "transaction_cost_bps":self.transaction_cost_bps,
          "loss_utilization":self.loss_utilization,
          "future_recapture_fraction":self.future_recapture_fraction,
          "marginal_tax_rate":self.marginal_tax_rate,
          "capital_gain_inclusion_fraction":self.capital_gain_inclusion_fraction,
          "risk_aversion":self.risk_aversion,
        }
        results["superficial_loss_watch"]={
          "lookback_30d_flagged_tickers":[t for t,v in self.recent_buy_flags.items() if v],
          "future_30d_identical_repurchase":"Must not assume permitted; any future buys or affiliated acquisitions require review",
          "at_day_30_ownership":"Not knowable at portfolio-decision time; must be monitored",
          "capital_loss_benefit":"Zero in model when flagged for recent acquisitions; conservative proxy, not CRA adjudication",
        }
        results["simulated_transactions_count"]=len(self.simulated_transactions)
        results["warning"]="All CAD amounts are synthetic. Affiliated holdings excluded from taxpayer's ACB but flagged for superficial-loss checks. No return filing or tax advice."
        return results


def review_superficial_loss(sale_date: date, shares_sold:float,
                           acquisitions: tuple[CADTransaction,...],
                           retained_substituted_shares_on_day_30:float,
                           identity_tickers: tuple[str,...],
                           affiliated_acquisitions: tuple[CADTransaction,...]=())->dict:
    """Educational retrospective quantity-screen, NOT a tax law decision.

    CRA requires acquisitions during +/-30 calendar days by taxpayer/affiliate
    AND ownership at end of the window. Approximate affected quantity using
    the lesser of disposed, acquired and still-held substituted shares.
    """
    if shares_sold<=0 or retained_substituted_shares_on_day_30<0:
        raise ValueError("Invalid sale or retained share quantity")
    lo=sale_date-timedelta(days=30)
    hi=sale_date+timedelta(days=30)
    buys=[tx for tx in (*acquisitions,*affiliated_acquisitions)
         if tx.side=="BUY" and tx.ticker in identity_tickers and lo<=tx.date<=hi]
    acquired=sum(tx.shares for tx in buys)
    affected=min(shares_sold,acquired,retained_substituted_shares_on_day_30)
    return {
       "acquired_in_window":round(acquired,6),
       "retained_day_30":retained_substituted_shares_on_day_30,
       "potentially_affected_shares":round(affected,6),
       "requires_review":affected>0,
       "determination":"illustrative quantity screen; check identity, affiliations, ACB adjustments and transactions"}


def canadian_demo(name="Canada / Base case", max_tracking_error=.025,
                  trading_cost_bps=10.,loss_utilization=.8,
                  affiliated_purchase=False,
                  future_recapture_fraction=.20)->CanadianScenario:
    """100k CAD simulated portfolio, own multi-account transaction history.

    Prices held at C$100, holdings XIC 400, XEF 300, XBB 200, XRE 100;
    target 25% each. XIC has a large averaged loss, XBB smaller loss.
    """
    from datetime import date
    symbols=("XIC","XEF","XBB","XRE")
    tx=(
      CADTransaction(date(2024,2,12),"XIC","BUY",200,145,account="SIM-A"),
      CADTransaction(date(2024,6,10),"XEF","BUY",300,94,account="SIM-A"),
      CADTransaction(date(2024,7,8),"XBB","BUY",200,108,account="SIM-A"),
      CADTransaction(date(2024,8,19),"XRE","BUY",100,80,account="SIM-A"),
      CADTransaction(date(2025,6,19),"XIC","BUY",200,119,account="SIM-B"),
    )
    stdev=np.array([.23,.20,.10,.26],dtype=float)
    cor=np.array([[1,.34,.06,.22],[.34,1,.04,.20],
                  [.06,.04,1,.08],[.22,.20,.08,1]],dtype=float)
    cov=cor*np.outer(stdev,stdev)
    return CanadianScenario(
        name=name,valuation_date=date(2026,10,8),
        tickers=symbols,prices_cad=(100.,100.,100.,100.),
        target_weights=(.25,.25,.25,.25),
        annual_covariance=tuple(tuple(float(x) for x in row) for row in cov),
        simulated_transactions=tx,
        affiliated_recent_purchases=("XIC",) if affiliated_purchase else (),
        max_tracking_error=max_tracking_error,
        transaction_cost_bps=trading_cost_bps,
        loss_utilization=loss_utilization,
        marginal_tax_rate=.42,
        capital_gain_inclusion_fraction=.50,
        future_recapture_fraction=future_recapture_fraction,
        risk_aversion=1.)
