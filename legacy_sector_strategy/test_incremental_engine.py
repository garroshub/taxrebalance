"""New execution mode: exact incremental two-leg orders and gross drift trim."""
import unittest
import pandas as pd
from test_execution_engine import fixture
from test_short_engine import pair_signal
from strategy_backtest import BacktestConfig,backtest_strategy

def cfg(**kwargs):
  args=dict(initial_capital=10000.,ma_windows=(2,3,4),vol_window=2,
       min_history=4,signal_threshold=.1,rebalance_every=5,
       cooldown_bars=3,transaction_cost_bps=10.,
       annual_borrow_cost_bps=200.,trailing_stop=.99,
       drawdown_stop=.99,execution_mode="incremental",
       gross_risk_response="trim",gross_drift_band=.10)
  args.update(kwargs)
  return BacktestConfig(**args)

class TestIncrementalPair(unittest.TestCase):
  def test_steady_pair_never_full_round_trips_on_scheduled_rebalance(self):
    d=fixture(35)
    sig=pair_signal(d)
    p,h=backtest_strategy(d,sig,cfg(transaction_cost_bps=0.,annual_borrow_cost_bps=0.))
    t=p.attrs["trades"]
    self.assertEqual(len(t),2)
    self.assertEqual(set(t.side),{"BUY","SHORT_SELL"})
    self.assertEqual(len(set(t.execution_date)),1)
    self.assertEqual(int((p.transaction_cost>0).sum()),0)
    self.assertTrue((h.gt(0).any(axis=1)==h.lt(0).any(axis=1)).all())

  def test_vix_transition_resizes_not_reopens_both_legs(self):
    d=fixture(35)
    d.loc[d.index[8:],"VIX"]=30
    p,h=backtest_strategy(d,pair_signal(d),cfg(annual_borrow_cost_bps=0))
    t=p.attrs["trades"]
    resize=t[t.reason=="risk_regime"]
    self.assertEqual(len(resize),2)
    self.assertEqual(set(resize.side),{"SELL","BUY_TO_COVER"})
    self.assertEqual(set(resize.signal_date),{d.index[8]})
    self.assertEqual(set(resize.execution_date),{d.index[9]})
    self.assertTrue((resize.shares.abs()<t[t.execution_date==d.index[4]].shares.abs().max()).all())
    self.assertLess(p.iloc[9].gross_exposure,.53)
    self.assertGreater(p.iloc[9].gross_exposure,.44)
    self.assertTrue((h.gt(0).any(axis=1)==h.lt(0).any(axis=1)).all())

  def test_no_spurious_margin_or_gross_exit_on_small_drift(self):
    d=fixture(45)
    d.loc[d.index[8:],"XLE"]=102
    p,h=backtest_strategy(d,pair_signal(d),cfg(annual_borrow_cost_bps=0))
    self.assertEqual(int(p.gross_limit_breach.sum()),0)
    self.assertFalse((p.attrs["trades"].reason=="gross_limit_exit").any())
    self.assertGreater(h.iloc[9].abs().sum(),0)

  def test_large_drift_trims_at_next_close_without_cash_cooldown(self):
    d=fixture(35)
    d.loc[d.index[8:],"XLE"]=120
    p,h=backtest_strategy(d,pair_signal(d),cfg(annual_borrow_cost_bps=0))
    self.assertTrue(bool(p.iloc[8].gross_limit_breach))
    trims=p.attrs["trades"].query("reason == 'gross_drift_trim'")
    self.assertTrue(len(trims)>0)
    self.assertTrue((trims.execution_date>=d.index[9]).all())
    self.assertGreater(h.iloc[9]["XLK"],0)
    self.assertLess(h.iloc[9]["XLE"],0)
    self.assertLess(p.iloc[9].gross_exposure,1.08)

  def test_margin_liquidation_still_exits_both(self):
    d=fixture(30)
    d.loc[d.index[8:],"XLE"]=240
    p,h=backtest_strategy(d,pair_signal(d),cfg(annual_borrow_cost_bps=0))
    self.assertTrue(bool(p.iloc[8].margin_breach))
    self.assertEqual(h.iloc[9].abs().sum(),0)
    self.assertEqual(set(p.attrs["trades"].query("reason == 'maintenance_margin_call'").side),{"SELL","BUY_TO_COVER"})

  def test_sign_flip_is_four_broker_side_transactions(self):
    d=fixture(30)
    sig=pair_signal(d)
    sig.loc[d.index[8]:,"XLK"]=-1.0
    sig.loc[d.index[8]:,"XLE"]=1.0
    p,h=backtest_strategy(d,sig,cfg(annual_borrow_cost_bps=0))
    trades=p.attrs["trades"].query("execution_date == @d.index[9]")
    self.assertEqual(set(trades.side),{"SELL","BUY_TO_COVER","SHORT_SELL","BUY"})
    self.assertGreater(h.iloc[9]["XLE"],0)
    self.assertLess(h.iloc[9]["XLK"],0)

  def test_trading_fees_and_borrow_reconcile(self):
    d=fixture(45)
    d.loc[d.index[9:],"VIX"]=30
    d.loc[d.index[19:],"VIX"]=20
    p,h=backtest_strategy(d,pair_signal(d),cfg(transaction_cost_bps=20,annual_borrow_cost_bps=300))
    trades=p.attrs["trades"]
    self.assertAlmostEqual(trades.fee.sum(),p.transaction_cost.sum(),places=7)
    self.assertAlmostEqual(p.borrow_cost.sum()+p.transaction_cost.sum(),p.cumulative_fees.iloc[-1],places=7)
    for date,sh in h.iterrows():
      marked=p.at[date,"cash"]+sum(sh[t]*d.at[date,t] for t in h.columns)
      self.assertAlmostEqual(marked,p.at[date,"value"],places=6)
    self.assertTrue((p.cash>=0).all())

  def test_no_future_leakage_into_earlier_trade_or_nav(self):
    d=fixture(45)
    s=pair_signal(d)
    p,h=backtest_strategy(d,s,cfg())
    d2=d.copy()
    d2.loc[d.index[22:],"XLK"]*=1.4
    p2,h2=backtest_strategy(d2,s,cfg())
    pd.testing.assert_frame_equal(h.iloc[:22],h2.iloc[:22])
    pd.testing.assert_series_equal(p.value.iloc[:22],p2.value.iloc[:22])

if __name__=="__main__":
    unittest.main()
