# Quant Sector Rotation Strategy 📈

A paired sector ETF strategy: **simultaneously long the highest MA Energy sector and short the lowest MA Energy sector**. Orders execute the following trading close with two-leg cash accounting, VIX risk controls, transaction costs and borrow fees. See the actual trading contract and audit in [BACKTEST_DESIGN.md](BACKTEST_DESIGN.md).

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28%2B-red)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://quantrotation.streamlit.app/)

## 🚀 Try It Now!

Experience the strategy in action: [Quant Sector Rotation App](https://quantrotation.streamlit.app/)

## 🚀 Strategy Overview

This project implements a systematic sector rotation strategy using ETFs, combining momentum signals with intelligent risk management. The strategy employs a unique "Moving Average Energy" indicator for momentum measurement and incorporates VIX-based position sizing.

### 🎯 Key Features

- **MA Energy Ranking**: Rank sectors on multi-horizon moving-average displacement normalized by trailing volatility. Take the highest-ranked sector long and the lowest-ranked sector short, regardless of their absolute signs.
- **Dollar-Neutral Target**: Equal long/short dollar notional at entry (default +50% and −50% equity; 1× combined gross), with a small entry cushion for execution costs and borrow.
- **Dynamic Risk Management**: VIX-based position sizing, trailing stops on both longs and shorts, gross exposure limits and short margin checks.
- **LLM Strategy Review**: AI-powered performance analysis and strategy behavior insights
- **Interactive Dashboard**: Real-time strategy monitoring and backtesting visualization

## 📊 Audited Historical Backtest (2000–2026)

The older displayed performance numbers were produced by a flawed trade ledger and are **withdrawn**. The redesigned engine uses delayed fills, signed shares, borrowing fees and exact cash reconciliation. On the fixed 2000–2026 data and default parameters:

| Version | CAGR | Maximum drawdown |
| --- | ---: | ---: |
| Strongest-long / weakest-short pair | **−2.02%** | 45.81% |
| Long-only control (different strategy) | 2.40% | 30.57% |
| SPY buy-and-hold benchmark | 8.37% | Not calculated in this audit |

The paired strategy uses the same frozen 2000–2026 observations with 10 bps trading costs per side and an illustrative 200 bps annual short borrow rate. Its Sharpe is −0.945 and annualized volatility is 4.18%. **This strategy did not outperform SPY.** Results are historical descriptions, not independent out-of-sample validation. An earlier single-direction short model produced 0.66% CAGR; that was a different strategy and is **withdrawn from this project's main results**. See [BACKTEST_DESIGN.md](BACKTEST_DESIGN.md) for details.

## 🛠️ Technical Architecture

1. **Signal Generation**
   - Multi-timeframe signed MA Energy calculation
   - Cross-sectional strongest/weakest ranking and simultaneous long/short execution
   - Volatility normalization without same-day execution

2. **Risk Management**
   - VIX-based position sizing without trading the VIX itself
   - Short-sale collateral, daily borrow cost and gross exposure guardrails
   - Trailing stop implementation
   - Maximum drawdown control

3. **Strategy Review**
   - LLM-powered strategy behavior analysis
   - Historical context integration
   - Performance attribution

## 📦 Installation

```bash
git clone https://github.com/garroshub/Quant_Sector_Rotation_Strategy.git
cd Quant_Sector_Rotation_Strategy
pip install -r requirements.txt
```

## 🚀 Quick Start

```bash
streamlit run app.py
```

## AI Strategy Review Configuration

The AI strategy review is optional. To enable it, set a Gemini API key in your runtime environment:

```bash
export GOOGLE_API_KEY="your_gemini_api_key_here"
```

On Windows PowerShell:

```powershell
$env:GOOGLE_API_KEY="your_gemini_api_key_here"
```

Do not commit real API keys to the repository. If no key is configured, the dashboard still runs and the AI review panel reports that the feature is disabled.

## 📊 Dashboard Features

1. **Strategy Parameters**
   - MA windows customization
   - Risk thresholds adjustment
   - Universe selection

2. **Performance Analytics**
   - Rolling window analysis (descriptive, not fresh out-of-sample tests)
   - Risk metrics visualization
   - Position history tracking

3. **AI Strategy Review**
   - Strategy behavior analysis
   - Performance attribution
   - Improvement suggestions

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact

GitHub: [@garroshub](https://github.com/garroshub)

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=garroshub/Quant_Sector_Rotation_Strategy&type=Date)](https://star-history.com/#garroshub/Quant_Sector_Rotation_Strategy&Date)

---
**Disclaimer**: This strategy is for educational purposes only. Past performance does not guarantee future results. Always do your own research and consider your risk tolerance before trading.
