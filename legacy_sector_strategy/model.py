import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import time

# ----------------- Strategy Parameters -----------------
START_DATE = '2000-01-01'  # Backtest start date
WINDOW = 120  # Window for calculating moving average energy
INITIAL_CAPITAL = 100000.0  # Initial capital for backtesting
MIN_HISTORY = WINDOW  # Minimum history required for signal generation

# ----------------- Signal Generation Parameters -----------------
BASE_THRESHOLD = 0.1  # Base threshold for signal strength
VOL_WINDOW = 30  # Window for volatility calculation
MA_WINDOWS = [10, 40, 140]  # Moving average windows for trend analysis

# ----------------- Stop Loss Parameters -----------------
TRAILING_STOP = 0.05  # Trailing stop loss percentage
MAX_DRAWDOWN_STOP = 0.20  # Maximum drawdown stop loss percentage
VIX_HIGH_THRESHOLD = 25  # VIX high threshold
VIX_EXTREME_THRESHOLD = 50  # VIX extreme threshold
TRANSACTION_COST_BPS = 10.0
SLIPPAGE_BPS = 0.0
REBALANCE_EVERY = 21
COOLDOWN_BARS = 21
SIGNAL_METHOD = "ma_energy"
ALLOW_SHORT = True
MAX_GROSS_EXPOSURE = 1.0
ANNUAL_BORROW_COST_BPS = 200.0
INITIAL_SHORT_MARGIN = 0.50
MAINTENANCE_SHORT_MARGIN = 0.30
EXECUTION_MODE = "incremental"  # Signed share differences; no redundant roundtrip
GROSS_RISK_RESPONSE = "trim"  # Above drift band, resize two legs at next close
GROSS_DRIFT_BAND = 0.10  # Research assumption: 10% post-entry price drift tolerance


def download_data(start_date, end_date=None):
    """
    Download corporate-action-adjusted ETF closing prices and VIX.
    end_date is exclusive (Yahoo convention), or omit it for latest close.
    
    Args:
        start_date: Start date for data download
    
    Returns:
        DataFrame with adjusted close prices for ETFs and VIX
    """
    # List of ETFs to trade
    etfs = ['SPY', 'XLK', 'XLV', 'XLE', 'XLF', 'XLI', 'XLY']
    
    # Download data for ETFs
    data = pd.DataFrame()
    download_failed = False
    
    for etf in etfs:
        try:
            print(f"Downloading data for {etf}...")
            ticker = yf.Ticker(etf)
            hist = ticker.history(start=start_date, end=end_date or datetime.now().strftime('%Y-%m-%d'), auto_adjust=True)['Close']
            if len(hist) == 0:
                print(f"Warning: No data available for {etf}")
                download_failed = True
                break
            else:
                print(f"Downloaded {len(hist)} data points for {etf}")
                # Convert index to date only (remove time and timezone info)
                hist.index = hist.index.date
                data[etf] = hist
        except Exception as e:
            print(f"Error downloading {etf}: {str(e)}")
            download_failed = True
            break
    
    if download_failed:
        print("Failed to download complete ETF data")
        return None
        
    # Download VIX data
    try:
        print("Downloading VIX data...")
        vix = yf.Ticker('^VIX')
        vix_hist = vix.history(start=start_date, end=end_date or datetime.now().strftime('%Y-%m-%d'), auto_adjust=True)['Close']
        if len(vix_hist) == 0:
            print("Warning: No VIX data available")
            return None
        else:
            print(f"Downloaded {len(vix_hist)} data points for VIX")
            # Convert index to date only (remove time and timezone info)
            vix_hist.index = vix_hist.index.date
            data['VIX'] = vix_hist
    except Exception as e:
        print(f"Error downloading VIX: {str(e)}")
        return None
    
    # Check for missing values before cleaning
    print("\nMissing values before cleaning:")
    print(data.isnull().sum())
    
    # Drop any rows with missing data
    data_cleaned = data.dropna()
    
    # Check for missing values after cleaning
    print("\nMissing values after cleaning:")
    print(data_cleaned.isnull().sum())
    
    if len(data_cleaned) == 0:
        print("No valid data after cleaning")
        # Try to identify why we lost all data
        print("\nSample of raw data:")
        print(data.head())
        print("\nDates with missing values:")
        print(data[data.isnull().any(axis=1)].head())
        return None
        
    print(f"\nFinal dataset shape after cleaning: {data_cleaned.shape}")
    print(f"Date range: {data_cleaned.index[0]} to {data_cleaned.index[-1]}")
    
    return data_cleaned

