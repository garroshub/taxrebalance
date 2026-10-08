"""Reproducible synthetic taxable US ETF portfolio; no personal account data."""
from __future__ import annotations
import numpy as np
from .models import Scenario, TaxLot

def demonstration(name="Base case",tracking_error=0.025,
                  loss_utilization=0.80,trading_cost_bps=10.,
                  future_recapture_fraction=0.20)->Scenario:
    tickers=("XLK","XLF","XLV","XLE")
    # 100,000 USD portfolio. Shares by ticker: 350/300/200/150.
    lots=(
       TaxLot("K-201","XLK",150,130.,720),
       TaxLot("K-202","XLK",150,82.,200),
       TaxLot("K-203","XLK",50,107.,80),
       TaxLot("F-101","XLF",175,116.,850),
       TaxLot("F-102","XLF",75,70.,420),
       TaxLot("F-103","XLF",50,96.,50),
       TaxLot("V-301","XLV",75,125.,600,prior_30d_replacement=True),
       TaxLot("V-302","XLV",125,83.,100),
       TaxLot("E-401","XLE",75,135.,700),
       TaxLot("E-402","XLE",75,82.,170),
    )
    stdev=np.array([.24,.21,.18,.27])
    corr=np.full((4,4),.25)
    np.fill_diagonal(corr,1.)
    cov=(np.outer(stdev,stdev)*corr)
    return Scenario(
        name=name,tickers=tickers,prices=(100.,100.,100.,100.),
        target_weights=(.25,.25,.25,.25),lots=lots,
        annual_covariance=tuple(tuple(float(v) for v in row) for row in cov),
        starting_cash=0,max_tracking_error=tracking_error,
        trading_cost_bps=trading_cost_bps,
        short_term_tax_rate=.35,long_term_tax_rate=.20,
        loss_utilization=loss_utilization,
        future_recapture_fraction=future_recapture_fraction,
        # Synthetic research trade-off weight: low enough that the TE bound
        # is active and different allowed risk budgets yield different trades.
        # Not a calibrated investor preference.
        risk_aversion=1.,jurisdiction="US")
