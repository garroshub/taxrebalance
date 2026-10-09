"""Tax-aware portfolio rebalancing with explicit tax and risk assumptions."""

from .api import (
    CanadaACB,
    Portfolio,
    RebalanceConfig,
    RebalanceResult,
    UnitedStatesLots,
    rebalance,
)
from tax_rebalancing.canada import CADTransaction, replay_acb, review_superficial_loss
from tax_rebalancing.models import TaxLot

__version__ = "0.1.0"
__all__ = [
    "CanadaACB", "Portfolio", "RebalanceConfig", "RebalanceResult",
    "UnitedStatesLots", "rebalance", "CADTransaction", "TaxLot",
    "replay_acb", "review_superficial_loss",
]
