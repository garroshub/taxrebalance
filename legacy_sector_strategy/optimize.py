import numpy as np
import pandas as pd
from skopt import gp_minimize
from skopt.space import Real, Integer
import model
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def objective(params):
    """
    Optimization objective function
    
    Args:
        params: Parameter list [base_threshold, vol_window, ma_window_1, ma_window_2, ma_window_3,
                        trailing_stop, max_drawdown_stop, vix_high, vix_extreme]
    Returns:
        -avg_sharpe: Negative average Sharpe ratio (because we want to maximize Sharpe ratio, but the optimizer minimizes the objective)
    """
    # Unpack parameters
    base_threshold, vol_window, ma_window_1, ma_window_2, ma_window_3, \
    trailing_stop, max_drawdown_stop, vix_high, vix_extreme = params
    
    # Ensure MA windows are in ascending order
    ma_windows = sorted([int(ma_window_1), int(ma_window_2), int(ma_window_3)])
    
    # Update model parameters
    model.BASE_THRESHOLD = base_threshold
    model.VOL_WINDOW = int(vol_window)
    model.MA_WINDOWS = ma_windows
    model.TRAILING_STOP = trailing_stop
    model.MAX_DRAWDOWN_STOP = max_drawdown_stop
    model.VIX_HIGH_THRESHOLD = vix_high
    model.VIX_EXTREME_THRESHOLD = vix_extreme
    
    try:
        # Get data
        data = model.download_data(start_date='2010-01-01')  # Use a shorter time period to speed up optimization
        if data is None or len(data) < 252:
            return 0
            
        # Run backtest
        results = model.rolling_backtest(data)
        if results.empty:
            return 0
            
        # Calculate average Sharpe ratio
        avg_sharpe = results['Strategy Sharpe'].mean()
        
        # If Sharpe ratio is invalid, return a very bad value
        if np.isnan(avg_sharpe) or np.isinf(avg_sharpe):
            return 0
            
        return -avg_sharpe  # Return negative value because we want to minimize the objective function
        
    except Exception as e:
        print(f"Error in optimization: {str(e)}")
        return 0

def optimize_parameters():
    """Run parameter optimization"""
    
    # Define parameter space
    space = [
        Real(0.1, 0.3, name='base_threshold'),           # BASE_THRESHOLD
        Integer(10, 30, name='vol_window'),              # VOL_WINDOW
        Integer(10, 30, name='ma_window_1'),             # MA_WINDOWS[0]
        Integer(40, 80, name='ma_window_2'),             # MA_WINDOWS[1]
        Integer(100, 140, name='ma_window_3'),           # MA_WINDOWS[2]
        Real(0.05, 0.15, name='trailing_stop'),          # TRAILING_STOP
        Real(0.10, 0.20, name='max_drawdown_stop'),      # MAX_DRAWDOWN_STOP
        Real(25, 40, name='vix_high'),                   # VIX_HIGH_THRESHOLD
        Real(35, 50, name='vix_extreme')                 # VIX_EXTREME_THRESHOLD
    ]
    
    # Run Bayesian optimization
    print("Starting parameter optimization...")
    result = gp_minimize(
        objective,
        space,
        n_calls=50,        # Total number of evaluations
        n_random_starts=10, # Number of random explorations
        noise=0.1,         # Assume the objective function has some noise
        verbose=True
    )
    
    # Extract optimal parameters
    best_params = result.x
    best_score = -result.fun  # Convert back to positive Sharpe ratio
    
    # Print results
    print("\nOptimization completed!")
    print(f"Best average Sharpe ratio: {best_score:.4f}")
    print("\nOptimal parameters:")
    print(f"BASE_THRESHOLD = {best_params[0]:.3f}")
    print(f"VOL_WINDOW = {int(best_params[1])}")
    print(f"MA_WINDOWS = [{int(best_params[2])}, {int(best_params[3])}, {int(best_params[4])}]")
    print(f"TRAILING_STOP = {best_params[5]:.3f}")
    print(f"MAX_DRAWDOWN_STOP = {best_params[6]:.3f}")
    print(f"VIX_HIGH_THRESHOLD = {best_params[7]:.1f}")
    print(f"VIX_EXTREME_THRESHOLD = {best_params[8]:.1f}")
    
    return best_params, best_score

if __name__ == "__main__":
    optimize_parameters()
