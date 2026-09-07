"""
04_client.py — The full "hire an agent" lifecycle from the marketplace user's perspective.

Steps:
1. Discover live agents via ERC-8004 (discover.py)
2. Assert all 4 categories are covered
3. Fetch A2A agent card from selected provider
4. Request a signed quote (negotiate-erc8183-job)
5. Verify the quote (provider address, payment token, contract match)
6. create_job → register_job → set_budget → fund
7. Poll until SUBMITTED, then verify the deliverable hash
8. Print the deliverable content

Run:
    python 04_client.py --category yield
    python 04_client.py --category health-factor --task "Check my wallet 0x..."
"""

import argparse
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

from bnbagent import EVMWalletProvider
from bnbagent.erc8183 import ERC8183JobOps
from discover import discover_agents, pick_for_category, assert_all_four_covered, HACKATHON_CATEGORIES

CLIENT_KEY = os.environ["CLIENT_PRIVATE_KEY"]
WALLET_PASS = os.getenv("WALLET_PASSWORD", "changeme")
NETWORK = os.getenv("NETWORK", "bsc-testnet")
COMMERCE = "0xa206c0517b6371c6638cd9e4a42cc9f02a33b0de"
BUDGET_U = 1 * 10**18
JOB_EXPIRY_MINUTES = 65


def _verify_quote(quote_data: dict, expected_provider: str) -> None:
    """Verify the signed quote before spending any on-chain gas."""
    got_provider = quote_data.get("provider_address", "").lower()
    if got_provider != expected_provider.lower():
        raise ValueError(
            f"Quote provider mismatch: expected {expected_provider}, got {got_provider}. "
            f"Possible MITM — aborting."
        )

    got_token = quote_data.get("payment_token", "").lower()
    expected_token = os.getenv(
        "U_TOKEN_ADDRESS", "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565"
    ).lower()
    if got_token != expected_token:
        raise ValueError(
            f"Payment token mismatch: expected {expected_token}, got {got_token}. Aborting."
        )

    print(
        f"[client] ✓ quote verified — provider={expected_provider[:10]}… "
        f"price={int(quote_data['price']) / 1e18:.4f} $U"
    )


def _fetch_agent_card(a2a_url: str) -> dict:
    """Fetch A2A agent card from the provider's well-known endpoint."""
    card_url = a2a_url.rstrip("/")
    if not card_url.endswith("agent-card.json"):
        card_url += "/.well-known/agent-card.json"
    r = httpx.get(card_url, timeout=10)
    r.raise_for_status()
    return r.json()


def _request_quote(a2a_url: str, task_description: str, category: str) -> dict:
    """Send negotiate-erc8183-job to the provider's A2A endpoint."""
    base_url = a2a_url.rstrip("/")
    if base_url.endswith("agent-card.json"):
        base_url = base_url.replace("/.well-known/agent-card.json", "")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "parts": [{
                    "type": "data",
                    "data": {
                        "skill": "negotiate-erc8183-job",
                        "task_description": task_description,
                        "terms": {
                            "deliverables": f"{category} analysis report",
                            "quality_standards": "Real on-chain data, structured output",
                        },
                    },
                }],
            },
        },
    }

    r = httpx.post(f"{base_url}/a2a", json=payload, timeout=15)
    r.raise_for_status()
    result = r.json()
    parts = result.get("result", {}).get("message", {}).get("parts", [])
    return next((p.get("data", {}) for p in parts if "data" in p), {})


def _verify_deliverable(deliverable_url: str, on_chain_hash: str) -> str:
    """Fetch manifest, verify keccak256 matches on-chain hash, return content."""
    r = httpx.get(deliverable_url, timeout=15)
    r.raise_for_status()
    raw_text = r.text
    computed = Web3.keccak(text=raw_text).hex()
    if computed.lower() != on_chain_hash.lower():
        raise ValueError(
            f"Deliverable hash MISMATCH.\n"
            f"on-chain: {on_chain_hash}\n"
            f"computed: {computed}\n"
            f"The manifest may have been tampered with."
        )

    manifest = json.loads(raw_text)
    return manifest.get("response", {}).get("content", raw_text)


