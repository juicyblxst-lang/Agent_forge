"""
02_register_provider.py — Register your provider on ERC-8004 for all four
hackathon categories so discover.py can find them.

Run ONCE. Prints the agent_id for each registered agent.
Put each agent_id in .env as AGENT_ID_REBALANCING, etc.

MegaFuel (gas-free) is active on BSC Testnet for the ERC-8004 registry.
"""

import os
import sys
from dotenv import load_dotenv
from bnbagent import ERC8004Agent, EVMWalletProvider, AgentEndpoint

load_dotenv()

PROVIDER_KEY = os.getenv("PROVIDER_PRIVATE_KEY")
WALLET_PASS = os.getenv("WALLET_PASSWORD", "changeme")
AGENT_HOST = os.getenv("AGENT_HOST", "http://localhost:8010")

if not PROVIDER_KEY:
    print("Set PROVIDER_PRIVATE_KEY in .env")
    sys.exit(1)

wallet = EVMWalletProvider(private_key=PROVIDER_KEY, password=WALLET_PASS)
sdk = ERC8004Agent(wallet_provider=wallet, network="bsc-testnet")

AGENTS_TO_REGISTER = [
    {
        "name": "smart-money-rebalancing-agent",
        "category": "rebalancing",
        "description": (
            "[category:rebalancing] Automatically manages PancakeSwap V3 LP ranges on BSC. "
            "Detects out-of-range positions and resets to the optimal tick band based on "
            "current volatility and fee tier. Submits a signed action report with the new "
            "range, estimated gas, and projected fee capture improvement."
        ),
    },
    {
        "name": "smart-money-grid-trading-agent",
        "category": "grid-trading",
        "description": (
            "[category:grid-trading] Places and manages automated grid orders on PancakeSwap. "
            "Buys low, sells high within a configurable price band, capturing spread from "
            "sideways markets 24/7. Returns a trade log with entry/exit prices and P&L."
        ),
    },
    {
        "name": "smart-money-yield-agent",
        "category": "yield",
        "description": (
            "[category:yield] Routes deposited liquidity to the highest available APR across "
            "Aave V3, Venus, Lista Liquid Staking, and PancakeSwap pools on BSC. "
            "Rebalances daily. Returns a ranked APR comparison table with recommended action."
        ),
    },
    {
        "name": "smart-money-health-factor-agent",
        "category": "health-factor",
        "description": (
            "[category:health-factor] Monitors Aave V3 and Venus lending positions in "
            "real time. Flags positions approaching the liquidation threshold and returns "
            "a structured recommendation: top-up collateral amount, repay amount, or "
            "safe — with the current health factor and liquidation price."
        ),
    },
]


def register_or_find(agent_def: dict) -> int:
    """Register agent if not already registered. Returns agent_id."""
    name = agent_def["name"]

    existing = sdk.get_local_agent_info(name)
    if existing:
        agent_id = existing["agent_id"]
        print(f"\nalready registered: {name} → agentId={agent_id}")
        return agent_id

    agent_uri = sdk.generate_agent_uri(
        name=name,
        description=agent_def["description"],
        endpoints=[AgentEndpoint.a2a(f"{AGENT_HOST}")],
    )

    result = sdk.register_agent(agent_uri=agent_uri)
    agent_id = result["agentId"]
    print(f"\n✓ registered: {name} → agentId={agent_id}\ntx: {result['transactionHash']}")
    return agent_id


print("\n[register] registering 4 agents on BSC Testnet ERC-8004...\n")
ids = {}
for agent_def in AGENTS_TO_REGISTER:
    cat = agent_def["category"]
    print(f"[{cat}]")
    ids[cat] = register_or_find(agent_def)

print("\n── Add these to your .env ──────────────────────────────────────────────")
for cat, agent_id in ids.items():
    key = f"AGENT_ID_{cat.upper().replace('-', '_')}"
    print(f"{key}={agent_id}")
print()
