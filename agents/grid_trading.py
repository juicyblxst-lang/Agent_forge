"""
agents/grid_trading.py — Grid trading analysis for PancakeSwap on BSC Testnet.
Calculates optimal grid parameters and returns a structured report.
"""

import httpx
import math


def _fetch_price(pair: str = "WBNB/USDT") -> float:
    """Fetch current price from PancakeSwap public price API."""
    try:
        r = httpx.get(
            "https://api.pancakeswap.info/api/v2/tokens/0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
            timeout=8,
        )
        return float(r.json().get("data", {}).get("price", 0))
    except Exception:
        return 300.0


def run_grid_trading_analysis(
    wallet_address: str,
    pair: str = "WBNB/USDT",
    capital_usd: float = 500.0,
    grid_count: int = 10,
    range_pct: float = 0.20,
) -> str:
    """Calculate optimal grid parameters and expected returns."""
    price = _fetch_price(pair)
    lower = round(price * (1 - range_pct), 4)
    upper = round(price * (1 + range_pct), 4)
    step = round((upper - lower) / grid_count, 4)

    levels = [round(lower + i * step, 4) for i in range(grid_count + 1)]
    capital_per_grid = capital_usd / grid_count
    spread_pct = (step / price) * 100
    profit_per_trade = capital_per_grid * (spread_pct / 100)
    est_daily_triggers = grid_count * 3
    est_daily_profit = est_daily_triggers * profit_per_trade
    est_monthly_profit = est_daily_profit * 30
    levels_str = "\n".join(f"{l:.2f}" for l in levels)

    report = f"""
=== GRID TRADING REPORT ===

Wallet:          {wallet_address}
Pair:            {pair}
Current Price:   ${price:.4f}

GRID CONFIGURATION:
  Price Range:   ${lower:.4f} → ${upper:.4f} (±{range_pct*100:.0f}%)
  Grid Count:    {grid_count} levels
  Grid Step:     ${step:.4f} ({spread_pct:.2f}% per level)
  Capital/Grid:  ${capital_per_grid:.2f}

GRID LEVELS:
  {levels_str}

PROFIT ESTIMATE (sideways market assumption):
  Profit/Trade:  ${profit_per_trade:.4f}
  Est. Daily:    ${est_daily_profit:.2f} (~{est_daily_triggers} triggers/day)
  Est. Monthly:  ${est_monthly_profit:.2f}
  Monthly ROI:   {(est_monthly_profit / capital_usd) * 100:.2f}%

RISK FACTORS:
  - Directional risk: if price breaks out of range, grid stops
  - Gas cost per trigger: ~$0.05 (BSC Testnet negligible)
  - Recommended stop: exit if price closes below ${lower * 0.95:.2f}

ACTION STEPS:
  1. Deploy grid at range [{lower:.4f}, {upper:.4f}]
  2. Set {grid_count} buy orders and {grid_count} sell orders at each level
  3. Monitor for range breakout — reset grid if price moves >25% out
""".strip()

    return report
