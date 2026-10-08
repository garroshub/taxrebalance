import re

import pandas as pd

import strategy_analysis_agent as agent


def test_no_hardcoded_google_api_key():
    source = open("strategy_analysis_agent.py", encoding="utf-8").read()

    assert not re.search(r"AIza[0-9A-Za-z_-]{35}", source)


def test_analysis_is_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    window_data = {
        "Start Date": pd.Timestamp("2024-01-01"),
        "End Date": pd.Timestamp("2024-01-31"),
        "SPY Return": 0.01,
        "SPY Volatility": 0.10,
        "SPY Sharpe": 1.0,
        "SPY Max Drawdown": -0.02,
        "Strategy Return": 0.02,
        "Strategy Volatility": 0.12,
        "Strategy Sharpe": 1.2,
        "Strategy Max Drawdown": -0.03,
        "Average Turnover": 0.05,
    }
    vix_data = pd.Series([13.0, 15.0, 17.0])

    result = agent.analyze_trading_window(window_data, vix_data)

    assert "AI strategy review is disabled" in result
