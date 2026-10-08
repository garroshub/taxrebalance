# Archived Original Sector Pair Trading Strategy

This directory contains the original **Quant Sector Rotation Strategy** work, including all modified local scripts, tests, its historical result plot, README and previous backtest method notes. It was moved here locally when the main repository was repurposed as **Tax-Aware Rebalancing Lab**.

The original strategy, annualized returns and sector-pair analysis are **not inputs to the new tax-aware optimizer**. This archive is preserved for provenance, auditing and optional future reference. It has not been deleted or pushed to GitHub.

To run the archived code (with its separate dependencies) from this folder:

```bash
cd legacy_sector_strategy
python -m pip install -r requirements.txt
python -m unittest -v test_execution_engine test_short_engine test_incremental_engine
streamlit run app.py
```

The main project now uses `../requirements.txt`, `../tax_rebalancing/`, `../test_tax_rebalancing.py`, and `../docs/`. This archive is not the active entry point.