def ma_energy(prices, window):
    """
    Calculate moving average energy indicator
    
    Args:
        prices: Price series
        window: Rolling window size
    
    Returns:
        Series of MA energy values
    """
    ma = prices.rolling(window=window).mean()
    energy = (prices - ma) / ma
    return energy

# Audited event-time trading engine, preserving the public UI/test signatures.
from strategy_backtest import BacktestConfig, calculate_signals, backtest_strategy
from strategy_backtest import _target as _deterministic_target


def _strategy_config(**overrides):
    values = dict(
        initial_capital=INITIAL_CAPITAL,
        ma_windows=tuple(MA_WINDOWS),
        vol_window=VOL_WINDOW,
        min_history=max(MIN_HISTORY, max(MA_WINDOWS)),
        signal_threshold=BASE_THRESHOLD,
        vix_high=VIX_HIGH_THRESHOLD,
        vix_extreme=VIX_EXTREME_THRESHOLD,
        trailing_stop=TRAILING_STOP,
        drawdown_stop=MAX_DRAWDOWN_STOP,
        transaction_cost_bps=TRANSACTION_COST_BPS,
        slippage_bps=SLIPPAGE_BPS,
        rebalance_every=REBALANCE_EVERY,
        cooldown_bars=COOLDOWN_BARS,
        signal_method=SIGNAL_METHOD,
        allow_short=ALLOW_SHORT,
        max_gross_exposure=MAX_GROSS_EXPOSURE,
        annual_borrow_cost_bps=ANNUAL_BORROW_COST_BPS,
        initial_short_margin=INITIAL_SHORT_MARGIN,
        maintenance_short_margin=MAINTENANCE_SHORT_MARGIN,
        execution_mode=EXECUTION_MODE,
        gross_risk_response=GROSS_RISK_RESPONSE,
        gross_drift_band=GROSS_DRIFT_BAND,
    )
    values.update(overrides)
    return BacktestConfig(**values)


def generate_signals(data):
    """Causal multi-horizon MA Energy scores for ETF sectors only."""
    return calculate_signals(data, _strategy_config())


def get_target_weights(signals, current_date, current_positions, data, entry_prices):
    """Legacy informational target; execution/stops are inside backtest()."""
    return _deterministic_target(
        signals.loc[current_date], float(data.loc[current_date, "VIX"]),
        _strategy_config(),
    )


def backtest(data, signals=None, **settings):
    """Trade after signal; portfolio attrs['trades'] contains the audit ledger."""
    return backtest_strategy(data, signals, _strategy_config(**settings))


def rolling_backtest(data, window_years=5, **settings):
    """Nonoverlapping descriptive windows, not untouched out-of-sample tests.

    Signal warmup and initial capital restart in each window; benchmark uses
    corresponding SPY adjusted-close series before SPY fees.
    """
    if window_years <= 0:
        raise ValueError("window_years must be positive")
    window_days = int(window_years * 252)
    records = []
    for start in range(0, len(data) - window_days + 1, window_days):
        window = data.iloc[start:start + window_days]
        nav, positions = backtest(window, **settings)
        spy_returns = window["SPY"].pct_change().fillna(0)
        records.append({
            "Start Date": window.index[0],
            "End Date": window.index[-1],
            "Window Days": len(window),
            "Strategy Return": calculate_annual_return(nav["value"]),
            "Strategy Volatility": calculate_annual_volatility(nav["return"]),
            "Strategy Sharpe": calculate_sharpe_ratio(nav["return"]),
            "Strategy Max Drawdown": calculate_max_drawdown(nav["value"]),
            "SPY Return": calculate_annual_return(window["SPY"]),
            "SPY Volatility": calculate_annual_volatility(spy_returns),
            "SPY Sharpe": calculate_sharpe_ratio(spy_returns),
            "SPY Volatility": calculate_annual_volatility(spy_returns),
            "SPY Max Drawdown": calculate_max_drawdown(window["SPY"]),
            "Average Turnover": float(nav["turnover"].sum() * 252 / len(window)),
            "Total Trading Cost": float(nav["transaction_cost"].sum()),
            "Total Borrow Cost": float(nav["borrow_cost"].sum()),
            "Trade Count": len(nav.attrs["trades"]),
            "Max Gross Exposure": float(nav["gross_exposure"].max()),
            "Short Exposure Days": int((nav["short_exposure"] > 0).sum()),
            "Margin Breach Days": int(nav["margin_breach"].sum()),
            "Gross Limit Breach Days": int(nav["gross_limit_breach"].sum()),
            "Negative Available Cash Days": int((nav["available_cash"] < -1e-6).sum()),
            "Negative Cash Days": int((nav["cash"] < -1e-7).sum()),
        })
    return pd.DataFrame(records)


