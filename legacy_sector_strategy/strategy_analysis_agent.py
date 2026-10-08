import os
import google.generativeai as genai
from datetime import datetime
import pandas as pd

def _get_google_api_key():
    """Return the configured Gemini API key, if one is available."""
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# Set up the model
generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

def _build_model():
    api_key = _get_google_api_key()
    if not api_key:
        return None

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name="gemini-pro",
        generation_config=generation_config,
        safety_settings=safety_settings
    )

def analyze_trading_window(window_data, vix_data):
    """
    Analyze trading strategy performance and market conditions for a specific time window.
    
    Args:
        window_data (dict): Dictionary containing window performance metrics
        vix_data (pd.Series): VIX data for the window period
    
    Returns:
        str: Structured analysis of strategy performance and market conditions
    """
    model = _build_model()
    if model is None:
        return (
            "AI strategy review is disabled because no Gemini API key is configured. "
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in the runtime environment to enable this feature."
        )
    
    # Format the analysis prompt
    prompt = f"""
    Analyze the trading strategy performance for the period {window_data['Start Date']} to {window_data['End Date']}.
    
    Market Data:
    - SPY Return: {window_data['SPY Return']:.2%}
    - SPY Volatility: {window_data['SPY Volatility']:.2%}
    - SPY Sharpe: {window_data['SPY Sharpe']:.2f}
    - SPY Max Drawdown: {window_data['SPY Max Drawdown']:.2%}
    - Average VIX: {vix_data.mean():.2f}
    - Max VIX: {vix_data.max():.2f}
    - Min VIX: {vix_data.min():.2f}
    
    Strategy Performance:
    - Strategy Return: {window_data['Strategy Return']:.2%}
    - Strategy Volatility: {window_data['Strategy Volatility']:.2%}
    - Strategy Sharpe: {window_data['Strategy Sharpe']:.2f}
    - Strategy Max Drawdown: {window_data['Strategy Max Drawdown']:.2%}
    - Average Turnover: {window_data['Average Turnover']:.2%}
    
    Please provide a structured analysis following this format:

    1. Historical Market Context:
    Describe the major market events and economic conditions during this period. Consider:
    - Major market events (e.g., Dot-com bubble, Financial Crisis, COVID-19)
    - Economic cycles and Fed policy changes
    - Sector trends and rotations
    
    2. Strategy Behavior Analysis:
    - How did the strategy adapt to market conditions?
    - Effectiveness of risk management (VIX-based sizing, stops)
    - Position timing and sector selection
    
    3. Performance Attribution:
    - Sources of returns and losses
    - Risk-adjusted performance analysis
    - Trading efficiency (turnover impact)
    
    4. Key Insights:
    List 2-3 crucial observations about strategy behavior and potential improvements.
    
    Keep the analysis focused on actionable insights for strategy enhancement.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error generating analysis: {str(e)}"

def analyze_all_windows(results_df, data):
    """
    Analyze all trading windows in the backtest results.
    
    Args:
        results_df (pd.DataFrame): DataFrame containing backtest results
        data (pd.DataFrame): Original price data including VIX
    
    Returns:
        list: List of analysis results for each window
    """
    analyses = []
    
    for idx, window in results_df.iterrows():
        # Get VIX data for the window period
        window_vix = data.loc[window['Start Date']:window['End Date']]['VIX']
        
        # Convert window data to dict for analysis
        window_dict = window.to_dict()
        
        # Get analysis for this window
        analysis = analyze_trading_window(window_dict, window_vix)
        analyses.append({
            'period': f"{window['Start Date'].strftime('%Y-%m-%d')} to {window['End Date'].strftime('%Y-%m-%d')}",
            'analysis': analysis
        })
    
    return analyses
