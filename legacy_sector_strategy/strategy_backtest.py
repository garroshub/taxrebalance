"""Auditable simultaneous strongest-long / weakest-short sector pair backtester.

Bar t closes -> signal at t -> execution at bar t+1 *close*. Close-only
data cannot simulate next-open fills or intraday stops. Sector ETF shorts have
signed shares, segregated proceeds, margin checks, and daily borrow charges.
VIX is not tradable; stock borrow availability is assumed, not observed.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
import numpy as np
import pandas as pd

SECTORS = ("XLK", "XLV", "XLE", "XLF", "XLI", "XLY")


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    ma_windows: tuple[int, ...] = (10, 40, 140)
    vol_window: int = 30
    min_history: int = 140
    signal_threshold: float = 0.10
    vix_high: float = 25.0
    vix_extreme: float = 50.0
    trailing_stop: float = 0.05
    drawdown_stop: float = 0.20
    rebalance_every: int = 21
    cooldown_bars: int = 21
    transaction_cost_bps: float = 10.0
    slippage_bps: float = 0.0
    annual_borrow_cost_bps: float = 200.0
    initial_short_margin: float = 0.50
    maintenance_short_margin: float = 0.30
    max_gross_exposure: float = 1.0
    short_execution_buffer: float = 0.01
    allow_short: bool = True
    signal_method: str = "ma_energy"
    execution_mode: str = "incremental"
    gross_risk_response: str = "trim"
    gross_drift_band: float = 0.10

    def __post_init__(self):
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not self.ma_windows or min(self.ma_windows) < 2:
            raise ValueError("ma_windows need positive windows >= 2")
        if self.vol_window < 2 or self.min_history < 2:
            raise ValueError("vol_window and min_history must be >= 2")
        if self.rebalance_every < 1 or self.cooldown_bars < 1:
            raise ValueError("rebalance_every and cooldown_bars must be >= 1")
        if not 0 < self.trailing_stop < 1 or not 0 < self.drawdown_stop < 1:
            raise ValueError("stop thresholds must be fractions in (0, 1)")
        if self.vix_high <= 0 or self.vix_extreme <= self.vix_high:
            raise ValueError("vix_extreme must exceed vix_high")
        if min(self.transaction_cost_bps,self.slippage_bps,self.annual_borrow_cost_bps) < 0:
            raise ValueError("trading costs cannot be negative")
        if not 0<=self.maintenance_short_margin<=self.initial_short_margin<=1:
            raise ValueError("short margin: 0 <= maintenance <= initial <= 1")
        if not 0<self.max_gross_exposure<=1:
            raise ValueError("this backtester supports <=100% initial gross exposure, not margin-financed leverage")
        if not 0<=self.short_execution_buffer<.10:
            raise ValueError("short_execution_buffer must be in [0, 0.1)")
        if self.signal_method not in ("ma_energy", "momentum"):
            raise ValueError("signal_method must be ma_energy or momentum")
        if self.execution_mode not in ("liquidate_reopen", "incremental"):
            raise ValueError("execution_mode must be liquidate_reopen or incremental")
        if self.gross_risk_response not in ("exit", "trim"):
            raise ValueError("gross_risk_response must be exit or trim")
        if not 0 <= self.gross_drift_band <= 0.25:
            raise ValueError("gross_drift_band must be in [0, .25]")

    @property
    def warmup(self) -> int:
        return max(self.min_history, max(self.ma_windows), self.vol_window + 2)


def _validate_prices(data: pd.DataFrame) -> list[str]:
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Prices must be a nonempty DataFrame")
    if not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError("Price dates must be unique and sorted ascending")
    if "SPY" not in data or "VIX" not in data:
        raise ValueError("Prices must include SPY benchmark and VIX risk feature")
    assets = [s for s in SECTORS if s in data]
    if len(assets)<2:
        raise ValueError("The sector pair requires at least two tradable ETFs")
    frame = data[["SPY", "VIX", *assets]]
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Prices must be finite without missing observations")
    if (frame <= 0).any().any():
        raise ValueError("Prices and VIX must be positive")
    return assets


def calculate_signals(data: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    """End-of-day scores: fixed multihorizon SMA distance / trailing daily volatility.

    VIX and SPY are always excluded from tradable rankings. All features use
    past-or-current prices and are first actionable at the following close.
    """
    assets = _validate_prices(data)
    close = data[assets].astype(float)
    result = pd.DataFrame(index=close.index, columns=assets, dtype=float)
    if config.signal_method == "momentum":
        result.loc[:, :] = close.pct_change(periods=max(config.ma_windows)).to_numpy()
    else:
        horizons=tuple(sorted(set(config.ma_windows)))
        weights=np.array([1.0 / np.sqrt(w) for w in horizons], dtype=float)
        weights/=weights.sum()
        dist=sum(
            weight * (close / close.rolling(w, min_periods=w).mean() - 1.0)
            for weight, w in zip(weights, horizons)
        )
        daily_vol=close.pct_change().rolling(config.vol_window,
            min_periods=config.vol_window).std().clip(lower=0.001)
        result = dist / (daily_vol * np.sqrt(21.0))
    result.iloc[:config.warmup - 1] = np.nan
    return result.replace([np.inf, -np.inf], np.nan)


def _risk_fraction(vix_level: float, config: BacktestConfig) -> float:
    if vix_level > config.vix_extreme:
        return 0.0
    if vix_level > config.vix_high:
        return min(0.5,config.max_gross_exposure)
    return config.max_gross_exposure


def _target(signal_row: pd.Series, vix: float, cfg: BacktestConfig) -> dict[str, float]:
    """Long the highest-scoring and short the lowest-scoring distinct sector.

    Even when both scores share a sign, this is a relative-strength pair.
    The fixed threshold applies to the best-minus-worst score spread.
    """
    risk_fraction = _risk_fraction(vix, cfg)
    if risk_fraction <= 0:
        return {}
    candidate = signal_row.replace([np.inf,-np.inf],np.nan).dropna()
    if not cfg.allow_short:
        # Explicit long-only ablation, NOT the main strategy.
        if candidate.empty:
            return {}
        winner=candidate.idxmax()
        return {str(winner):risk_fraction} if float(candidate[winner])>cfg.signal_threshold else {}
    if len(candidate)<2:
        return {}
    strongest=candidate.idxmax()
    weakest=candidate.idxmin()
    if strongest==weakest or float(candidate[strongest]-candidate[weakest])<=cfg.signal_threshold:
        return {}
    return {str(strongest):risk_fraction/2, str(weakest):-risk_fraction/2}


def backtest_strategy(
    data: pd.DataFrame,
    signals: pd.DataFrame | None = None,
    config: BacktestConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Simulate signed integer share transfers and audited daily closing equity.

    The NAV at a close is computed with signed positions carried into the session.
    Pending instructions from the *prior* close execute at this close and incur
    a fee on all bought AND sold notional. New signals are queued afterward.
    """
    cfg = config or BacktestConfig()
    assets = _validate_prices(data)
    if signals is None:
        signals=calculate_signals(data,cfg)
    if not signals.index.equals(data.index):
        raise ValueError("Signals dates must exactly equal price dates")
    if any(s not in assets for s in signals.columns):
        raise ValueError("Signals must contain only tradable sector ETFs")
    if not set(assets).issubset(signals.columns):
        raise ValueError("Signals are missing tradable sector ETFs")

    dates=data.index
    if len(dates)<cfg.warmup+2:
        raise ValueError("Not enough daily data beyond signal warmup")
    price=data[assets].to_numpy(dtype=float)
    vix=data["VIX"].to_numpy(dtype=float)
    scores=signals[assets]
    positions=np.zeros(len(assets),dtype=np.int64)
    peak_by_asset: dict[str,float]={}
    cash=float(cfg.initial_capital)
    prior_nav=float(cfg.initial_capital)
    peak_nav=float(cfg.initial_capital)
    pending=None  # {weights, signal_date, reason}, strictly one-bar delayed
    halt_until=-1
    last_regime=None
    ledger=[]
    rows=[]
    holdings=[]
    friction=(cfg.transaction_cost_bps+cfg.slippage_bps)/10_000
    borrow_rate=cfg.annual_borrow_cost_bps/10_000/252

    for i, day in enumerate(dates):
        px=price[i]
        pre_nav=float(cash+np.dot(positions,px))
        if pre_nav<=0 or not np.isfinite(pre_nav):
            raise AssertionError("Portfolio equity exhausted; cannot continue short replay")
        prior_short_notional=float(np.dot(np.maximum(-positions,0),px))
        borrow_fee=prior_short_notional*borrow_rate
        cash-=borrow_fee
        daily_notional=0.0
        daily_cost=0.0

        if pending is not None:
            desired=pending["weights"]
            if sum(abs(float(w)) for w in desired.values())>cfg.max_gross_exposure+1e-10:
                raise AssertionError("Gross target exposure exceeds entry limit")
            if len(desired)>2:
                raise AssertionError("Only the strongest/weakest pair is supported")
            if len(desired)==2:
                weights=list(desired.values())
                if min(weights)>=0 or max(weights)<=0 or abs(sum(weights))>1e-10:
                    raise AssertionError("Pair targets must be dollar-neutral at signal")
            elif len(desired)==1 and cfg.allow_short:
                raise AssertionError("Paired strategy cannot enter a naked leg")
            if cfg.execution_mode=="incremental":
                # Existing shares are retained. Only signed share differences
                # are executed, so an unchanged pair incurs no round trip.
                # Current t+1 marked equity sizes the t+1 order, *not* its
                # signal: asset selection and intended fractions come from t.
                budget=pre_nav-borrow_fee
                old_signs=np.sign(positions.copy())
                target=np.zeros(len(assets),dtype=np.int64)
                for j,ticker in enumerate(assets):
                    frac=float(desired.get(ticker,0.0))
                    if frac<0 and not cfg.allow_short:
                        raise AssertionError("Cannot short in long-only control")
                    reserve=cfg.short_execution_buffer if (
                        len(desired)==2 or frac<0) else 0.0
                    target[j]=int(np.sign(frac))*floor(
                        max(0.0,budget*abs(frac)*(1-reserve))/
                        (float(px[j])*(1+friction))
                    )
                if len(desired)==2 and ((target>0).sum()!=1 or (target<0).sum()!=1):
                    # The strategy cannot hold only one affordable pair leg.
                    target[:]=0
                # If both legs are the same as yesterday, no trades occur.
                deltas=target-positions
                # Sell and short proceeds first, buy and cover second.
                # Short proceeds remain restricted by collateral checks.
                order=sorted(range(len(assets)),key=lambda j:int(deltas[j]))
                for j in order:
                    change=int(deltas[j])
                    if change==0:
                        continue
                    old=int(positions[j])
                    fills=[change]
                    if old and target[j] and (old>0)!=(target[j]>0):
                        fills=[-old,int(target[j])]
                    held=old
                    for filled in fills:
                        traded_value=filled*float(px[j])
                        fee=abs(traded_value)*friction
                        cash-=traded_value+fee
                        daily_notional+=abs(traded_value)
                        daily_cost+=fee
                        if filled>0:
                            side="BUY_TO_COVER" if held<0 else "BUY"
                        else:
                            side="SELL" if held>0 else "SHORT_SELL"
                        ledger.append({"signal_date":pending["signal_date"],
                            "execution_date":day,"ticker":assets[j],
                            "shares":filled,"price":float(px[j]),
                            "notional":traded_value,"fee":fee,
                            "side":side,"reason":pending["reason"]})
                        held+=filled
                    positions[j]=target[j]
                # Preserve trailing anchors for held legs; reset on new legs.
                peak_by_asset={
                    ticker:(peak_by_asset[ticker] if ticker in peak_by_asset
                        and int(np.sign(positions[j]))==int(old_signs[j])
                        else float(px[j]))
                    for j,ticker in enumerate(assets) if positions[j]!=0
                }
            else:
                # Legacy full-liquidation path retained for apples-to-apples
                # baseline audits and backward-compatible existing tests.
                for j,ticker in enumerate(assets):
                    old=int(positions[j])
                    if old:
                        notional=old*float(px[j])
                        fee=abs(notional)*friction
                        cash+=notional-fee
                        daily_notional+=abs(notional)
                        daily_cost+=fee
                        ledger.append({"signal_date":pending["signal_date"],
                            "execution_date":day,"ticker":ticker,"shares":-old,
                            "price":float(px[j]),"notional":-notional,"fee":fee,
                            "side":"BUY_TO_COVER" if old<0 else "SELL",
                            "reason":pending["reason"]})
                        positions[j]=0
                available=float(cash)
                for j,ticker in enumerate(assets):
                    frac=float(desired.get(ticker,0.0))
                    if frac == 0:
                        continue
                    if frac<0 and not cfg.allow_short:
                        raise AssertionError("Short requested in long-only mode")
                    reserve=cfg.short_execution_buffer if len(desired)==2 else (
                        cfg.short_execution_buffer if frac<0 else 0.0
                    )
                    effective_fraction=abs(frac)*(1-reserve)
                    size=floor(max(0,available*effective_fraction)/(float(px[j])*(1+friction)))
                    if size:
                        signed_qty=int(np.sign(frac)*size)
                        notional=signed_qty*float(px[j])
                        fee=abs(notional)*friction
                        cash-=notional+fee
                        daily_notional+=abs(notional)
                        daily_cost+=fee
                        ledger.append({"signal_date":pending["signal_date"],
                            "execution_date":day,"ticker":ticker,"shares":signed_qty,
                            "price":float(px[j]),"notional":notional,"fee":fee,
                            "side":"SHORT_SELL" if signed_qty<0 else "BUY",
                            "reason":pending["reason"]})
                        positions[j]=signed_qty
                peak_by_asset={ticker:float(px[j]) for j,ticker in enumerate(assets)
                    if positions[j]!=0}
            pending=None

        nav=float(cash+np.dot(positions,px))
        long_value=float(np.dot(np.maximum(positions,0),px))
        short_value=float(np.dot(np.maximum(-positions,0),px))
        exposure=(long_value+short_value)/nav
        net_exposure=(long_value-short_value)/nav
        collateral=short_value*(1+cfg.initial_short_margin)
        available_cash=cash-collateral
        if cash<-1e-6:
            raise AssertionError("Unfunded margin loan, not simulated by this engine")
        if daily_notional>0 and short_value>0 and available_cash<-1e-5:
            raise AssertionError("New short violates 50% initial margin collateral")
        if abs(pre_nav-nav-daily_cost-borrow_fee)>max(0.00001,1e-9*pre_nav):
            raise AssertionError("Trade ledger fails NAV conservation")
        value_return=nav/prior_nav-1
        prior_nav=nav

        rows.append({
            "value":nav,"return":value_return,"cash":cash,
            "available_cash":available_cash,"restricted_collateral":collateral,
            "long_exposure":long_value/nav,"short_exposure":short_value/nav,
            "net_exposure":net_exposure,
            "gross_exposure":exposure,"turnover":daily_notional/(2*pre_nav),
            "transaction_cost":daily_cost,"borrow_cost":borrow_fee,
            "margin_breach":False,"gross_limit_breach":False,"cumulative_fees":0.0,
        })
        holdings.append(positions.copy())

        if i<cfg.warmup-1:
            peak_nav=max(peak_nav,nav)
            continue

        # All stops are evaluated using t-close information; fill at t+1 close.
        peak_nav=max(peak_nav,nav)
        drawdown=1-nav/peak_nav
        touched=None
        for j,ticker in enumerate(assets):
            if positions[j]>0:
                peak_by_asset[ticker]=max(peak_by_asset.get(ticker,float(px[j])),float(px[j]))
                if float(px[j]) < peak_by_asset[ticker]*(1-cfg.trailing_stop):
                    touched=ticker
            elif positions[j]<0:
                peak_by_asset[ticker]=min(peak_by_asset.get(ticker,float(px[j])),float(px[j]))
                if float(px[j]) > peak_by_asset[ticker]*(1+cfg.trailing_stop):
                    touched=ticker
        # Overnight price gaps can violate gross or maintenance margins.
        # Queue next-close cover, never pretend to liquidate at trigger close.
        maintenance_breach=(
            short_value>0 and nav<short_value*cfg.maintenance_short_margin
        )
        gross_limit_breach=exposure>cfg.max_gross_exposure*(
            1+cfg.gross_drift_band if cfg.gross_risk_response=="trim"
            else 1.0
        )+1e-7
        if maintenance_breach or gross_limit_breach:
            rows[-1]["margin_breach"]=maintenance_breach
            rows[-1]["gross_limit_breach"]=gross_limit_breach
            if maintenance_breach or cfg.gross_risk_response=="exit":
                pending={"weights":{},"signal_date":day,
                         "reason":"maintenance_margin_call" if maintenance_breach else "gross_limit_exit"}
                halt_until=max(halt_until,i+cfg.cooldown_bars)
            else:
                # Keep sector selection unchanged and trim both legs
                # toward the equal-notional gross budget next close.
                current_long=next((assets[j] for j in range(len(assets))
                    if positions[j]>0),None)
                current_short=next((assets[j] for j in range(len(assets))
                    if positions[j]<0),None)
                fraction=min(_risk_fraction(float(vix[i]),cfg),
                             cfg.max_gross_exposure)/2
                desired=({current_long:fraction,current_short:-fraction}
                    if current_long and current_short else {})
                pending={"weights":desired,"signal_date":day,
                         "reason":"gross_drift_trim"}
            continue
        if i<halt_until:
            if np.any(positions):
                pending={"weights":{},"signal_date":day,"reason":"cooldown_liquidation"}
            continue

        if drawdown>=cfg.drawdown_stop:
            pending={"weights":{},"signal_date":day,"reason":"portfolio_drawdown_stop"}
            halt_until=i+cfg.cooldown_bars
            peak_nav=nav  # reset reference for the next permitted investment cycle
            continue

        if touched is not None:
            pending={"weights":{},"signal_date":day,"reason":"trailing_stop"}
            halt_until=i+cfg.cooldown_bars
            continue

        current_regime=_risk_fraction(float(vix[i]),cfg)
        regular=((i-cfg.warmup+1)%cfg.rebalance_every==0)
        changed=last_regime is not None and current_regime!=last_regime
        if regular or changed:
            planned=_target(scores.iloc[i],float(vix[i]),cfg)
            current_assets={ticker:int(np.sign(positions[j]))
                for j,ticker in enumerate(assets) if positions[j]!=0}
            new_assets={ticker:int(np.sign(w)) for ticker,w in planned.items()}
            # Skip redundant identical allocation if weights still close to desired;
            # don't incur fees or reset high-water just because a date has passed.
            desired_long=sum(max(w,0.0) for w in planned.values())
            desired_short=sum(max(-w,0.0) for w in planned.values())
            current_long=long_value/nav
            current_short=short_value/nav
            if (new_assets!=current_assets or
                abs(desired_long-current_long)>.05 or
                abs(desired_short-current_short)>.05):
                pending={"weights":planned,"signal_date":day,
                    "reason":"risk_regime" if changed else "scheduled_rotation"}
        last_regime=current_regime

    portfolio=pd.DataFrame(rows,index=dates)
    portfolio["cumulative_fees"]=(portfolio["transaction_cost"]+portfolio["borrow_cost"]).cumsum()
    shares=pd.DataFrame(holdings,index=dates,columns=assets,dtype=np.int64)
    ledger_frame=pd.DataFrame(ledger,columns=[
        "signal_date","execution_date","ticker","shares","price","notional","fee","side","reason"
    ])
    portfolio.attrs["trades"]=ledger_frame
    portfolio.attrs["assumptions"]={
        "execution":"signal at t close, filled at t+1 close",
        "schedule":f"every {cfg.rebalance_every} bars plus risk overrides",
        "transaction_cost_bps":cfg.transaction_cost_bps,
        "slippage_bps":cfg.slippage_bps,
        "allow_short":cfg.allow_short,
        "strategy":"simultaneous strongest long / weakest short; equal target notionals",
        "pair_selection":"max and min cross-sectional scores, with spread threshold",
        "pair_neutrality":"target zero net, realized net drifts with prices and share rounding",
        "max_gross_exposure_at_entry":cfg.max_gross_exposure,
        "short_initial_margin":cfg.initial_short_margin,
        "short_maintenance_margin":cfg.maintenance_short_margin,
        "annual_borrow_cost_bps":cfg.annual_borrow_cost_bps,
        "short_execution_buffer":cfg.short_execution_buffer,
        "execution_mode":cfg.execution_mode,
        "gross_risk_response":cfg.gross_risk_response,
        "gross_drift_band":cfg.gross_drift_band,
        "short_proceeds":"restricted collateral, not free investment cash",
        "borrow_availability":"assumed, not historically verified",
        "ETF_dividends":"adjusted closing-price approximation",
        "cash_interest":"zero",
        "VIX":"risk feature only, never traded",
        "stops":"close-triggered, executed at next close; no intraday stop guarantee",
        "signals":"MA energy normalized by trailing daily volatility" if
                  cfg.signal_method=="ma_energy" else "trailing simple momentum",
    }
    return portfolio,shares