def calculate_annual_volatility(returns):
    """Calculate annualized volatility"""
    return returns.std() * np.sqrt(252)

def calculate_annual_return(portfolio_values):
    """
    Calculate annualized return from a series of portfolio values
    
    Args:
        portfolio_values: Series of portfolio values
        
    Returns:
        Annualized return as a decimal (not percentage)
    """
    if len(portfolio_values) < 2:
        return 0.0
        
    start_value = portfolio_values.iloc[0]
    end_value = portfolio_values.iloc[-1]
    years = len(portfolio_values) / 252  # Assuming 252 trading days per year
    
    total_return = (end_value / start_value) - 1
    annual_return = (1 + total_return) ** (1 / years) - 1
    
    return annual_return  # Return as decimal, not percentage

def calculate_average_turnover(portfolio_values):
    """Annualized half-gross-notional turnover, computed from actual trades."""
    if not isinstance(portfolio_values, pd.DataFrame) or "turnover" not in portfolio_values:
        raise ValueError("Turnover needs the full portfolio with a turnover column")
    return float(portfolio_values["turnover"].sum() * 252 / len(portfolio_values))

def calculate_sharpe_ratio(returns):
    """
    Calculate annualized Sharpe ratio
    
    Args:
        returns: Series of daily returns
        
    Returns:
        Annualized Sharpe ratio
    """
    # Annualize returns and volatility
    annual_return = returns.mean() * 252
    annual_vol = returns.std() * np.sqrt(252)
    risk_free_rate = 0.02  # Assuming 2% annual risk-free rate
    
    if annual_vol == 0:
        return 0.0
        
    return (annual_return - risk_free_rate) / annual_vol

def calculate_max_drawdown(values):
    """
    Calculate maximum drawdown using rolling maximum
    
    Args:
        values: Series of values
        
    Returns:
        Maximum drawdown as a decimal (not percentage)
    """
    rolling_max = values.expanding().max()
    drawdowns = (values - rolling_max) / rolling_max
    return abs(drawdowns.min())

def plot_rolling_metrics(results):
    """
    Plot rolling window performance metrics
    
    Args:
        results: DataFrame with rolling window results
    """
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Plot Returns
    axes[0, 0].plot(results['End Date'], results['Strategy Return'], 
                    label='Strategy', marker='o')
    axes[0, 0].plot(results['End Date'], results['SPY Return'], 
                    label='SPY', marker='o')
    axes[0, 0].set_title('Annual Returns')
    axes[0, 0].legend()
    
    # Plot Sharpe Ratios
    axes[0, 1].plot(results['End Date'], results['Strategy Sharpe'], 
                    label='Strategy', marker='o')
    axes[0, 1].plot(results['End Date'], results['SPY Sharpe'], 
                    label='SPY', marker='o')
    axes[0, 1].set_title('Sharpe Ratios')
    axes[0, 1].legend()
    
    # Plot Maximum Drawdowns
    axes[1, 0].plot(results['End Date'], results['Strategy Max Drawdown'], 
                    label='Strategy', marker='o')
    axes[1, 0].plot(results['End Date'], results['SPY Max Drawdown'], 
                    label='SPY', marker='o')
    axes[1, 0].set_title('Maximum Drawdowns')
    axes[1, 0].legend()
    
    # Plot Average Turnover
    axes[1, 1].plot(results['End Date'], results['Average Turnover'], 
                    label='Strategy', marker='o')
    axes[1, 1].set_title('Average Turnover')
    axes[1, 1].legend()
    
    plt.tight_layout()
    plt.savefig('rolling_metrics.png', bbox_inches='tight')
    plt.close()

if __name__ == "__main__":
    # Download data
    data = download_data(start_date=START_DATE)
    
    # Execute rolling window backtest
    print("\n=== Rolling Window Backtest (5-Year Windows) ===")
    rolling_results = rolling_backtest(data)
    
    # Print detailed statistics for each window
    pd.set_option('display.float_format', '{:.2%}'.format)
    print("\nDetailed Statistics for Each Window:")
    print(rolling_results.to_string(index=False))
    
    # Plot metrics
    plot_rolling_metrics(rolling_results)
    print("\nPlot saved as 'rolling_metrics.png'")