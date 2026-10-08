"""Synthetic nonconvex tax-aware rebalancing decision tests, no market download."""
import unittest
from dataclasses import replace
import numpy as np

from tax_rebalancing.models import Scenario,TaxLot
from tax_rebalancing.scenarios import demonstration
from tax_rebalancing.optimizer import (
    compare_methods,convex_relaxation_heuristic,exhaustive_small_benchmark,
    risk_only_rebalance,greedy_loss_harvest,hold_position,evaluate
)

class TestTaxAwareDecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=demonstration()
        cls.results=compare_methods(cls.s)
        cls.by={m["method"]:m for m in cls.results["methods"]}

    def test_synthetic_starting_portfolio_reconciles(self):
        self.assertEqual(self.s.equity,100000.)
        np.testing.assert_allclose(self.s.initial_weights,[.35,.30,.20,.15])
        self.assertEqual(len(self.s.lots),10)
        self.assertEqual(sum(z.shares for z in self.s.lots),1000)

    def test_hold_reports_risk_infeasibility(self):
        h=self.by["hold"]
        self.assertFalse(h["feasible"])
        self.assertIn("tracking_error",h["violations"])
        self.assertEqual(h["transaction_cost"],0)

    def test_three_methods_and_global_benchmark_feasible(self):
        for name in ("risk_only_rebalance","greedy_loss_harvest",
                     "two_stage_convex_heuristic","enumerated_global_small_continuous"):
            d=self.by[name]
            self.assertTrue(d["feasible"],name+str(d["violations"]))
            self.assertLess(d["tracking_error"],self.s.max_tracking_error+1e-5)
            self.assertGreaterEqual(d["post_cash"],-0.001)

    def test_exact_method_is_no_worse_than_heuristic(self):
        h=self.by["two_stage_convex_heuristic"]
        g=self.by["enumerated_global_small_continuous"]
        self.assertLessEqual(g["objective_dollars"],h["objective_dollars"]+.01)
        self.assertGreaterEqual(h["explored_patterns"],1)
        self.assertEqual(g["explored_patterns"],3**len(self.s.tickers))

    def test_optimized_lot_trades_never_oversell(self):
        d=self.by["two_stage_convex_heuristic"]
        ids={z.lot_id:z for z in self.s.lots}
        seen={}
        for t in d["trades"]:
            if t["side"]=="SELL":
                self.assertIn(t["lot_id"],ids)
                seen[t["lot_id"]]=seen.get(t["lot_id"],0)+t["shares"]
        for lot_id,shares in seen.items():
            self.assertLessEqual(shares,ids[lot_id].shares+.0001)

    def test_conservative_same_ticker_buy_sale_exclusion(self):
        d=self.by["two_stage_convex_heuristic"]
        buys={t["ticker"] for t in d["trades"] if t["side"]=="BUY"}
        sells={t["ticker"] for t in d["trades"] if t["side"]=="SELL"}
        self.assertFalse(buys&sells)
        self.assertEqual(d["violations"],[])

    def test_cash_and_portfolio_value_conservation(self):
        d=self.by["two_stage_convex_heuristic"]
        x=np.asarray(self.s.shares).copy()
        p=dict(zip(self.s.tickers,self.s.prices))
        cash=self.s.starting_cash
        for t in d["trades"]:
            idx=self.s.tickers.index(t["ticker"])
            amount=t["shares"]*p[t["ticker"]]
            if t["side"]=="BUY":
                x[idx]+=t["shares"];cash-=amount
            else:
                x[idx]-=t["shares"];cash+=amount
        cash-=d["transaction_cost"]
        self.assertAlmostEqual(cash,d["post_cash"],places=2)
        np.testing.assert_allclose(x*np.asarray(self.s.prices)/self.s.equity,
                                   d["post_weights"],atol=.00001)

    def test_reporting_tax_breakdown_consistent(self):
        d=self.by["two_stage_convex_heuristic"]
        self.assertAlmostEqual(
            d["estimated_tax_current"]+d["estimated_future_recapture"],
            d["estimated_tax_pv"],places=3)
        self.assertAlmostEqual(
            d["estimated_tax_pv"]+d["transaction_cost"]+d["risk_penalty"],
            d["objective_dollars"],places=3)

    def test_recent_replacement_flag_no_immediate_loss_credit(self):
        flagged=self.s.modify(lots=tuple(
            replace(z,prior_30d_replacement=True)
            if z.lot_id=="K-201" else z for z in self.s.lots))
        lots={z.lot_id:z for z in flagged.lots}
        # Evaluate an explicit sale of K-201; tax reporting makes no claim of
        # usable capital loss when flagged as a recent replacement.
        z=np.zeros(len(flagged.lots));z[list(lots).index("K-201")]=10
        decision=evaluate(flagged,np.zeros(len(flagged.tickers)),z,
                         "probe_prior_replacement")
        trade=next(x for x in decision.trades if x["lot_id"]=="K-201")
        self.assertEqual(trade["tax_current_model"],0)
        self.assertEqual(trade["tax_future_model"],0)

    def test_invalid_covariance_and_unsupported_jurisdiction(self):
        with self.assertRaisesRegex(ValueError,"positive semidefinite"):
            self.s.modify(annual_covariance=((1,2,0,0),(2,1,0,0),
                        (0,0,1,0),(0,0,0,1)))
        with self.assertRaisesRegex(ValueError,"Only US"):
            self.s.modify(jurisdiction="CA")

    def test_no_loss_utilization_removes_immediate_loss_credit(self):
        s=self.s.modify(loss_utilization=0.)
        d=convex_relaxation_heuristic(s)
        self.assertTrue(d.feasible)
        self.assertGreaterEqual(d.estimated_tax_current,-.001)

    def test_tighter_risk_budget_keeps_feasible(self):
        s=self.s.modify(max_tracking_error=.012)
        d=convex_relaxation_heuristic(s)
        self.assertTrue(d.feasible)
        self.assertLessEqual(d.tracking_error,.01201)

    def test_fees_change_objective_and_cash_conservation(self):
        nofees=self.s.modify(trading_cost_bps=0.)
        nofee=convex_relaxation_heuristic(nofees)
        self.assertTrue(nofee.feasible)
        self.assertEqual(nofee.transaction_cost,0.)

if __name__=="__main__":
    unittest.main()
