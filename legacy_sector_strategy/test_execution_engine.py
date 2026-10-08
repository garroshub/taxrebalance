"""Execution invariants and leakage tests for the auditable strategy engine.

No network or brokers. Explicit synthetic prices let us assert fill timing,
cash conservation, stop timing, fees and trading restrictions exactly.
"""
import unittest

import numpy as np
import pandas as pd

import model
from strategy_backtest import BacktestConfig, calculate_signals, backtest_strategy


ASSETS = ("XLK", "XLV", "XLE", "XLF", "XLI", "XLY")


def fixture(n=28, *, vix=20.0, value=100.0):
    days=pd.date_range("2023-01-02",periods=n,freq="B")
    result=pd.DataFrame(index=days)
    result["SPY"]=value
    for k in ASSETS:
        result[k]=value
    result["VIX"]=vix
    return result


def fixed_signals(data, winner="XLK", score=1.0):
    s=pd.DataFrame(0.0,index=data.index,columns=list(ASSETS))
    s[winner]=score
    return s


def cfg(**kwargs):
    opts=dict(initial_capital=10_000.,ma_windows=(2,3,4),vol_window=2,
              min_history=4,signal_threshold=0.1,
              rebalance_every=20,cooldown_bars=5,transaction_cost_bps=0,
              slippage_bps=0,trailing_stop=.05,drawdown_stop=.2,
              allow_short=False,execution_mode="liquidate_reopen",
              gross_risk_response="exit")
    opts.update(kwargs)
    return BacktestConfig(**opts)


