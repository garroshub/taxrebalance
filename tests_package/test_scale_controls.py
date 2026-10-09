"""Numerical and trading-constraint checks for larger portfolios."""
from __future__ import annotations

import numpy as np
import pytest
from concurrent.futures import ThreadPoolExecutor

from taxrebalance import (
    Portfolio, RebalanceConfig, TaxLot, UnitedStatesLots, rebalance,
)


def make_portfolio(n: int, lots_per_asset: int, seed: int = 19):
    rng = np.random.default_rng(seed)
    tickers = tuple(f"S{i:04d}" for i in range(n))
    prices = dict(zip(tickers, rng.uniform(45.0, 170.0, size=n)))
    lots = tuple(
        TaxLot(
            lot_id=f"{ticker}-{j}", ticker=ticker,
            shares=float(rng.uniform(5.0, 40.0)),
            basis_per_share=float(prices[ticker] * rng.uniform(0.72, 1.3)),
            days_held=int(rng.choice([150, 210, 420, 750])),
            prior_30d_replacement=bool(j == 0 and i % 17 == 0),
        )
        for i, ticker in enumerate(tickers) for j in range(lots_per_asset)
    )
    holding_value = {t: prices[t] * sum(lot.shares for lot in lots if lot.ticker == t)
                     for t in tickers}
    weights = np.array([holding_value[t] for t in tickers], dtype=float)
    weights /= weights.sum()
    raw = weights * rng.uniform(0.50, 1.60, size=n)
    raw /= raw.sum()
    factors = rng.normal(0, 0.045, size=(n, 4))
    covariance = factors @ factors.T + np.diag(rng.uniform(0.10, 0.17, size=n) ** 2)
    return (Portfolio.from_tax_lots(lots, prices=prices),
            dict(zip(tickers, raw.tolist())), covariance, tickers)


@pytest.mark.parametrize("n,lots_per_asset", [(50, 3), (100, 5)])
def test_correlated_portfolio_with_trade_controls(n, lots_per_asset):
    portfolio, target, covariance, tickers = make_portfolio(n, lots_per_asset)
    max_turnover = 0.35
    restricted = (tickers[-1],)
    result = rebalance(
        portfolio, target_weights=target, covariance=covariance,
        tax_policy=UnitedStatesLots(),
        config=RebalanceConfig(
            max_tracking_error=0.03,
            trading_cost_bps=15,
            max_turnover_fraction=max_turnover,
            restricted_tickers=restricted,
        ),
    )
    decision = result.decision
    assert result.feasible, decision["violations"]
    assert decision["search_limited"]
    assert decision["explored_patterns"] <= 25
    assert decision["gross_turnover_fraction"] <= max_turnover + 1e-6
    assert decision["tracking_error"] <= 0.03002
    assert not any(trade["ticker"] in restricted for trade in result.trades)
    assert decision["post_cash"] >= -0.002
    buys = {trade["ticker"] for trade in result.trades if trade["side"] == "BUY"}
    sells = {trade["ticker"] for trade in result.trades if trade["side"] == "SELL"}
    assert not buys.intersection(sells)


def test_search_budget_and_input_validation():
    portfolio, target, covariance, tickers = make_portfolio(50, 2)
    result = rebalance(
        portfolio, target_weights=target, covariance=covariance,
        tax_policy=UnitedStatesLots(),
        config=RebalanceConfig(direction_search_budget=9),
    )
    assert result.decision["search_budget"] == 9
    assert result.decision["explored_patterns"] <= 9
    assert result.feasible
    with pytest.raises(ValueError, match="turnover"):
        RebalanceConfig(max_turnover_fraction=2.01)
    with pytest.raises(ValueError, match="positive integer"):
        RebalanceConfig(direction_search_budget=0)
    with pytest.raises(ValueError, match="Restricted"):
        rebalance(portfolio, target_weights=target, covariance=covariance,
                  tax_policy=UnitedStatesLots(),
                  config=RebalanceConfig(restricted_tickers=("UNKNOWN",)))


def test_impossible_turnover_cap_returns_infeasible():
    tickers = ("A", "B", "C", "D")
    lots = tuple(TaxLot(f"{t}-0", t, 10.0, 100.0, 450) for t in tickers)
    portfolio = Portfolio.from_tax_lots(lots, prices={t: 100.0 for t in tickers})
    result = rebalance(
        portfolio,
        target_weights={"A": 0.85, "B": 0.05, "C": 0.05, "D": 0.05},
        covariance=np.eye(4) * 0.09,
        tax_policy=UnitedStatesLots(),
        config=RebalanceConfig(max_tracking_error=0.01, max_turnover_fraction=0.02),
    )
    assert not result.feasible


def test_large_solver_isolated_between_threads():
    portfolio, target, covariance, _ = make_portfolio(50, 2)
    policy = UnitedStatesLots()

    def solve(budget):
        output = rebalance(
            portfolio, target_weights=target, covariance=covariance,
            tax_policy=policy, config=RebalanceConfig(direction_search_budget=budget),
        )
        return output.decision

    budgets = (5, 9, 13)
    sequential = [solve(b) for b in budgets]
    with ThreadPoolExecutor(max_workers=3) as pool:
        concurrent = list(pool.map(solve, budgets))
    for expected, observed in zip(sequential, concurrent):
        assert expected["feasible"] and observed["feasible"]
        assert observed["objective_dollars"] == pytest.approx(
            expected["objective_dollars"], abs=0.05)
        assert observed["gross_turnover_fraction"] == pytest.approx(
            expected["gross_turnover_fraction"], abs=0.0001)


def test_nonfinite_lot_rejected():
    with pytest.raises(ValueError, match="positive"):
        TaxLot("invalid", "XIC", float("nan"), 90.0, 200)
