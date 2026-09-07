"""
03_provider.py — The actual running agent server.

Architecture:
- Serves A2A card at /.well-known/agent-card.json
- Handles POST /a2a message/send with skill: negotiate-erc8183-job
- Runs funded_job_watcher poll loop in a background thread
- Builds the DeliverableManifest with CANONICAL JSON (sort_keys=True, ensure_ascii=True)
- Calls submit_result which hashes the manifest and writes it on-chain

Run:
    uvicorn 03_provider:app --port 8010 --host 0.0.0.0
"""

import json
import os
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from web3 import Web3

load_dotenv()

from bnbagent import ERC8004Agent, EVMWalletProvider
from bnbagent.erc8183 import ERC8183JobOps, funded_job_watcher

from agents.rebalancing import run_rebalancing_analysis
from agents.grid_trading import run_grid_trading_analysis
from agents.yield_opt import run_yield_analysis
from agents.health_factor import run_health_factor_analysis

PROVIDER_KEY = os.environ["PROVIDER_PRIVATE_KEY"]
WALLET_PASS = os.getenv("WALLET_PASSWORD", "changeme")
NETWORK = os.getenv("NETWORK", "bsc-testnet")
AGENT_HOST = os.getenv("AGENT_HOST", "http://localhost:8010")

wallet = EVMWalletProvider(private_key=PROVIDER_KEY, password=WALLET_PASS)
identity_sdk = ERC8004Agent(wallet_provider=wallet, network=NETWORK)
job_ops = ERC8183JobOps(wallet_provider=wallet, network=NETWORK)
PROVIDER_ADDR = wallet.address

app = FastAPI()

# Deployment-only configuration: allows the Vercel-hosted UI to call the API.
# Agent implementations and execution logic are unchanged.
allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"]
)

AGENT_CARD = {
    "name": "Smart Money Era Multi-Category Agent",
    "description": (
        "Covers all four Smart Money Era hackathon categories: "
        "LP rebalancing, grid trading, yield optimisation, and health factor monitoring."
    ),
    "url": AGENT_HOST,
    "version": "1.0.0",
    "skills": [
        {
            "id": "negotiate-erc8183-job",
            "name": "Negotiate ERC-8183 Job",
            "description": "Returns a signed quote for a job. Specify category in task_description.",
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        },
        {
            "id": "erc8183-job-status",
            "name": "Job Status",
            "description": "Returns the on-chain status of a job by job_id.",
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        },
    ],
}


@app.get("/.well-known/agent-card.json")
def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/status")
def status():
    return {"status": "ok", "provider": PROVIDER_ADDR, "network": NETWORK}


@app.post("/a2a")
async def a2a_endpoint(request: Request):
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})

    if method != "message/send":
        return JSONResponse({"error": "unsupported method"}, status_code=400)

    message = params.get("message", {})
    parts = message.get("parts", [])
    data = next((p.get("data", {}) for p in parts if "data" in p), {})
    skill = data.get("skill", "")

    if skill == "negotiate-erc8183-job":
        task_description = data.get("task_description", "")
        payment_token = os.getenv("U_TOKEN_ADDRESS", "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565")
price_u = 1 * 10**18
        price_u = 1 * 10**18

        quote = job_ops.build_signed_quote(
            task_description=task_description,
            price=price_u,
            payment_token=payment_token,
        )

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {
                "message": {
                    "parts": [{
                        "type": "data",
                        "data": {
                            "skill": skill,
                            "provider_address": PROVIDER_ADDR,
                            "payment_token": payment_token,
                            "price": str(price_u),
                            "negotiation_hash": quote["negotiation_hash"],
                            "provider_sig": quote["provider_sig"],
                            "terms": {
                                "price": str(price_u),
                                "deliverables": "Structured analysis report in plain text",
                                "quality": "Real on-chain data, canonical JSON manifest",
                                "expiry_minutes": 10,
                            },
                        },
                    }],
                },
            },
        })

    elif skill == "erc8183-job-status":
        job_id = data.get("job_id")
        if not job_id:
            return JSONResponse({"error": "job_id required"}, status_code=400)
        job_state = job_ops.get_job(int(job_id))
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"message": {"parts": [{"type": "data", "data": job_state}]}},
        })

    return JSONResponse({"error": f"unknown skill: {skill}"}, status_code=400)


