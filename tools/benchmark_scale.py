"""Reproducible scale benchmark for synthetic tax-aware portfolios."""
from __future__ import annotations

import argparse
import json
from time import perf_counter

import numpy as np

from taxrebalance import (
    Portfolio, RebalanceConfig, TaxLot, UnitedStatesLots, rebalance,
)


def benchmark(assets: int, lots_per_asset: int, seed: int) -> dict:
    if assets < 2 or lots_per_asset < 1:
        raise ValueError("At least two assets and one lot per asset are required")
    rng = np.random.default_rng(seed)
    tickers = tuple(f"S{i:04d}" for i in range(assets))
    prices = dict(zip(tickers, rng.uniform(45.0, 170.0, assets)))
    lots = tuple(
        TaxLot(
            lot_id=f"{ticker}-{j}", ticker=ticker,
            shares=float(rng.uniform(5, 40)),
            basis_per_share=float(prices[ticker] * rng.uniform(.72, 1.3)),
            days_held=int(rng.choice([150, 210, 420, 750])),
            prior_30d_replacement=(j == 0 and i % 17 == 0),
        )
        for i, ticker in enumerate(tickers) for j in range(lots_per_asset)
    )
    value = np.array([
        prices[t] * sum(z.shares for z in lots if z.ticker == t)
        for t in tickers
    ])
    weights = value / value.sum()
    targets = weights * rng.uniform(.50, 1.60, assets)
    targets /= targets.sum()
    factors = rng.normal(0, .045, (assets, 4))
    covariance = factors @ factors.T + np.diag(
        rng.uniform(.10, .17, assets) ** 2
    )
    start = perf_counter()
    decision = rebalance(
        Portfolio.from_tax_lots(lots, prices=prices),
        target_weights=dict(zip(tickers, targets.tolist())),
        covariance=covariance,
        tax_policy=UnitedStatesLots(),
        config=RebalanceConfig(
            max_tracking_error=.03,
            trading_cost_bps=15,
            max_turnover_fraction=.35,
            restricted_tickers=(tickers[-1],),
        ),
    )
    elapsed = perf_counter() - start
    d = decision.decision
    return {
        "assets": assets,
        "tax_lots": len(lots),
        "seed": seed,
        "elapsed_seconds": round(elapsed, 3),
        "feasible": d["feasible"],
        "tracking_error": d["tracking_error"],
        "gross_turnover_fraction": d["gross_turnover_fraction"],
        "trade_entries": len(decision.trades),
        "explored_direction_patterns": d["explored_patterns"],
        "search_limited": d["search_limited"],
        "modeled_objective": d["objective_dollars"],
        "relaxation_lower_bound": d["relaxed_lower_bound"],
        "violations": d["violations"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=int, default=100)
    parser.add_argument("--lots", type=int, default=3)
    parser.add_argument("--seed", type=int, default=19)
    args = parser.parse_args()
    report = benchmark(args.assets, args.lots, args.seed)
    print(json.dumps(report, indent=2))
    if not report["feasible"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
