"""
05_settle.py -- Settle, dispute, or reclaim a job after the dispute window.

The OptimisticPolicy window is 1 hour.
- AFTER 1 hour with no dispute: settle() releases payment to provider
- WITHIN 1 hour: dispute() contests and triggers voter review
- AFTER expiry with no submission: claimRefund() returns escrow to client

Usage:
    python 05_settle.py --job-id 42
    python 05_settle.py --job-id 42 --dispute
    python 05_settle.py --job-id 42 --refund
"""

import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from bnbagent import EVMWalletProvider
from bnbagent.erc8183 import ERC8183JobOps

CLIENT_KEY             = os.environ["CLIENT_PRIVATE_KEY"]
WALLET_PASS            = os.getenv("WALLET_PASSWORD", "changeme")
NETWORK                = os.getenv("NETWORK", "bsc-testnet")
DISPUTE_WINDOW_SECONDS = 3600


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--dispute", action="store_true", help="Dispute the result")
    parser.add_argument("--refund", action="store_true", help="Claim refund (expired job)")
    args = parser.parse_args()

    wallet  = EVMWalletProvider(private_key=CLIENT_KEY, password=WALLET_PASS)
    job_ops = ERC8183JobOps(wallet_provider=wallet, network=NETWORK)
    job_id  = args.job_id

    state  = await job_ops.get_job(job_id)
    status = state.get("status", "")
    print(f"\n[settle] job #{job_id} current status: {status}")

    if args.refund:
        print(f"[settle] claiming refund for expired job #{job_id}...")
        result = await job_ops.claim_refund(job_id=job_id)
        print(f"[settle] refund claimed tx: {result['transactionHash']}")
        return

    if args.dispute:
        if status != "SUBMITTED":
            print(f"[settle] can only dispute SUBMITTED jobs, got: {status}")
            sys.exit(1)
        submitted_at = state.get("submitted_at", 0)
        window_end   = submitted_at + DISPUTE_WINDOW_SECONDS
        remaining    = window_end - time.time()
        if remaining <= 0:
            print(f"[settle] dispute window has closed ({DISPUTE_WINDOW_SECONDS}s). Cannot dispute.")
            sys.exit(1)
        print(f"[settle] disputing job #{job_id} ({remaining:.0f}s remaining in window)...")
        result = await job_ops.dispute(job_id=job_id)
        print(f"[settle] disputed tx: {result['transactionHash']}")
        print("[settle] job is now DISPUTED -- voters will review within 24h")
        print(f"[settle] monitor with: python 05_settle.py --job-id {job_id}")
        return

    if status != "SUBMITTED":
        print(f"[settle] can only settle SUBMITTED jobs, got: {status}")
        if status == "FUNDED":
            print("[settle] Provider has not submitted yet. Wait or check provider logs.")
        sys.exit(1)

    submitted_at = state.get("submitted_at", 0)
    window_end   = submitted_at + DISPUTE_WINDOW_SECONDS
    remaining    = window_end - time.time()

    if remaining > 0:
        print(f"[settle] dispute window still open -- {remaining:.0f}s remaining")
        print("[settle] waiting for window to close before settling...")
        time.sleep(remaining + 5)

    print(f"[settle] settling job #{job_id}...")
    result = await job_ops.settle(job_id=job_id)
    print(f"[settle] COMPLETED tx: {result['transactionHash']}")
    print("[settle] Payment released to provider.")
    print(f"[settle] Job #{job_id} is now COMPLETED on-chain.")


if __name__ == "__main__":
    asyncio.run(main())
