"""Tax-Aware Rebalancing Lab data contracts.

US tax-lot research scenario only. No claim of final wash-sale determinations or
legal tax advice. Dollar-valued cost, tax-benefit, and risk penalties are
explicit assumptions in an illustrative one-period decision model.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np

@dataclass(frozen=True)
class TaxLot:
    lot_id: str
    ticker: str
    shares: float
    basis_per_share: float
    days_held: int
    prior_30d_replacement: bool = False

    def __post_init__(self):
        if not self.lot_id or not self.ticker:
            raise ValueError("Tax lots need unique identifiers and tickers")
        if self.shares <= 0 or self.basis_per_share <= 0 or self.days_held < 0:
            raise ValueError("Tax lot shares/basis must be positive and holding age nonnegative")

@dataclass(frozen=True)
class Scenario:
    name: str
    tickers: tuple[str, ...]
    prices: tuple[float, ...]
    target_weights: tuple[float, ...]
    lots: tuple[TaxLot, ...]
    annual_covariance: tuple[tuple[float, ...], ...]
    starting_cash: float = 0.0
    max_tracking_error: float = 0.025
    trading_cost_bps: float = 10.0
    short_term_tax_rate: float = 0.35
    long_term_tax_rate: float = 0.20
    loss_utilization: float = 0.80
    future_recapture_fraction: float = 0.20
    risk_aversion: float = 80.0
    jurisdiction: Literal["US"] = "US"

    def __post_init__(self):
        n=len(self.tickers)
        prices=np.asarray(self.prices,dtype=float)
        weights=np.asarray(self.target_weights,dtype=float)
        cov=np.asarray(self.annual_covariance,dtype=float)
        if n<2 or n!=len(set(self.tickers)) or prices.shape!=(n,) or weights.shape!=(n,):
            raise ValueError("At least two distinct assets and aligned price/weight vectors required")
        if np.any(prices<=0) or np.any(weights<0) or abs(weights.sum()-1)>1e-8:
            raise ValueError("Prices positive, target weights nonnegative and sum to 1")
        if cov.shape!=(n,n) or not np.allclose(cov,cov.T,atol=1e-9):
            raise ValueError("Annual covariance matrix shape/symmetry invalid")
        if min(np.linalg.eigvalsh(cov)) < -1e-10:
            raise ValueError("Annual covariance must be positive semidefinite")
        if not self.lots or len(set(z.lot_id for z in self.lots))!=len(self.lots):
            raise ValueError("Unique and nonempty tax lots required")
        if any(z.ticker not in self.tickers for z in self.lots):
            raise ValueError("A tax lot references an unknown asset")
        if self.starting_cash<0 or not 0<self.max_tracking_error<1 or self.trading_cost_bps<0:
            raise ValueError("Cash, tracking error and cost parameters invalid")
        if not all(0<=t<=1 for t in (self.short_term_tax_rate,self.long_term_tax_rate,self.loss_utilization,self.future_recapture_fraction)):
            raise ValueError("Tax parameters must lie in [0,1]")
        if self.risk_aversion<0 or self.jurisdiction!="US":
            raise ValueError("Only US tax-lot demonstration with nonnegative risk aversion is supported")

    @property
    def equity(self)->float:
        return float(self.starting_cash+sum(self.prices[self.tickers.index(z.ticker)]*z.shares for z in self.lots))

    @property
    def shares(self)->np.ndarray:
        return np.array([sum(z.shares for z in self.lots if z.ticker==t) for t in self.tickers],dtype=float)

    @property
    def initial_weights(self)->np.ndarray:
        return self.shares*np.asarray(self.prices)/self.equity

    def modify(self,**changes)->Scenario:
        return replace(self,**changes)
