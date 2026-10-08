import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import model
from datetime import datetime
import yfinance as yf
import strategy_analysis_agent as agent

# Set page config
st.set_page_config(
    page_title="Sector Long–Short Pair Strategy",
    page_icon="📈",
    layout="wide"
)

# Title and description
st.title("📈 Sector ETF Long–Short Pair Strategy")

# Create two columns for the description
col1, col2 = st.columns(2)

# First column
with col1:
    st.subheader("🎯 Signal Generation & Position Selection")
    st.markdown("""
    - 📊 Moving Average Energy Indicator
      * Calculates momentum using multiple MA windows [10, 40, 140]
      * Energy = Σ(MA_fast - MA_slow) / σ_price
      * Higher energy indicates stronger trend momentum
      * Normalized by price volatility for cross-asset comparison
    - 🔍 Multi-timeframe Trend Analysis
    - 🎯 Rank six sector ETFs by the same MA Energy signal
    - 📈 Buy the highest-ranked sector and short the lowest-ranked sector together
    - ⚖️ Target +50% / −50% for a near dollar-neutral pair (1x combined gross)
    - 🧪 Compare with a separate, explicitly long-only control
    """)

# Second column
with col2:
    st.subheader("🛡️ Risk Management")
    st.markdown(f"""
    - 📉 VIX-based Position Sizing:
      * VIX > VIX_EXTREME_THRESHOLD: ❌ Exit All
      * VIX > VIX_HIGH_THRESHOLD: ⚠️ 50% Size
      * VIX ≤ VIX_HIGH_THRESHOLD: ✅ Full Size
    - 🎚️ Close-triggered trailing stop, executed next trading close
    - 🔒 Drawdown and short margin / gross-exposure controls
    - 🧾 Restricted short proceeds, annual borrow fees, and two-leg trading costs
    """)

# Create MA Energy example using plotly
st.markdown("### 📊 MA Energy Signal Example")
random_walk = np.array([1] + [np.random.randn() for _ in range(99)]).cumsum()
ma_energy = random_walk * 0.5 + 2 + np.random.randn(100) * 0.3

fig1 = go.Figure()
fig1.add_trace(go.Scatter(y=random_walk, name='Price', line=dict(color='#2E86C1', width=2)))
fig1.add_trace(go.Scatter(y=ma_energy, name='MA Energy', line=dict(color='#E67E22', width=2)))

fig1.update_layout(
    title='MA Energy Example',
    title_x=0.5,
    height=400,
    template='plotly_dark',
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=20, r=20, t=50, b=20)
)
st.plotly_chart(fig1, use_container_width=True)

# Sidebar parameters
st.sidebar.header("Strategy Parameters")

# Signal Parameters
st.sidebar.subheader("Signal Parameters")
base_threshold = st.sidebar.slider(
    "Base Signal Threshold",
    min_value=0.05,
    max_value=0.3,
    value=0.1,
    step=0.01,
    help="Base threshold for signal strength"
)

vol_window = st.sidebar.slider(
    "Volatility Window",
    min_value=10,
    max_value=50,
    value=30,
    step=5,
    help="Window for volatility calculation"
)

# Risk Management Parameters
st.sidebar.subheader("Risk Management")
trailing_stop = st.sidebar.slider(
    "Trailing Stop (%)",
    min_value=2,
    max_value=20,
    value=5,
    step=1,
    help="Trailing stop loss percentage"
) / 100

max_drawdown_stop = st.sidebar.slider(
    "Maximum Drawdown Stop (%)",
    min_value=10,
    max_value=30,
    value=20,
    step=1,
    help="Maximum drawdown stop loss percentage"
) / 100

vix_high = st.sidebar.slider(
    "VIX High Threshold",
    min_value=20,
    max_value=40,
    value=25,
    step=1,
    help="VIX level for reducing position sizes"
)

vix_extreme = st.sidebar.slider(
    "VIX Extreme Threshold",
    min_value=35,
    max_value=60,
    value=50,
    step=1,
    help="VIX level for exiting positions"
)

# Backtest Parameters
st.sidebar.subheader("Backtest Settings")
allow_short = st.sidebar.checkbox(
    "Enable strongest-long / weakest-short pair", value=True,
    help="Default strategy: long the highest MA Energy sector and short the lowest simultaneously. Unchecking is a long-only ablation, not the main strategy. VIX is never traded."
)
transaction_cost_bps = st.sidebar.slider(
    "Transaction cost (bps per traded side)", 0, 50, 10, 5
)
annual_borrow_cost_bps = st.sidebar.slider(
    "Annual short borrow fee (bps)", 0, 1000, 200, 25,
    help="A constant illustration; historical borrowing availability and rates are unobserved."
)
start_date = st.sidebar.date_input(
    "Start Date",
    value=datetime(2000, 1, 1),
    help="Backtest start date"
)

