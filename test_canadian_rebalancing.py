"""Canada-only, CAD-denominated synthetic ACB and superficial-loss tests."""
import unittest
from dataclasses import replace
from datetime import date,timedelta
import numpy as np

from tax_rebalancing.canada import (
 CADTransaction, CanadianScenario, canadian_demo, replay_acb,
 review_superficial_loss
)

class TestCanadianACB(unittest.TestCase):
    def test_acb_average_across_own_taxable_accounts(self):
        s=canadian_demo()
        x=s.pools["XIC"]
        self.assertEqual(x.shares,400.)
        self.assertEqual(x.total_acb_cad,52800.)
        self.assertEqual(x.acb_per_share_cad,132.)
        self.assertEqual(x.acquisition_count,2)
        self.assertEqual(s.to_solver_scenario().lots[0].lot_id,"ACB-XIC")

    def test_acb_sell_uses_average_and_remains_unchanged(self):
        t=(
          CADTransaction(date(2025,1,1),"ABC","BUY",10,80,1,account="SIM-A"),
          CADTransaction(date(2025,2,1),"ABC","BUY",10,120,1,account="SIM-B"),
          CADTransaction(date(2025,3,1),"ABC","SELL",5,150,2,account="SIM-A"),
        )
        p=replay_acb(t,date(2025,3,1))["ABC"]
        self.assertEqual(p.shares,15)
        self.assertAlmostEqual(p.acb_per_share_cad,100.1)
        self.assertAlmostEqual(p.total_acb_cad,1501.5)
        self.assertAlmostEqual(p.historical_realized_gain_cad,(150-100.1)*5-2)

    def test_invalid_sale_and_time_order_rejected(self):
        t=(CADTransaction(date(2025,1,2),"ABC","BUY",1,100),
           CADTransaction(date(2025,1,3),"ABC","SELL",2,100))
        with self.assertRaisesRegex(ValueError,"Cannot sell"):
            replay_acb(t,date(2025,1,3))
        with self.assertRaisesRegex(ValueError,"chronological"):
            replay_acb(t[::-1],date(2025,1,3))

    def test_unrealized_loss_uses_single_acb_not_elective_lots(self):
        s=canadian_demo()
        out=s.solve()
        self.assertEqual(out["tax_basis_method"],"Canadian pooled average adjusted cost base (ACB)")
        self.assertEqual([p["lot_id"] for p in out["tax_lots"]],
            ["ACB-XIC","ACB-XEF","ACB-XBB","ACB-XRE"])
        self.assertEqual(out["tax_lots"][0]["unrealized_gain_loss"],-12800.)
        self.assertEqual(out["tax_lots"][0]["days_held"],None)
        for x in out["methods"]:
            for trade in x["trades"]:
                if trade["side"]=="SELL":
                    self.assertEqual(trade["lot_id"],"ACB-"+trade["ticker"])

    def test_half_inclusion_applies_to_all_capital_gains_not_us_holding_period(self):
        s=canadian_demo()
        adapter=s.to_solver_scenario()
        self.assertAlmostEqual(adapter.long_term_tax_rate,.21)
        self.assertAlmostEqual(adapter.short_term_tax_rate,.21)
        self.assertAlmostEqual(adapter.loss_utilization,.8)

    def test_all_candidate_methods_and_enumeration(self):
        s=canadian_demo()
        result=s.solve()
        methods={m["method"]:m for m in result["methods"]}
        self.assertFalse(methods["hold"]["feasible"])
        for name in ("risk_only_rebalance","greedy_loss_harvest",
                     "two_stage_convex_heuristic",
                     "enumerated_global_small_continuous"):
            m=methods[name]
            self.assertTrue(m["feasible"],name+str(m["violations"]))
            self.assertLessEqual(m["tracking_error"],s.max_tracking_error+.00002)
            self.assertGreaterEqual(m["post_cash"],-.002)
        heuristic=methods["two_stage_convex_heuristic"]
        exact=methods["enumerated_global_small_continuous"]
        self.assertLessEqual(exact["objective_dollars"],heuristic["objective_dollars"]+.02)
        self.assertEqual(exact["explored_patterns"],81)

    def test_conservative_affiliated_lookback_suppresses_loss_credit(self):
        s=canadian_demo(affiliated_purchase=True)
        self.assertTrue(s.recent_buy_flags["XIC"])
        adapter=s.to_solver_scenario()
        self.assertTrue(adapter.lots[0].prior_30d_replacement)
        # Under the CA flag a sale of a loss pool is never reported as a
        # currently realizable tax credit, pending an actual legal review.
        out=s.solve()
        for method in out["methods"]:
            for tr in method["trades"]:
                if tr["side"]=="SELL" and tr["ticker"]=="XIC":
                    self.assertEqual(tr["tax_current_model"],0)
                    self.assertTrue(tr["recent_replacement_flag"])
        self.assertIn("XIC",out["superficial_loss_watch"]["lookback_30d_flagged_tickers"])

    def test_actual_own_lookback_buy_creates_warning(self):
        s=canadian_demo()
        tx=s.simulated_transactions+(
          CADTransaction(date(2026,9,20),"XIC","BUY",5,95,account="SIM-B"),
        )
        ss=replace(s,simulated_transactions=tx)
        self.assertTrue(ss.recent_buy_flags["XIC"])
        self.assertAlmostEqual(ss.pools["XIC"].acb_per_share_cad,
             (52800+475)/405)

    def test_30_day_calendar_window_and_end_hold_required(self):
        sold=date(2026,10,8)
        before=CADTransaction(sold-timedelta(days=30),"XIC","BUY",15,99)
        after=CADTransaction(sold+timedelta(days=30),"XIC","BUY",15,99)
        too_early=CADTransaction(sold-timedelta(days=31),"XIC","BUY",999,99)
        too_late=CADTransaction(sold+timedelta(days=31),"XIC","BUY",999,99)
        review=review_superficial_loss(sold,100,
            (too_early,before,after,too_late),
            20,("XIC",))
        self.assertEqual(review["acquired_in_window"],30)
        self.assertEqual(review["potentially_affected_shares"],20)
        self.assertTrue(review["requires_review"])
        no_hold=review_superficial_loss(sold,100,(before,),0,("XIC",))
        self.assertFalse(no_hold["requires_review"])

    def test_affiliated_transactions_watch_separate_from_acb(self):
        sold=date(2026,10,8)
        family_buy=CADTransaction(sold+timedelta(days=7),
                         "XIC","BUY",10,100,account="AFFILIATED-SIM")
        review=review_superficial_loss(sold,30,(),10,("XIC",),
                            affiliated_acquisitions=(family_buy,))
        self.assertEqual(review["potentially_affected_shares"],10)
        self.assertTrue(review["requires_review"])
        s=canadian_demo()
        self.assertEqual(s.pools["XIC"].shares,400)

    def test_future_transactions_not_misrepresented_as_history(self):
        s=canadian_demo()
        extra=CADTransaction(date(2026,10,9),"XIC","BUY",5,99)
        with self.assertRaisesRegex(ValueError,"Future hypothetical purchases"):
            replace(s,simulated_transactions=s.simulated_transactions+(extra,))

    def test_cannot_use_us_tax_lot_holding_period_rate(self):
        s=canadian_demo()
        self.assertEqual(len(s.to_solver_scenario().lots),len(s.tickers))
        self.assertAlmostEqual(s.to_solver_scenario().long_term_tax_rate,
                               s.to_solver_scenario().short_term_tax_rate)

    def test_all_values_are_synthetic_cad_and_no_broker_dependencies(self):
        out=canadian_demo().solve()
        self.assertEqual(out["currency"],"CAD")
        self.assertEqual(out["equity"],100000.)
        self.assertIn("Canada",out["jurisdiction"])
        self.assertTrue(out["simulated_transactions_count"]>0)
        self.assertEqual(len(out["tax_lots"]),4)

if __name__=="__main__":
    unittest.main()