class TestAuditedBacktest(unittest.TestCase):

    def test_market_index_and_vix_cannot_be_positions_or_signals(self):
        d=fixture()
        sig=calculate_signals(d,cfg())
        self.assertEqual(list(sig.columns),list(ASSETS))
        portfolio,positions=backtest_strategy(d,fixed_signals(d),cfg())
        self.assertTrue(set(positions.columns).isdisjoint({"VIX","SPY"}))
        self.assertTrue(set(portfolio.attrs["trades"]["ticker"]).issubset(set(ASSETS)))
        bad=fixed_signals(d).assign(VIX=99)
        with self.assertRaisesRegex(ValueError,"only tradable"):
            backtest_strategy(d,bad,cfg())

    def test_signal_close_t_only_fills_at_next_close(self):
        d=fixture()
        p,h=backtest_strategy(d,fixed_signals(d),cfg())
        # warmup=4; first eligible signal at i=3, trade at i=4
        self.assertTrue((h.iloc[:4].sum(axis=1)==0).all())
        self.assertEqual(int(h.iloc[4]["XLK"]),100)
        self.assertEqual(len(p.attrs["trades"]),1)
        trade=p.attrs["trades"].iloc[0]
        self.assertEqual(trade["signal_date"],d.index[3])
        self.assertEqual(trade["execution_date"],d.index[4])

    def test_no_future_price_leakage_into_earlier_trades(self):
        d=fixture()
        sig=fixed_signals(d)
        p1,h1=backtest_strategy(d,sig,cfg())
        d2=d.copy()
        d2.loc[d2.index[18:],"XLK"]*=2
        p2,h2=backtest_strategy(d2,sig,cfg())
        pd.testing.assert_series_equal(p1["value"].iloc[:18],p2["value"].iloc[:18])
        pd.testing.assert_frame_equal(h1.iloc[:18],h2.iloc[:18])
        self.assertNotEqual(p1["value"].iloc[-1],p2["value"].iloc[-1])

    def test_one_day_price_jump_belongs_to_preexisting_holder_not_same_day_new_trade(self):
        d=fixture()
        d.loc[d.index[4],"XLK"]=200.0
        p,h=backtest_strategy(d,fixed_signals(d),cfg())
        # Signal i=3 -> buy at the inflated i=4 closing price, no free +100% jump.
        self.assertAlmostEqual(p.loc[d.index[4],"return"],0.0,places=12)
        self.assertEqual(int(h.loc[d.index[4],"XLK"]),50)
        self.assertAlmostEqual(p.loc[d.index[4],"value"],10_000.0,places=8)

    def test_cash_accounting_exposure_and_cost_conservation(self):
        d=fixture()
        d["XLK"]=100+np.arange(len(d),dtype=float)*.2
        d.loc[d.index[13]:,"VIX"]=27.
        p,h=backtest_strategy(d,fixed_signals(d),cfg(
            transaction_cost_bps=15,slippage_bps=5,rebalance_every=5
        ))
        self.assertGreater(len(p.attrs["trades"]),1)
        self.assertGreater(p["transaction_cost"].sum(),0)
        self.assertTrue((p.cash>=-1e-9).all())
        self.assertTrue((p.gross_exposure<=1+1e-9).all())
        for ix,row in h.iterrows():
            nav=p.at[ix,"value"]
            calc=p.at[ix,"cash"]+sum(row[k]*d.at[ix,k] for k in ASSETS)
            self.assertAlmostEqual(nav,calc,places=7)
        self.assertAlmostEqual(p.transaction_cost.sum(),p.attrs["trades"].fee.sum(),places=8)
        # turnover is half of total purchase+sale notional divided by pre-trade NAV
        self.assertTrue((p.turnover>=0).all())

    def test_vix_extreme_liquidates_next_close(self):
        d=fixture()
        d.loc[d.index[9]:,"VIX"]=60.
        p,h=backtest_strategy(d,fixed_signals(d),cfg())
        self.assertGreater(h.iloc[9].sum(),0)
        self.assertEqual(h.iloc[10].sum(),0)
        self.assertEqual(p.iloc[10].gross_exposure,0.0)
        self.assertTrue((h.iloc[10:].sum(axis=1)==0).all())
        trades=p.attrs["trades"]
        self.assertEqual(trades.iloc[-1].reason,"risk_regime")
        self.assertEqual(trades.iloc[-1].signal_date,d.index[9])
        self.assertEqual(trades.iloc[-1].execution_date,d.index[10])

    def test_high_vix_half_risk_exposure_and_no_shorting(self):
        d=fixture(vix=30.0)
        p,h=backtest_strategy(d,fixed_signals(d),cfg())
        self.assertTrue((h>=0).all().all())
        self.assertGreater(p.iloc[4].gross_exposure,.45)
        self.assertLessEqual(p.iloc[4].gross_exposure,.50+1e-9)
        self.assertGreater(p.iloc[4].cash,4_999)

    def test_trailing_stop_exits_after_one_bar_delay(self):
        d=fixture()
        d.loc[d.index[8],"XLK"]=110.
        d.loc[d.index[9],"XLK"]=103.
        d.loc[d.index[10:],"XLK"]=103.
        p,h=backtest_strategy(d,fixed_signals(d),cfg(trailing_stop=.05))
        self.assertGreater(h.iloc[9]["XLK"],0)
        self.assertEqual(h.iloc[10]["XLK"],0)
        exits=p.attrs["trades"].query("reason == 'trailing_stop'")
        self.assertEqual(len(exits),1)
        self.assertEqual(exits.iloc[0].signal_date,d.index[9])
        self.assertEqual(exits.iloc[0].execution_date,d.index[10])

    def test_drawdown_kill_exits_with_delayed_fill(self):
        d=fixture()
        d.loc[d.index[8],"XLK"]=75.0
        d.loc[d.index[9:],"XLK"]=75.0
        p,h=backtest_strategy(d,fixed_signals(d),cfg(
            trailing_stop=.99,drawdown_stop=.2
        ))
        self.assertGreater(h.iloc[8]["XLK"],0)
        self.assertEqual(h.iloc[9]["XLK"],0)
        exits=p.attrs["trades"].query("reason == 'portfolio_drawdown_stop'")
        self.assertEqual(len(exits),1)
        self.assertEqual(exits.iloc[0].signal_date,d.index[8])
        self.assertEqual(exits.iloc[0].execution_date,d.index[9])

    def test_invalid_dates_prices_and_signal_index_rejected(self):
        d=fixture()
        bad=d.copy();bad.loc[bad.index[4],"XLK"]=0.
        with self.assertRaisesRegex(ValueError,"positive"):
            backtest_strategy(bad,config=cfg())
        bad=d.iloc[::-1]
        with self.assertRaisesRegex(ValueError,"sorted"):
            backtest_strategy(bad,config=cfg())
        with self.assertRaisesRegex(ValueError,"dates"):
            backtest_strategy(d,signals=fixed_signals(d).iloc[1:],config=cfg())

    def test_fee_reduces_returns_against_zero_cost_control(self):
        d=fixture()
        d.loc[d.index[5:],"XLK"]=105.0
        sig=fixed_signals(d)
        fee,_=backtest_strategy(d,sig,cfg(transaction_cost_bps=20))
        no_fee,_=backtest_strategy(d,sig,cfg(transaction_cost_bps=0))
        self.assertLess(fee.value.iloc[-1],no_fee.value.iloc[-1])
        self.assertGreater(fee.cumulative_fees.iloc[-1],0)

    def test_full_model_signals_only_use_past_to_current(self):
        d=fixture(190)
        for i in range(len(d)):
            d.iloc[i,d.columns.get_loc("XLK")]=100*(1+i*.002)
        a=calculate_signals(d,BacktestConfig())
        future=d.copy()
        future.loc[future.index[160:],"XLK"]*=4
        b=calculate_signals(future,BacktestConfig())
        pd.testing.assert_frame_equal(a.iloc[:160],b.iloc[:160])

    def test_model_public_rolling_output_contract(self):
        d=fixture(1260)
        # Under controlled no-price-change inputs the curve should stay
        # close to initial capital, with explicit 0-cost assumption.
        old = (model.TRANSACTION_COST_BPS, model.SLIPPAGE_BPS)
        try:
            model.TRANSACTION_COST_BPS = 0
            model.SLIPPAGE_BPS = 0
            result=model.rolling_backtest(d)
            self.assertEqual(len(result),1)
            for field in ["Start Date","End Date","Window Days","Strategy Return",
                          "Average Turnover","Max Gross Exposure","Negative Cash Days"]:
                self.assertIn(field,result)
            self.assertLessEqual(float(result["Max Gross Exposure"].iloc[0]),1+1e-8)
        finally:
            model.TRANSACTION_COST_BPS,model.SLIPPAGE_BPS=old


if __name__=="__main__":
    unittest.main()
