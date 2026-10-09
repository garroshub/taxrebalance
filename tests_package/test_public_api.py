"""Regression checks for installed public API and external input contracts."""
import csv
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from taxrebalance import (
    CanadaACB, Portfolio, RebalanceConfig, UnitedStatesLots, TaxLot, rebalance,
)
from tax_rebalancing.canada import canadian_demo
from tax_rebalancing.scenarios import demonstration


def test_canada_public_api_matches_legacy_model():
    s = canadian_demo()
    p = Portfolio(
        jurisdiction="CA", prices=dict(zip(s.tickers, s.prices_cad)),
        transactions=s.simulated_transactions, valuation_date=s.valuation_date,
    )
    result = rebalance(
        p, target_weights=dict(zip(s.tickers, s.target_weights)),
        covariance=s.annual_covariance, tax_policy=CanadaACB(), compare=True,
    )
    old = next(x for x in s.solve()["methods"]
               if x["method"] == "two_stage_convex_heuristic")
    assert result.feasible
    assert result.decision["objective_dollars"] == old["objective_dollars"]
    assert result.currency == "CAD"
    assert len(result.methods) == 5
    assert result.to_dict()["summary"]["trade_count"] == len(result.trades)


def test_us_public_api_matches_legacy_model():
    s = demonstration()
    p = Portfolio.from_tax_lots(s.lots, prices=dict(zip(s.tickers, s.prices)))
    result = rebalance(
        p, target_weights=dict(zip(s.tickers, s.target_weights)),
        covariance=s.annual_covariance, tax_policy=UnitedStatesLots(), compare=True,
    )
    from tax_rebalancing.optimizer import convex_relaxation_heuristic
    original = convex_relaxation_heuristic(s)
    assert result.feasible
    assert result.decision["objective_dollars"] == original.objective_dollars


def test_csv_io_and_failed_validation(tmp_path):
    path = tmp_path / "transactions.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["date", "ticker", "side", "shares", "price_cad", "fee_cad", "account"]
        )
        writer.writeheader()
        writer.writerows([
            dict(date="2024-01-01", ticker="A", side="BUY", shares="10", price_cad="100",
                 fee_cad="0", account="ONE"),
            dict(date="2024-01-02", ticker="B", side="BUY", shares="10", price_cad="100",
                 fee_cad="0", account="ONE"),
        ])
    p = Portfolio.from_transactions(path, prices={"A": 100, "B": 100},
                                    valuation_date="2026-10-08")
    cov = [[0.04, 0], [0, 0.04]]
    outcome = rebalance(p, target_weights={"A": .5, "B": .5}, covariance=cov,
                        tax_policy=CanadaACB())
    assert outcome.feasible
    assert json.loads(outcome.to_json())["summary"]["jurisdiction"] == "CA"
    outcome.trades_to_csv(tmp_path / "trades.csv")
    assert (tmp_path / "trades.csv").exists()
    with pytest.raises(ValueError, match="must match"):
        rebalance(p, target_weights={"A": .5, "B": .5}, covariance=cov,
                  tax_policy=UnitedStatesLots())
    with pytest.raises(ValueError, match="finite"):
        rebalance(p, target_weights={"A": .5, "B": .5},
                  covariance=[[float("nan"), 0], [0, 1]], tax_policy=CanadaACB())


@pytest.mark.parametrize("n", [5, 10, 20])
def test_multiasset_solver(n):
    tickers = tuple(f"ETF{i}" for i in range(n))
    lot = tuple(TaxLot(f"L{i}", t, 10, 110, 400) for i, t in enumerate(tickers))
    p = Portfolio.from_tax_lots(lot, prices={t:100.0 for t in tickers})
    covariance = np.eye(n) * 0.04
    result = rebalance(p, target_weights={t: 1/n for t in tickers},
                       covariance=covariance,
                       tax_policy=UnitedStatesLots())
    assert result.feasible
    assert result.decision["tracking_error"] <= .025 + 0.00002
    assert result.method == "tax_aware"
    assert not result.methods
    with pytest.raises(ValueError, match="at most four"):
        rebalance(p, target_weights={t: 1/n for t in tickers},
                  covariance=covariance, tax_policy=UnitedStatesLots(),
                  method="small_exact")
