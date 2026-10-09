"""Public input contracts and optimization interface."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from tax_rebalancing.canada import CADTransaction, CanadianScenario, replay_acb
from tax_rebalancing.models import Scenario, TaxLot
from tax_rebalancing.optimizer import (
    compare_methods,
    convex_relaxation_heuristic,
    exhaustive_small_benchmark,
    greedy_loss_harvest,
    hold_position,
    risk_only_rebalance,
)

METHODS = {
    "tax_aware": convex_relaxation_heuristic,
    "risk_only": risk_only_rebalance,
    "greedy": greedy_loss_harvest,
    "hold": hold_position,
    "small_exact": exhaustive_small_benchmark,
}


def _table(source: str | Path) -> list[dict[str, str]]:
    with Path(source).open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


@dataclass(frozen=True)
class Portfolio:
    jurisdiction: str
    prices: Mapping[str, float]
    cash: float = 0.0
    transactions: tuple[CADTransaction, ...] = ()
    tax_lots: tuple[TaxLot, ...] = ()
    valuation_date: date | None = None
    affiliated_recent_purchases: tuple[str, ...] = ()

    @classmethod
    def from_transactions(
        cls, path: str | Path, *, prices: Mapping[str, float],
        valuation_date: date | str, cash: float = 0.0,
        affiliated_recent_purchases: Sequence[str] = (),
    ) -> Portfolio:
        """Read Canadian purchases and sales from a dated CSV ledger."""
        day = date.fromisoformat(valuation_date) if isinstance(valuation_date, str) else valuation_date
        if not isinstance(day, date):
            raise ValueError("valuation_date must be an ISO date or date object")
        records = tuple(
            CADTransaction(
                date=date.fromisoformat(row["date"]),
                ticker=row["ticker"], side=row["side"].upper(),
                shares=float(row["shares"]), price_cad=float(row["price_cad"]),
                fee_cad=float(row.get("fee_cad") or 0),
                account=row.get("account") or "TAXABLE",
            )
            for row in _table(path)
        )
        return cls("CA", dict(prices), float(cash), records, (),
                   day, tuple(affiliated_recent_purchases))

    @classmethod
    def from_tax_lots(
        cls, source: str | Path | Sequence[TaxLot], *,
        prices: Mapping[str, float], cash: float = 0.0,
    ) -> Portfolio:
        """Read U.S. purchase lots from CSV or an existing list of TaxLot objects."""
        if isinstance(source, (str, Path)):
            lots = tuple(
                TaxLot(
                    lot_id=row["lot_id"], ticker=row["ticker"],
                    shares=float(row["shares"]),
                    basis_per_share=float(row["basis_per_share"]),
                    days_held=int(row["days_held"]),
                    prior_30d_replacement=(row.get("prior_30d_replacement", "").lower() in
                                           ("true", "1", "yes")),
                )
                for row in _table(source)
            )
        else:
            lots = tuple(source)
        return cls("US", dict(prices), float(cash), (), lots)


@dataclass(frozen=True)
class CanadaACB:
    marginal_rate: float = 0.42
    inclusion_rate: float = 0.50

    def __post_init__(self) -> None:
        if not all(np.isfinite(x) and 0 <= x <= 1
                   for x in (self.marginal_rate, self.inclusion_rate)):
            raise ValueError("Canadian tax parameters must be between 0 and 1")


@dataclass(frozen=True)
class UnitedStatesLots:
    short_term_rate: float = 0.35
    long_term_rate: float = 0.20

    def __post_init__(self) -> None:
        if not all(np.isfinite(x) and 0 <= x <= 1
                   for x in (self.short_term_rate, self.long_term_rate)):
            raise ValueError("U.S. tax parameters must be between 0 and 1")


@dataclass(frozen=True)
class RebalanceConfig:
    max_tracking_error: float = 0.025
    trading_cost_bps: float = 10.0
    loss_utilization: float = 0.80
    future_recapture_fraction: float = 0.20
    risk_aversion: float = 1.0
    direction_search_budget: int | None = None
    max_turnover_fraction: float | None = None
    restricted_tickers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        items = (self.max_tracking_error, self.trading_cost_bps,
                 self.loss_utilization, self.future_recapture_fraction, self.risk_aversion)
        if not all(np.isfinite(x) for x in items):
            raise ValueError("All optimization parameters must be finite")
        if not (0 < self.max_tracking_error < 1) or self.trading_cost_bps < 0 or self.risk_aversion < 0:
            raise ValueError("Tracking error, trading fees, or risk aversion are invalid")
        if not 0 <= self.loss_utilization <= 1 or not 0 <= self.future_recapture_fraction <= 1:
            raise ValueError("Loss and recapture fractions must be between 0 and 1")
        if self.direction_search_budget is not None and (
                isinstance(self.direction_search_budget, bool)
                or not isinstance(self.direction_search_budget, int)
                or self.direction_search_budget < 1):
            raise ValueError("direction_search_budget must be a positive integer")
        if self.max_turnover_fraction is not None and (
                not np.isfinite(self.max_turnover_fraction)
                or not 0 <= self.max_turnover_fraction <= 2):
            raise ValueError("max_turnover_fraction must be between 0 and 2")


@dataclass(frozen=True)
class RebalanceResult:
    method: str
    jurisdiction: str
    currency: str
    decision: dict
    initial_weights: dict[str, float]
    target_weights: dict[str, float]
    methods: tuple[dict, ...] = ()

    @property
    def trades(self) -> list[dict]:
        return list(self.decision["trades"])

    @property
    def feasible(self) -> bool:
        return bool(self.decision["feasible"])

    def summary(self) -> dict:
        keys = ("feasible", "objective_dollars", "tracking_error",
                "estimated_tax_current", "estimated_future_recapture",
                "transaction_cost", "risk_penalty", "post_cash",
                "solver_status", "violations", "explored_patterns", "relaxed_lower_bound",
                "gross_turnover_fraction", "search_limited", "search_budget")
        return {"method": self.method, "jurisdiction": self.jurisdiction,
                "currency": self.currency,
                **{key: self.decision.get(key) for key in keys},
                "trade_count": len(self.trades)}

    def to_dict(self) -> dict:
        return {"summary": self.summary(), "trades": self.trades,
                "initial_weights": self.initial_weights,
                "target_weights": self.target_weights,
                "methods": list(self.methods)}

    def to_json(self, path: str | Path | None = None) -> str:
        output = json.dumps(self.to_dict(), indent=2, allow_nan=False)
        if path is not None:
            Path(path).write_text(output + "\n", encoding="utf-8")
        return output

    def trades_to_csv(self, path: str | Path) -> None:
        rows = self.trades
        columns = sorted({key for row in rows for key in row})
        with Path(path).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)


def rebalance(
    portfolio: Portfolio, *, target_weights: Mapping[str, float],
    covariance: Sequence[Sequence[float]], tax_policy: CanadaACB | UnitedStatesLots,
    config: RebalanceConfig | None = None, method: str = "tax_aware",
    compare: bool = False,
) -> RebalanceResult:
    """Solve a continuous-share rebalancing decision with supplied market inputs.

    The result is conditional on the supplied prices, covariance, tax parameters,
    and risk objective. Tax-loss eligibility remains subject to external review.
    """
    if method not in METHODS:
        raise ValueError(f"Unknown method {method!r}; expected one of {tuple(METHODS)}")
    config = config or RebalanceConfig()
    tickers = tuple(portfolio.prices)
    if not tickers or set(tickers) != set(target_weights):
        raise ValueError("Prices and target weights must cover the same securities")
    if any(not isinstance(t, str) or not t for t in tickers):
        raise ValueError("Ticker names must be nonempty strings")
    if not np.isfinite(portfolio.cash) or portfolio.cash < 0:
        raise ValueError("Cash must be finite and nonnegative")
    price_values = tuple(float(portfolio.prices[t]) for t in tickers)
    weights = tuple(float(target_weights[t]) for t in tickers)
    matrix = np.asarray(covariance, dtype=float)
    if (matrix.shape != (len(tickers), len(tickers))
            or not np.all(np.isfinite(matrix))
            or not all(np.isfinite(x) for x in price_values + weights)):
        raise ValueError("Prices, target weights, and covariance must be finite and aligned")
    cov = tuple(tuple(float(x) for x in row) for row in matrix)

    if portfolio.jurisdiction == "CA" and isinstance(tax_policy, CanadaACB):
        if portfolio.valuation_date is None:
            raise ValueError("Canadian portfolios need a valuation date")
        if portfolio.tax_lots:
            raise ValueError("Canadian portfolios must use pooled transaction history")
        scenario = CanadianScenario(
            name="Portfolio", valuation_date=portfolio.valuation_date,
            tickers=tickers, prices_cad=price_values,
            target_weights=weights, annual_covariance=cov,
            simulated_transactions=portfolio.transactions,
            affiliated_recent_purchases=portfolio.affiliated_recent_purchases,
            starting_cash_cad=portfolio.cash,
            max_tracking_error=config.max_tracking_error,
            transaction_cost_bps=config.trading_cost_bps,
            marginal_tax_rate=tax_policy.marginal_rate,
            capital_gain_inclusion_fraction=tax_policy.inclusion_rate,
            loss_utilization=config.loss_utilization,
            future_recapture_fraction=config.future_recapture_fraction,
            risk_aversion=config.risk_aversion,
            max_turnover_fraction=config.max_turnover_fraction,
            restricted_tickers=tuple(config.restricted_tickers),
        ).to_solver_scenario()
        currency = "CAD"
    elif portfolio.jurisdiction == "US" and isinstance(tax_policy, UnitedStatesLots):
        if portfolio.transactions:
            raise ValueError("U.S. portfolios must supply individual tax lots")
        scenario = Scenario(
            name="Portfolio", tickers=tickers, prices=price_values,
            target_weights=weights, lots=portfolio.tax_lots,
            annual_covariance=cov, starting_cash=portfolio.cash,
            max_tracking_error=config.max_tracking_error,
            trading_cost_bps=config.trading_cost_bps,
            short_term_tax_rate=tax_policy.short_term_rate,
            long_term_tax_rate=tax_policy.long_term_rate,
            loss_utilization=config.loss_utilization,
            future_recapture_fraction=config.future_recapture_fraction,
            risk_aversion=config.risk_aversion,
            max_turnover_fraction=config.max_turnover_fraction,
            restricted_tickers=tuple(config.restricted_tickers),
        )
        currency = "USD"
    else:
        raise ValueError("Tax policy must match CA or US portfolio jurisdiction")

    if compare:
        results = compare_methods(scenario, include_exact=len(tickers) <= 4,
                                  max_evaluations=config.direction_search_budget)
        all_methods = tuple(results["methods"])
        internal = {
            "tax_aware": "two_stage_convex_heuristic",
            "risk_only": "risk_only_rebalance",
            "greedy": "greedy_loss_harvest",
            "hold": "hold",
            "small_exact": "enumerated_global_small_continuous",
        }
        decision = next(x for x in all_methods if x["method"] == internal[method])
    else:
        if method in ("tax_aware", "risk_only"):
            decision = METHODS[method](
                scenario, max_evaluations=config.direction_search_budget,
            ).as_dict()
        else:
            decision = METHODS[method](scenario).as_dict()
        all_methods = ()

    return RebalanceResult(
        method=method, jurisdiction=portfolio.jurisdiction,
        currency=currency, decision=decision,
        initial_weights=dict(zip(tickers, (float(x) for x in scenario.initial_weights))),
        target_weights=dict(zip(tickers, weights)), methods=all_methods,
    )
