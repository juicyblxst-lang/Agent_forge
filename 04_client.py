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
from bnbagent.erc8183 import ERC8183Client
from discover import discover_agents, pick_for_category, assert_all_four_covered, HACKATHON_CATEGORIES

CLIENT_KEY         = os.environ["CLIENT_PRIVATE_KEY"]
WALLET_PASS        = os.getenv("WALLET_PASSWORD", "changeme")
NETWORK            = os.getenv("NETWORK", "bsc-testnet")
AGENT_HOST         = os.getenv("AGENT_HOST", "https://agent-forge-atdz.onrender.com")
U_TOKEN_ADDRESS    = os.getenv("U_TOKEN_ADDRESS", "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565")
JOB_EXPIRY_MINUTES = 65


def _verify_quote(quote_data: dict, expected_provider: str) -> None:
    got_provider = quote_data.get("provider_address", "").lower()
    if got_provider != expected_provider.lower():
        raise ValueError(
            f"Quote provider mismatch: expected {expected_provider}, got {got_provider}. Aborting."
        )
    got_token = quote_data.get("payment_token", "").lower()
    if got_token != U_TOKEN_ADDRESS.lower():
        raise ValueError(
            f"Payment token mismatch: expected {U_TOKEN_ADDRESS}, got {got_token}. Aborting."
        )
    print(
        f"[client] quote verified -- provider={expected_provider[:10]}... "
        f"price={int(quote_data['price']) / 1e18:.4f} $U"
    )


def _fetch_agent_card(a2a_url: str) -> dict:
    card_url = a2a_url.rstrip("/")
    if not card_url.endswith("agent-card.json"):
        card_url += "/.well-known/agent-card.json"
    r = httpx.get(card_url, timeout=10)
    r.raise_for_status()
    return r.json()


def _request_quote(a2a_url: str, task_description: str, category: str) -> dict:
    base_url = a2a_url.rstrip("/").replace("/.well-known/agent-card.json", "")
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


def _verify_deliverable(deliverable_url: str, on_chain_hash) -> str:
    r = httpx.get(deliverable_url, timeout=15)
    r.raise_for_status()
    raw_text = r.text

    # Normalise on-chain hash to hex string
    if isinstance(on_chain_hash, bytes):
        on_chain_hex = on_chain_hash.hex()
    else:
        on_chain_hex = str(on_chain_hash).lower().lstrip("0x")

    # Hash canonical JSON (sorted keys, no spaces) -- matches DeliverableManifest.manifest_hash()
    manifest  = json.loads(raw_text)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    computed  = Web3.keccak(text=canonical).hex().lstrip("0x")

    if computed.lower() != on_chain_hex.lower():
        raise ValueError(
            f"Deliverable hash MISMATCH.\non-chain: {on_chain_hex}\ncomputed: {computed}"
        )

    return manifest.get("response", {}).get("content", raw_text)


def hire_agent(category: str, task: str | None = None) -> None:
    wallet      = EVMWalletProvider(private_key=CLIENT_KEY, password=WALLET_PASS)
    erc8183     = ERC8183Client(wallet, network=NETWORK)
    client_addr = wallet.address
    print(f"\n[client] wallet: {client_addr}")

    # Discover
    print(f"[client] discovering agents for category: {category}")
    agents = discover_agents(categories=HACKATHON_CATEGORIES, require_live=True, verbose=True)
    assert_all_four_covered(agents)

    provider_record = pick_for_category(agents, category)
    if not provider_record:
        print(f"[client] no live agent for category '{category}'")
        sys.exit(1)

    provider_addr = (
        provider_record["provider_wallet"]
        or "0x46cBFBdDfeDDDc783D1f58976F91a488710695dc"
    )
    a2a_url = provider_record["a2a_url"] or provider_record["erc8183_url"]
    print(f"[client] selected provider: {provider_addr}")
    print(f"[client] A2A endpoint: {a2a_url}")

    # Agent card
    card = _fetch_agent_card(a2a_url)
    print(f"[client] agent card: {card.get('name')}")

    # Quote
    task_description = task or f"Run {category} analysis for wallet {client_addr}"
    print(f"[client] requesting quote for task: {task_description[:60]}...")
    quote = _request_quote(a2a_url, task_description, category)
    _verify_quote(quote, expected_provider=provider_addr)

    # Budget & decimals
    decimals   = erc8183.token_decimals()
    budget     = 1 * (10 ** decimals)
    expired_at = int(time.time()) + JOB_EXPIRY_MINUTES * 60

    # create_job
    print("[client] create_job...")
    res    = erc8183.create_job(
        provider=provider_addr,
        expired_at=expired_at,
        description=task_description,
    )
    job_id = res["jobId"]
    print(f"[client] job created jobId={job_id} tx: {res['transactionHash']}")

    # register_job
    print("[client] register_job...")
    reg = erc8183.register_job(job_id)
    print(f"[client] registered tx: {reg['transactionHash']}")

    # set_budget
    print(f"[client] set_budget ({budget / 1e18:.4f} $U)...")
    sb = erc8183.set_budget(job_id, budget)
    print(f"[client] budget set tx: {sb['transactionHash']}")

    # fund
    print("[client] fund (ERC-20 escrow)...")
    fund = erc8183.fund(job_id, budget)
    print(f"[client] funded tx: {fund['transactionHash']}")
    print("[client] status: FUNDED -- waiting for provider to submit...")

    # Poll for SUBMITTED
    print("[client] polling for SUBMITTED status...")
    state = None
    for attempt in range(40):
        time.sleep(15)
        state  = erc8183.get_job(job_id)
        status = state.status if hasattr(state, "status") else state.get("status", "")
        print(f"[client] poll {attempt+1:2d}: status={status}")
        if str(status) in ("SUBMITTED", "2") or status == 2:
            break
    else:
        print("[client] timed out. Check provider logs.")
        sys.exit(1)

    deliverable_hash = state.get("deliverable") if isinstance(state, dict) else getattr(state, "deliverable", None)
    deliverable_url  = (
        (state.get("deliverableUrl") if isinstance(state, dict) else None)
        or f"{AGENT_HOST}/manifests/{job_id}"
    )
    print(f"[client] SUBMITTED deliverable: {deliverable_url}")

    content = _verify_deliverable(deliverable_url, deliverable_hash)
    print("[client] hash verified -- deliverable is authentic\n")
    print("=" * 70)
    print("AGENT DELIVERABLE:")
    print("=" * 70)
    print(content)
    print("=" * 70)
    print(f"\n[client] jobId={job_id} complete.")
    print(f"[client] Run 05_settle.py --job-id {job_id} after the dispute window.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", choices=HACKATHON_CATEGORIES, default="yield")
    parser.add_argument("--task", default=None)
    args = parser.parse_args()
    hire_agent(args.category, args.task)