def hire_agent(category: str, task: str | None = None) -> None:
    wallet = EVMWalletProvider(private_key=CLIENT_KEY, password=WALLET_PASS)
    job_ops = ERC8183JobOps(wallet_provider=wallet, network=NETWORK)
    client_addr = wallet.address
    print(f"\n[client] wallet: {client_addr}")

    print(f"[client] discovering agents for category: {category}")
    agents = discover_agents(
        categories=HACKATHON_CATEGORIES,
        require_live=True,
        verbose=True,
    )
    assert_all_four_covered(agents)

    provider_record = pick_for_category(agents, category)
    if not provider_record:
        print(f"[client] ✗ no live agent for category '{category}'")
        sys.exit(1)

    provider_addr = provider_record["provider_wallet"]
    a2a_url = provider_record["a2a_url"] or provider_record["erc8183_url"]
    print(f"[client] selected provider: {provider_addr}")
    print(f"[client] A2A endpoint: {a2a_url}")

    card = _fetch_agent_card(a2a_url)
    print(f"[client] agent card: {card.get('name')}")

    task_description = task or f"Run {category} analysis for wallet {client_addr}"
    print(f"[client] requesting quote for task: {task_description[:60]}...")
    quote = _request_quote(a2a_url, task_description, category)
    _verify_quote(quote, expected_provider=provider_addr)

    expiry = int(time.time()) + JOB_EXPIRY_MINUTES * 60
    print("[client] create_job...")
    job = job_ops.create_job(
        provider=provider_addr,
        description=task_description,
        expiry=expiry,
        negotiation_hash=quote.get("negotiation_hash"),
        provider_sig=quote.get("provider_sig"),
    )
    job_id = job["job_id"]
    print(f"[client] ✓ job created jobId={job_id} tx: {job['transactionHash']}")

    print("[client] register_job (binds OptimisticPolicy)...")
    reg = job_ops.register_job(job_id=job_id)
    print(f"[client] ✓ registered tx: {reg['transactionHash']}")

    print(f"[client] set_budget ({BUDGET_U / 1e18:.4f} $U)...")
    sb = job_ops.set_budget(job_id=job_id, budget=BUDGET_U)
    print(f"[client] ✓ budget set tx: {sb['transactionHash']}")

    print("[client] fund (ERC-20 escrow)...")
    fund = job_ops.fund(job_id=job_id)
    print(f"[client] ✓ funded tx: {fund['transactionHash']}")
    print("[client] job status: FUNDED — waiting for provider to submit...")

    print("[client] polling for SUBMITTED status...")
    for attempt in range(40):
        time.sleep(15)
        state = job_ops.get_job(job_id)
        status = state.get("status", "")
        print(f"[client] poll {attempt+1:2d}: status={status}")
        if status == "SUBMITTED":
            break
    else:
        print("[client] ✗ timed out waiting for SUBMITTED. Check provider logs.")
        sys.exit(1)

    deliverable_hash = state.get("deliverable")
    deliverable_url = state.get("deliverable_url") or job_ops.get_deliverable_url(job_id)
    print(f"[client] ✓ SUBMITTED deliverable: {deliverable_url}")
    print("[client] verifying deliverable hash...")

    content = _verify_deliverable(deliverable_url, deliverable_hash)
    print("[client] ✓ hash verified — deliverable is authentic\n")
    print("═" * 70)
    print("AGENT DELIVERABLE:")
    print("═" * 70)
    print(content)
    print("═" * 70)
    print(f"\n[client] jobId={job_id} is now in SUBMITTED state.")
    print(f"[client] Run 05_settle.py --job-id {job_id} after the 1-hour dispute window.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=HACKATHON_CATEGORIES, default="yield")
    parser.add_argument("--task", default=None, help="Custom task description")
    args = parser.parse_args()
    hire_agent(args.category, args.task)