def _detect_category(job_description: str) -> str:
    """Infer which agent category this job is for from the task description."""
    desc = job_description.lower()
    if "rebalanc" in desc:
        return "rebalancing"
    if "grid" in desc:
        return "grid-trading"
    if "yield" in desc or "apr" in desc or "liquidity" in desc:
        return "yield"
    if "health" in desc or "liquidat" in desc or "borrow" in desc:
        return "health-factor"
    return "yield"


def _run_agent_for_category(category: str, wallet_address: str, job: dict) -> str:
    """Dispatch to the correct agent implementation and return the deliverable string."""
    task = job.get("description", "")
    if category == "rebalancing":
        return run_rebalancing_analysis(wallet_address)
    elif category == "grid-trading":
        return run_grid_trading_analysis(wallet_address)
    elif category == "yield":
        return run_yield_analysis(wallet_address)
    elif category == "health-factor":
        return run_health_factor_analysis(wallet_address)
    else:
        return f"Analysis complete for task: {task}"


def _build_canonical_manifest(job_id: int, content: str) -> tuple[str, str]:
    """Build the DeliverableManifest with canonical JSON and return its hash."""
    addresses = job_ops.contract_addresses
    manifest = {
        "version": 1,
        "job_id": job_id,
        "chain_id": 97,
        "contracts": {
            "commerce": addresses["commerce"],
            "router": addresses["router"],
            "policy": addresses["policy"],
        },
        "response": {
            "content": content,
            "content_type": "text/plain",
        },
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": "smart-money-era-provider",
        },
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = Web3.keccak(text=canonical).hex()
    return canonical, digest


_manifest_store: dict[str, str] = {}


def _on_funded_job(job: dict) -> None:
    """Called by funded_job_watcher for each FUNDED job."""
    job_id = job["job_id"]
    client = job.get("client", "unknown")
    task = job.get("description", "")

    print(f"\n[provider] FUNDED job #{job_id} received")
    print(f"[provider] client: {client}")
    print(f"[provider] task: {task[:80]}...")

    category = _detect_category(task)
    print(f"[provider] routing to: {category}")
    content = _run_agent_for_category(category, client, job)
    print(f"[provider] agent output: {len(content)} chars")

    manifest_text, manifest_hash = _build_canonical_manifest(job_id, content)
    _manifest_store[str(job_id)] = manifest_text
    deliverable_url = f"{AGENT_HOST}/manifests/{job_id}"

    print(f"[provider] manifest hash: {manifest_hash}")
    print(f"[provider] deliverable URL: {deliverable_url}")

    try:
        result = job_ops.submit_result(
            job_id=job_id,
            deliverable=manifest_hash,
            deliverable_url=deliverable_url,
        )
        print(f"[provider] ✓ submitted job #{job_id} tx: {result['transactionHash']}")
    except Exception as e:
        print(f"[provider] ✗ submit failed for job #{job_id}: {e}")


@app.get("/manifests/{job_id}")
def serve_manifest(job_id: int):
    """Serve the manifest verbatim so the buyer can verify its hash."""
    text = _manifest_store.get(str(job_id))
    if not text:
        return JSONResponse({"error": "manifest not found"}, status_code=404)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=text, media_type="application/json")


def _start_poll_loop():
    """Start the funded_job_watcher in a background thread."""
    print(f"[provider] starting funded_job_watcher for {PROVIDER_ADDR}")
    funded_job_watcher(
        job_ops=job_ops,
        provider_address=PROVIDER_ADDR,
        on_job=_on_funded_job,
        poll_interval=15,
    )


if __name__ == "__main__":
    import uvicorn
    t = threading.Thread(target=_start_poll_loop, daemon=True)
    t.start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8010)))
