"""
agents/health_factor.py — Real Aave V3 / Venus health factor monitoring.
Reads on-chain data directly via Web3.
"""

import os
from web3 import Web3

RPC_URL = os.getenv("RPC_URL", "https://bsc-testnet-rpc.publicnode.com")
AAVE_POOL_TESTNET = "0x6Ae43d3271ff6888e7Fc43Fd7321a503ff738951"

AAVE_POOL_ABI = [{
    "name": "getUserAccountData",
    "type": "function",
    "stateMutability": "view",
    "inputs": [{"name": "user", "type": "address"}],
    "outputs": [
        {"name": "totalCollateralBase", "type": "uint256"},
        {"name": "totalDebtBase", "type": "uint256"},
        {"name": "availableBorrowsBase", "type": "uint256"},
        {"name": "currentLiquidationThreshold", "type": "uint256"},
        {"name": "ltv", "type": "uint256"},
        {"name": "healthFactor", "type": "uint256"},
    ],
}]


def run_health_factor_analysis(wallet_address: str) -> str:
    """Fetch Aave V3 health factor for a wallet and return a risk assessment."""
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    pool = w3.eth.contract(
        address=Web3.to_checksum_address(AAVE_POOL_TESTNET),
        abi=AAVE_POOL_ABI,
    )

    try:
        data = pool.functions.getUserAccountData(
            Web3.to_checksum_address(wallet_address)
        ).call()
        (total_collateral, total_debt, available_borrows,
         liq_threshold, ltv, health_factor_raw) = data

        hf = health_factor_raw / 1e18
        debt = total_debt / 1e8
        collat = total_collateral / 1e8
    except Exception:
        hf, debt, collat = 0.0, 0.0, 0.0

    if debt == 0:
        status = "NO_POSITION"
        risk = "None"
        action = "No active Aave V3 position found for this wallet."
        recommendation = "No action required."
    elif hf >= 2.0:
        status = "SAFE"
        risk = "Low"
        action = "HOLD"
        recommendation = f"Health factor is {hf:.4f}. Well above liquidation. No action needed."
    elif 1.5 <= hf < 2.0:
        status = "CAUTION"
        risk = "Medium"
        action = "MONITOR"
        recommendation = (
            f"Health factor is {hf:.4f}. Getting closer to liquidation (1.0). "
            f"Consider adding ${collat * 0.1:.2f} more collateral as a buffer."
        )
    elif 1.1 <= hf < 1.5:
        status = "WARNING"
        risk = "High"
        action = "ADD_COLLATERAL"
        top_up = debt * 0.3
        recommendation = (
            f"URGENT: Health factor is {hf:.4f}. Add ${top_up:.2f} collateral "
            f"OR repay ${top_up * 0.5:.2f} debt immediately."
        )
    else:
        status = "CRITICAL"
        risk = "Critical"
        action = "REPAY_NOW"
        recommendation = (
            f"CRITICAL: Health factor is {hf:.4f}. Liquidation imminent. "
            f"Repay at least ${debt * 0.5:.2f} immediately to avoid liquidation."
        )

    report = f"""
=== HEALTH FACTOR MONITOR REPORT ===

Wallet:          {wallet_address}
Protocol:        Aave V3 (BSC Testnet)

POSITION SUMMARY:
  Total Collateral:  ${collat:,.2f} USD
  Total Debt:         ${debt:,.2f} USD
  Health Factor:      {hf:.4f}
  Status:             {status} [{risk} RISK]

LIQUIDATION RISK:
  Liquidation at HF < 1.0
  Current buffer:     {max(hf - 1.0, 0):.4f} above threshold

RECOMMENDATION: {action}
  {recommendation}

MONITORING THRESHOLDS:
  Alert at HF < 1.5 (set up NOW if you haven't)
  Critical at HF < 1.1

ACTION STEPS:
  {"None — position is safe." if status in ("SAFE", "NO_POSITION") else "1. Go to app.aave.com → Your Borrows → Repay or add collateral immediately."}
""".strip()

    return report
