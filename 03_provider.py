import json
import os
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from web3 import Web3

load_dotenv()

from bnbagent import ERC8004Agent, EVMWalletProvider
from bnbagent.erc8183 import ERC8183JobOps, funded_job_watcher

from agents.rebalancing import run_rebalancing_analysis
from agents.grid_trading import run_grid_trading_analysis
from agents.yield_opt import run_yield_analysis
from agents.health_factor import run_health_factor_analysis

PROVIDER_KEY  = os.environ["PROVIDER_PRIVATE_KEY"]
WALLET_PASS   = os.getenv("WALLET_PASSWORD", "changeme")
NETWORK       = os.getenv("NETWORK", "bsc-testnet")
AGENT_HOST    = os.getenv("AGENT_HOST", "http://localhost:8010")
PAYMENT_TOKEN = os.getenv("U_TOKEN_ADDRESS", "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565")

wallet        = EVMWalletProvider(private_key=PROVIDER_KEY, password=WALLET_PASS)
identity_sdk  = ERC8004Agent(wallet_provider=wallet, network=NETWORK)
job_ops       = ERC8183JobOps(wallet_provider=wallet, network=NETWORK)
PROVIDER_ADDR = wallet.address
ACCOUNT       = Account.from_key(PROVIDER_KEY)

app = FastAPI()

_raw_origins    = os.getenv("CORS_ORIGINS", "*")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
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
    body   = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})

    if method != "message/send":
        return JSONResponse({"error": "unsupported method"}, status_code=400)

    message = params.get("message", {})
    parts   = message.get("parts", [])
    data    = next((p.get("data", {}) for p in parts if "data" in p), {})
    skill   = data.get("skill", "")

    if skill == "negotiate-erc8183-job":
        task_description = data.get("task_description", "")
        price_u  = 1 * 10**18
        expiry   = int(time.time()) + 600

        raw              = f"{task_description}:{price_u}:{PAYMENT_TOKEN}:{expiry}"
        negotiation_hash = "0x" + hashlib.sha256(raw.encode()).hexdigest()

        msg    = encode_defunct(hexstr=negotiation_hash)
        signed = ACCOUNT.sign_message(msg)
        sig    = signed.signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {
                "message": {
                    "parts": [{
                        "type": "data",
                        "data": {
                            "skill":            skill,
                            "provider_address": PROVIDER_ADDR,
                            "payment_token":    PAYMENT_TOKEN,
                            "price":            str(price_u),
                            "negotiation_hash": negotiation_hash,
                            "provider_sig":     sig,
                            "expiry":           expiry,
                            "terms": {
                                "price":          str(price_u),
                                "deliverables":   "Structured analysis report in plain text",
                                "quality":        "Real on-chain data, canonical JSON manifest",
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


# ── Agent dispatch ────────────────────────────────────────────────────────────

def _detect_category(desc: str) -> str:
    d = desc.lower()
    if "rebalanc" in d:
        return "rebalancing"
    if "grid" in d:
        return "grid-trading"
    if "yield" in d or "apr" in d or "liquidity" in d:
        return "yield"
    if "health" in d or "liquidat" in d or "borrow" in d:
        return "health-factor"
    return "yield"


def _run_agent(category: str, client: str, job: dict) -> str:
    if category == "rebalancing":
        return run_rebalancing_analysis(client)
    elif category == "grid-trading":
        return run_grid_trading_analysis(client)
    elif category == "yield":
        return run_yield_analysis(client)
    elif category == "health-factor":
        return run_health_factor_analysis(client)
    return f"Analysis complete for: {job.get('description', '')}"


_manifest_store: dict[str, str] = {}


def _on_funded_job(job: dict) -> None:
    # SDK delivers camelCase keys
    job_id = job.get("jobId") or job.get("job_id")
    client = job.get("client", "unknown")
    task   = job.get("description", "")

    print(f"\n[provider] FUNDED job #{job_id}  client={client}")
    print(f"[provider] task: {task[:80]}...")

    category = _detect_category(task)
    print(f"[provider] routing → {category}")
    content = _run_agent(category, client, job)
    print(f"[provider] agent output: {len(content)} chars")

    # Build and store manifest for /manifests/{job_id}
    manifest = json.dumps({
        "version":  1,
        "job_id":   job_id,
        "chain_id": 97,
        "response": {
            "content":      content,
            "content_type": "text/plain",
        },
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent":        "smart-money-era-provider",
        },
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    _manifest_store[str(job_id)] = manifest

    try:
        # submit_result takes the deliverable content string — SDK hashes it internally
        result = job_ops.submit_result(
            job_id=job_id,
            deliverable=content,
        )
        print(f"[provider] ✓ submitted tx: {result['transactionHash']}")
    except Exception as e:
        print(f"[provider] ✗ submit failed: {e}")


@app.get("/manifests/{job_id}")
def serve_manifest(job_id: int):
    text = _manifest_store.get(str(job_id))
    if not text:
        return JSONResponse({"error": "manifest not found"}, status_code=404)
    return PlainTextResponse(content=text, media_type="application/json")


def _start_watcher():
    print(f"[provider] starting funded_job_watcher for {PROVIDER_ADDR}")
    funded_job_watcher(
        job_ops=job_ops,
        provider_address=PROVIDER_ADDR,
        on_job=_on_funded_job,
        poll_interval=15,
    )


if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=_start_watcher, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AGENT_PORT", 8010)))
