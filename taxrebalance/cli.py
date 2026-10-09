"""Command line interface for local portfolio inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import (
    CanadaACB, Portfolio, RebalanceConfig, UnitedStatesLots, rebalance,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="taxrebalance", description="Tax-aware portfolio rebalancing"
    )
    parser.add_argument("--jurisdiction", choices=("CA", "US"), required=True)
    parser.add_argument("--portfolio", required=True, help="CSV transaction ledger or U.S. tax lots")
    parser.add_argument("--prices", required=True, help="JSON object mapping ticker to price")
    parser.add_argument("--targets", required=True, help="JSON object mapping ticker to target weight")
    parser.add_argument("--covariance", required=True, help="JSON annual covariance matrix")
    parser.add_argument("--valuation-date", help="YYYY-MM-DD for Canadian portfolios")
    parser.add_argument("--config", help="Optional JSON of RebalanceConfig parameters")
    parser.add_argument("--output", help="Write result as JSON")
    parser.add_argument("--method", choices=("tax_aware", "risk_only", "greedy", "hold", "small_exact"),
                        default="tax_aware")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args(argv)
    try:
        prices = json.loads(Path(args.prices).read_text(encoding="utf-8"))
        targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
        covariance = json.loads(Path(args.covariance).read_text(encoding="utf-8"))
        options = (json.loads(Path(args.config).read_text(encoding="utf-8"))
                   if args.config else {})
        cash = float(options.pop("cash", 0))
        config = RebalanceConfig(**options)
        if args.jurisdiction == "CA":
            if not args.valuation_date:
                parser.error("--valuation-date is required for CA")
            portfolio = Portfolio.from_transactions(
                args.portfolio, prices=prices,
                valuation_date=args.valuation_date, cash=cash,
            )
            policy = CanadaACB()
        else:
            portfolio = Portfolio.from_tax_lots(args.portfolio, prices=prices, cash=cash)
            policy = UnitedStatesLots()
        result = rebalance(
            portfolio, target_weights=targets, covariance=covariance,
            tax_policy=policy, config=config, method=args.method, compare=args.compare,
        )
        print(result.to_json(args.output))
        return 0 if result.feasible else 2
    except (KeyError, OSError, ValueError, TypeError) as error:
        parser.exit(2, f"taxrebalance: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
