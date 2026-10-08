import unittest
import model
import pandas as pd
from datetime import datetime, timedelta

class TestModel(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.start_date = '2000-01-01'
        
    def test_data_download(self):
        """Test if we can successfully download and process data"""
        print("\nTesting data download...")
        data = model.download_data(self.start_date)
        
        # Check if data is not None
        self.assertIsNotNone(data, "Data should not be None")
        
        # Check if data is not empty
        self.assertFalse(data.empty, "Data should not be empty")
        
        # Check if we have all required columns
        required_columns = ['SPY', 'XLK', 'XLV', 'XLE', 'XLF', 'XLI', 'XLY', 'VIX']
        for col in required_columns:
            self.assertIn(col, data.columns, f"Missing required column: {col}")
        
        # Print data info
        print(f"Data shape: {data.shape}")
        print(f"Date range: {data.index[0]} to {data.index[-1]}")
        print(f"Number of trading days: {len(data)}")
        
        return data
    
    def test_signal_generation(self):
        """Test if we can generate signals correctly"""
        print("\nTesting signal generation...")
        data = self.test_data_download()
        
        signals = model.generate_signals(data)
        
        # Check if signals DataFrame is not empty
        self.assertFalse(signals.empty, "Signals should not be empty")
        
        # Check if signals have same index as data
        self.assertTrue(signals.index.equals(data.index), "Signals index should match data index")
        
        # Print signals info
        print(f"Signals shape: {signals.shape}")
        print("Signal columns:", signals.columns.tolist())
        
        return signals
    
    def test_backtest(self):
        """Test if we can run backtest successfully"""
        print("\nTesting backtest...")
        data = self.test_data_download()
        signals = self.test_signal_generation()
        
        portfolio, positions = model.backtest(data, signals)
        
        # Check if portfolio DataFrame is not empty
        self.assertFalse(portfolio.empty, "Portfolio should not be empty")
        
        # Check if we have required columns in portfolio
        required_columns = ['value', 'return']
        for col in required_columns:
            self.assertIn(col, portfolio.columns, f"Missing required column in portfolio: {col}")
        
        # Print portfolio info
        print(f"Portfolio shape: {portfolio.shape}")
        print(f"Final portfolio value: {portfolio['value'].iloc[-1]:.2f}")
        print(f"Total return: {(portfolio['value'].iloc[-1] / model.INITIAL_CAPITAL - 1):.2%}")
        
        return portfolio, positions
    
    def test_rolling_backtest(self):
        """Test if we can run rolling window backtest successfully"""
        print("\nTesting rolling window backtest...")
        data = self.test_data_download()
        
        results = model.rolling_backtest(data)
        
        # Check if results DataFrame is not empty
        self.assertFalse(results.empty, "Results should not be empty")
        
        # Check if we have required columns
        required_columns = [
            'Start Date', 'End Date', 'Window Days',
            'Strategy Return', 'Strategy Volatility', 'Strategy Sharpe',
            'Strategy Max Drawdown', 'SPY Return', 'SPY Volatility',
            'SPY Sharpe', 'SPY Max Drawdown', 'Average Turnover'
        ]
        for col in required_columns:
            self.assertIn(col, results.columns, f"Missing required column in results: {col}")
        
        # Print results info
        print(f"Results shape: {results.shape}")
        print("\nLatest window results:")
        latest = results.iloc[-1]
        print(f"Strategy Return: {latest['Strategy Return']:.2%}")
        print(f"Strategy Sharpe: {latest['Strategy Sharpe']:.2f}")
        print(f"Strategy Max Drawdown: {latest['Strategy Max Drawdown']:.2%}")
        print(f"SPY Return: {latest['SPY Return']:.2%}")
        
        return results

if __name__ == '__main__':
    unittest.main(argv=[''], verbosity=2)