# Universe display
st.sidebar.subheader("Investment Universe")
universe = {
    'SPY': 'S&P 500 (Benchmark)',
    'XLK': 'Technology',
    'XLV': 'Healthcare',
    'XLE': 'Energy',
    'XLF': 'Financials',
    'XLI': 'Industrials',
    'XLY': 'Consumer Discretionary'
}
st.sidebar.markdown("\n".join([f"- **{k}**: {v}" for k, v in universe.items()]))

# Run backtest button
if st.sidebar.button('🚀 Run Backtest'):
    model.BASE_THRESHOLD = base_threshold
    model.VOL_WINDOW = vol_window
    model.TRAILING_STOP = trailing_stop
    model.MAX_DRAWDOWN_STOP = max_drawdown_stop
    model.VIX_HIGH_THRESHOLD = vix_high
    model.VIX_EXTREME_THRESHOLD = vix_extreme
    model.ALLOW_SHORT = allow_short
    model.TRANSACTION_COST_BPS = transaction_cost_bps
    model.ANNUAL_BORROW_COST_BPS = annual_borrow_cost_bps
    
    with st.spinner('📊 Downloading data and running backtest...'):
        try:
            data = model.download_data(start_date=start_date.strftime('%Y-%m-%d'))
            
            if data is None or data.empty:
                st.error("❌ No data was downloaded. This could be due to API limits or connectivity issues.")
                st.info("🔄 Please try again in a few minutes.")
            else:
                st.info(f"📅 Analysis Period: {data.index[0].strftime('%Y-%m-%d')} to {data.index[-1].strftime('%Y-%m-%d')}")
                
                if len(data) < 252:
                    st.error("⚠️ Not enough data available. Please select an earlier start date.")
                else:
                    results = model.rolling_backtest(data)
                    
                    if results.empty:
                        st.error("❌ No results generated. Please check the parameters and try again.")
                    else:
                        # Strategy Analysis Section
                        st.subheader("📊 LLM Strategist Review")
                        analyses = agent.analyze_all_windows(results, data)
                        
                        for analysis in analyses:
                            with st.expander(f"**{analysis['period']}**"):
                                st.markdown(analysis['analysis'])
                        
                        # Create rolling window performance visualization
                        st.subheader("📈 Rolling Window Performance Analysis")
                        
                        # Get the latest window data
                        latest_window = results.iloc[-1]
                        
                        # Create window period labels
                        window_labels = [f"{row['Start Date'].strftime('%Y-%m')} to {row['End Date'].strftime('%Y-%m')}" 
                                       for _, row in results.iterrows()]
                        
                        # Create a bar chart comparing returns across windows
                        fig = go.Figure()
                        
                        # Add bars for strategy and benchmark returns
                        fig.add_trace(go.Bar(
                            x=window_labels,
                            y=results['Strategy Return']*100,
                            name='Strategy Return',
                            marker_color='#2E86C1'
                        ))
                        
                        fig.add_trace(go.Bar(
                            x=window_labels,
                            y=results['SPY Return']*100,
                            name='SPY Return',
                            marker_color='#E67E22'
                        ))
                        
                        # Add Sharpe ratio lines
                        fig.add_trace(go.Scatter(
                            x=window_labels,
                            y=results['Strategy Sharpe'],
                            name='Strategy Sharpe',
                            line=dict(color='#2ECC71', width=2),
                            yaxis='y2'
                        ))
                        
                        fig.add_trace(go.Scatter(
                            x=window_labels,
                            y=results['SPY Sharpe'],
                            name='SPY Sharpe',
                            line=dict(color='#F39C12', width=2, dash='dash'),
                            yaxis='y2'
                        ))
                        
                        # Update layout with secondary y-axis
                        fig.update_layout(
                            title='Rolling Window Returns and Sharpe Ratio',
                            title_x=0.5,
                            xaxis_title='Window Period',
                            yaxis_title='Annual Return (%)',
                            yaxis2=dict(
                                title='Sharpe Ratio',
                                overlaying='y',
                                side='right'
                            ),
                            height=500,
                            template='plotly_dark',
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, 
                                      xanchor="right", x=1),
                            margin=dict(l=20, r=20, t=100, b=20),
                            barmode='group',
                            xaxis=dict(
                                tickangle=45,
                                tickmode='array',
                                ticktext=window_labels,
                                tickvals=window_labels
                            )
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # Show risk metrics in a separate chart
                        fig_risk = go.Figure()
                        
                        # Add max drawdown bars
                        fig_risk.add_trace(go.Bar(
                            x=window_labels,
                            y=results['Strategy Max Drawdown']*100,
                            name='Strategy Drawdown',
                            marker_color='#E74C3C'
                        ))
                        
                        fig_risk.add_trace(go.Bar(
                            x=window_labels,
                            y=results['SPY Max Drawdown']*100,
                            name='SPY Drawdown',
                            marker_color='#F39C12'
                        ))
                        
                        # Add turnover line
                        fig_risk.add_trace(go.Scatter(
                            x=window_labels,
                            y=results['Average Turnover']*100,
                            name='Turnover',
                            line=dict(color='#2ECC71', width=2),
                            yaxis='y2'
                        ))
                        
                        # Update layout
                        fig_risk.update_layout(
                            title='Risk Metrics by Window',
                            title_x=0.5,
                            xaxis_title='Window Period',
                            yaxis_title='Maximum Drawdown (%)',
                            yaxis2=dict(
                                title='Average Turnover (%)',
                                overlaying='y',
                                side='right'
                            ),
                            height=500,
                            template='plotly_dark',
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, 
                                      xanchor="right", x=1),
                            margin=dict(l=20, r=20, t=100, b=20),
                            barmode='group',
                            xaxis=dict(
                                tickangle=45,
                                tickmode='array',
                                ticktext=window_labels,
                                tickvals=window_labels
                            )
                        )
                        
                        st.plotly_chart(fig_risk, use_container_width=True)
                        
                        # Show detailed metrics in expandable section
                        with st.expander("📋 Detailed Performance Metrics"):
                            # Overall metrics
                            st.subheader("Overall Performance")
                            metrics_df = pd.DataFrame({
                                'Metric': ['Annual Return', 'Sharpe Ratio', 
                                         'Max Drawdown', 'Volatility'],
                                'Strategy': [
                                    f"{latest_window['Strategy Return']:.2%}",
                                    f"{latest_window['Strategy Sharpe']:.2f}",
                                    f"{latest_window['Strategy Max Drawdown']:.2%}",
                                    f"{latest_window['Strategy Volatility']:.2%}"
                                ],
                                'Benchmark (SPY)': [
                                    f"{latest_window['SPY Return']:.2%}",
                                    f"{latest_window['SPY Sharpe']:.2f}",
                                    f"{latest_window['SPY Max Drawdown']:.2%}",
                                    f"{latest_window['SPY Volatility']:.2%}"
                                ]
                            })
                            st.table(metrics_df)
                            
                            # Rolling window metrics
                            st.subheader("Rolling Window Performance")
                            for idx, row in results.iterrows():
                                st.markdown(f"**Window {row['Start Date'].strftime('%Y-%m-%d')} to {row['End Date'].strftime('%Y-%m-%d')}**")
                                window_metrics = pd.DataFrame({
                                    'Metric': ['Annual Return', 'Sharpe Ratio', 
                                             'Max Drawdown', 'Volatility'],
                                    'Strategy': [
                                        f"{row['Strategy Return']:.2%}",
                                        f"{row['Strategy Sharpe']:.2f}",
                                        f"{row['Strategy Max Drawdown']:.2%}",
                                        f"{row['Strategy Volatility']:.2%}"
                                    ],
                                    'Benchmark (SPY)': [
                                        f"{row['SPY Return']:.2%}",
                                        f"{row['SPY Sharpe']:.2f}",
                                        f"{row['SPY Max Drawdown']:.2%}",
                                        f"{row['SPY Volatility']:.2%}"
                                    ]
                                })
                                st.table(window_metrics)
                        
                        # Display current holdings
                        st.subheader("📊 Latest Portfolio Analysis")
                        signals = model.generate_signals(data)
                        portfolio, positions = model.backtest(data, signals)
                        
                        # Get active positions from the last row of positions
                        active_positions = positions.iloc[-1]
                        active_positions = active_positions[active_positions > 0]
                        
                        if len(active_positions) > 0:
                            st.write("Current Holdings:")
                            for etf, shares in active_positions.items():
                                st.write(f"- {etf} ({universe[etf]}): {int(shares)} shares")
                        else:
                            st.write("Currently no active positions")
                            
        except Exception as e:
            st.error(f"❌ Error during backtest: {str(e)}")
            st.info("🔄 Please check your parameters and try again.")
else:
    st.info("👈 Adjust the parameters in the sidebar and click '🚀 Run Backtest' to start the analysis")
