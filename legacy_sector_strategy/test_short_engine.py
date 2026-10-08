"""Causal strongest-long / weakest-short paired sector ETF backtest regression tests."""
import unittest

import pandas as pd
import numpy as np

from strategy_backtest import BacktestConfig, _target, backtest_strategy, calculate_signals
from test_execution_engine import ASSETS, cfg as legacy_cfg, fixture

def cfg(**options):
    return legacy_cfg(allow_short=True, **options)

def pair_signal(data, best="XLK", worst="XLE", high=1.0, low=-1.0):
    s=pd.DataFrame(0.0,index=data.index,columns=list(ASSETS))
    s[best]=high
    s[worst]=low
    return s

def run(data,**options):
    return backtest_strategy(data,pair_signal(data),cfg(**options))


class TestSectorLongShortPair(unittest.TestCase):

    def test_two_distinct_cross_sectional_extremes_simultaneously(self):
        data=fixture()
        p,h=run(data)
        date=data.index[4]
        self.assertEqual(int(h.at[date,"XLK"]),49)
        self.assertEqual(int(h.at[date,"XLE"]),-49)
        self.assertEqual(int(h.loc[date].astype(bool).sum()),2)
        self.assertEqual(set(p.attrs["trades"]["side"]),{"BUY","SHORT_SELL"})
        self.assertEqual(set(p.attrs["trades"]["execution_date"]),{date})
        self.assertEqual(set(p.attrs["trades"]["signal_date"]),{data.index[3]})
        self.assertAlmostEqual(p.at[date,"net_exposure"],0.,places=10)
        self.assertAlmostEqual(p.at[date,"gross_exposure"],.98,places=10)

    def test_cross_sectional_even_if_every_sector_bullish(self):
        sig=pd.Series({"XLK":2.,"XLV":1.5,"XLE":1.0,"XLF":1.8,"XLI":1.3,"XLY":1.2})
        self.assertEqual(_target(sig,20.,cfg()),{"XLK":.5,"XLE":-.5})
        sig=-sig
        self.assertEqual(_target(sig,20.,cfg()),{"XLE":.5,"XLK":-.5})

    def test_spread_threshold_and_all_equal_signal_gates_pair(self):
        sig=pd.Series({t:1. for t in ASSETS})
        self.assertEqual(_target(sig,20.,cfg()),{})
        sig["XLK"]=1.05
        self.assertEqual(_target(sig,20.,cfg()),{})
        sig["XLK"]=1.25
        self.assertEqual(_target(sig,20.,cfg()),{"XLK":.5,"XLV":-.5})

    def test_half_gross_vix_scales_both_legs_together(self):
        s=pair_signal(fixture()).iloc[4]
        self.assertEqual(_target(s,30,cfg()),{"XLK":.25,"XLE":-.25})
        self.assertEqual(_target(s,60,cfg()),{})
        d=fixture(vix=30.)
        p,h=run(d)
        self.assertGreater(p.iloc[4].long_exposure,.23)
        self.assertLess(p.iloc[4].long_exposure,.26)
        self.assertGreater(p.iloc[4].short_exposure,.23)
        self.assertLess(p.iloc[4].short_exposure,.26)
        self.assertLess(abs(p.iloc[4].net_exposure),.011)

    def test_vix_extreme_closes_both_legs_at_next_close(self):
        d=fixture()
        d.loc[d.index[9:],"VIX"]=60
        p,h=run(d)
        self.assertGreater(h.iloc[9]["XLK"],0)
        self.assertLess(h.iloc[9]["XLE"],0)
        self.assertEqual(h.iloc[10].abs().sum(),0)
        exit_trades=p.attrs["trades"].query("reason == 'risk_regime' and execution_date == @d.index[10]")
        self.assertEqual(len(exit_trades),2)
        self.assertEqual(set(exit_trades.side),{"SELL","BUY_TO_COVER"})

    def test_exact_daily_share_nav_cash_and_collateral_reconciliation(self):
        d=fixture()
        d["XLK"]=100+np.arange(len(d))*.13
        d["XLE"]=100-np.arange(len(d))*.16
        p,h=run(d,transaction_cost_bps=15,slippage_bps=5,
                annual_borrow_cost_bps=300,rebalance_every=5)
        self.assertTrue((p.value>0).all())
        self.assertTrue((p.cash>=0).all())
        self.assertTrue((p.transaction_cost>=0).all())
        self.assertTrue((p.borrow_cost>=0).all())
        self.assertAlmostEqual(float(p.transaction_cost.sum()),float(p.attrs["trades"].fee.sum()),places=7)
        for date,hold in h.iterrows():
            marked=float(p.at[date,"cash"]+sum(hold[t]*d.at[date,t] for t in ASSETS))
            self.assertAlmostEqual(p.at[date,"value"],marked,places=7)
            short_notional=float(sum(-min(hold[t],0)*d.at[date,t] for t in ASSETS))
            self.assertAlmostEqual(p.at[date,"restricted_collateral"],1.5*short_notional,places=7)
            self.assertAlmostEqual(p.at[date,"available_cash"],
                                   p.at[date,"cash"]-1.5*short_notional,places=7)

    def test_pair_positive_spread_pnl_when_winner_rises_loser_falls(self):
        d=fixture()
        d.loc[d.index[8:],"XLK"]=120.
        d.loc[d.index[8:],"XLE"]=80.
        p,h=run(d,annual_borrow_cost_bps=0,transaction_cost_bps=0,
                trailing_stop=.99,drawdown_stop=.99)
        self.assertGreater(p.iloc[8].value,10_000)
        self.assertGreater(h.iloc[8]["XLK"],0)
        self.assertLess(h.iloc[8]["XLE"],0)

    def test_pair_negative_spread_pnl_when_winner_falls_loser_rises(self):
        d=fixture()
        d.loc[d.index[8:],"XLK"]=90.
        d.loc[d.index[8:],"XLE"]=110.
        p,h=run(d,annual_borrow_cost_bps=0,transaction_cost_bps=0,
                trailing_stop=.99,drawdown_stop=.99)
        self.assertLess(p.iloc[8].value,10_000)
        self.assertEqual(int(p.iloc[8].gross_limit_breach),1)

    def test_no_same_close_capture_of_first_trade_price_gap(self):
        d=fixture()
        d.loc[d.index[4],"XLK"]=140
        d.loc[d.index[4],"XLE"]=70
        p,h=run(d,transaction_cost_bps=0,annual_borrow_cost_bps=0)
        self.assertAlmostEqual(p.iloc[4].value,10_000,places=9)
        self.assertGreater(h.iloc[4]["XLK"],0)
        self.assertLess(h.iloc[4]["XLE"],0)
        self.assertTrue((p.attrs["trades"].signal_date<p.attrs["trades"].execution_date).all())

    def test_pair_trailing_long_or_short_stop_liquidates_both(self):
        for asset, new_value in [("XLK",90.),("XLE",110.)]:
            with self.subTest(asset=asset):
                d=fixture()
                d.loc[d.index[8:],asset]=new_value
                p,h=run(d,annual_borrow_cost_bps=0,transaction_cost_bps=0,
                        trailing_stop=.05,drawdown_stop=.99,
                        max_gross_exposure=1)
                # A gap may trigger the trailing stop without breaching gross;
                # when both trigger, exposure protection takes precedence.
                self.assertEqual(h.iloc[9].abs().sum(),0)
                exits=p.attrs["trades"].query("execution_date == @d.index[9]")
                self.assertEqual(set(exits.side),{"SELL","BUY_TO_COVER"})
                self.assertEqual(len(set(exits.reason)),1)
                self.assertIn(exits.iloc[0].reason,("trailing_stop","gross_limit_exit"))

    def test_pair_changes_both_instruments_at_one_rebalance(self):
        d=fixture()
        sig=pair_signal(d)
        sig.loc[d.index[8:],"XLV"]=2.
        sig.loc[d.index[8:],"XLF"]=-2.
        p,h=backtest_strategy(d,sig,cfg(rebalance_every=5,trailing_stop=.99,
                                       drawdown_stop=.99,annual_borrow_cost_bps=0))
        later=d.index[9]
        self.assertGreater(h.loc[later,"XLV"],0)
        self.assertLess(h.loc[later,"XLF"],0)
        self.assertEqual(h.loc[later,"XLK"],0)
        self.assertEqual(h.loc[later,"XLE"],0)
        # Sell and cover original pair, buy and short new pair.
        events=p.attrs["trades"].query("execution_date == @later")
        self.assertEqual(set(events.side),{"SELL","BUY_TO_COVER","BUY","SHORT_SELL"})

    def test_true_margin_call_versus_gross_limit_risk(self):
        d=fixture()
        d.loc[d.index[8:],"XLE"]=240.
        p,h=run(d,annual_borrow_cost_bps=0,transaction_cost_bps=0,
                trailing_stop=.99,drawdown_stop=.99)
        self.assertTrue(p.iloc[8].gross_limit_breach)
        self.assertTrue(p.iloc[8].margin_breach)
        self.assertEqual(h.iloc[9].abs().sum(),0)
        exits=p.attrs["trades"].query("reason == 'maintenance_margin_call'")
        self.assertEqual(set(exits.side),{"SELL","BUY_TO_COVER"})

    def test_borrow_fee_always_reduces_pair_nav(self):
        d=fixture()
        a,_=run(d,annual_borrow_cost_bps=0,transaction_cost_bps=0)
        b,_=run(d,annual_borrow_cost_bps=500,transaction_cost_bps=0)
        self.assertLess(b.iloc[6].value,a.iloc[6].value)
        self.assertGreater(b.borrow_cost.sum(),0)

    def test_no_future_input_leakage_into_signals_and_positions(self):
        d=fixture(190)
        for k in ASSETS:
            d[k]=100+np.arange(len(d))*(0.2 if k=="XLK" else -.02)
        c=cfg(ma_windows=(10,40,140),vol_window=30,min_history=140)
        scores=calculate_signals(d,c)
        d2=d.copy()
        d2.loc[d2.index[166:],"XLK"]*=3
        scores2=calculate_signals(d2,c)
        pd.testing.assert_frame_equal(scores.iloc[:166],scores2.iloc[:166])
        p1,h1=backtest_strategy(d,scores,c)
        p2,h2=backtest_strategy(d2,scores2,c)
        pd.testing.assert_series_equal(p1.value.iloc[:166],p2.value.iloc[:166])
        pd.testing.assert_frame_equal(h1.iloc[:166],h2.iloc[:166])

    def test_invalid_naked_pair_and_non_sector_instrument_rejected(self):
        d=fixture()
        signal=pair_signal(d).assign(VIX=-1000)
        with self.assertRaisesRegex(ValueError,"only tradable"):
            backtest_strategy(d,signal,cfg())
        with self.assertRaisesRegex(ValueError,"at least two"):
            backtest_strategy(d.drop(columns=["XLV","XLE","XLF","XLI","XLY"]),config=cfg())


if __name__=="__main__":
    unittest.main()
