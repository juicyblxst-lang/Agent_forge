"""
01_setup_funds.py — Claim testnet $U and pre-approve the escrow contract.

Run ONCE per wallet before any client or provider operation.
The $U faucet pays 10 $U per address every 30 minutes.

Source for faucet address: https://docs.altana.network/concepts/networks/testnet
Source for U token address: https://docs.altana.network/concepts/networks/testnet
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

RPC_URL = os.getenv("RPC_URL", "https://bsc-testnet-rpc.publicnode.com")
U_TOKEN = Web3.to_checksum_address(os.getenv("U_TOKEN_ADDRESS", "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565"))
U_FAUCET = Web3.to_checksum_address(os.getenv("U_FAUCET_ADDRESS", "0x86e9197CC0F76E4e4aaa7082180945196bBAb5D3"))
COMMERCE = Web3.to_checksum_address("0xa206c0517b6371c6638cd9e4a42cc9f02a33b0de")

MAX_UINT256 = 2**256 - 1

ERC20_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view", "inputs": [{"name": "account", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "approve", "type": "function", "stateMutability": "nonpayable", "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "outputs": [{"type": "bool"}]},
    {"name": "allowance", "type": "function", "stateMutability": "view", "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
]

FAUCET_ABI = [
    {"name": "requestTokens", "type": "function", "stateMutability": "nonpayable", "inputs": [], "outputs": []},
    {"name": "allowedToWithdraw", "type": "function", "stateMutability": "view", "inputs": [{"name": "user", "type": "address"}], "outputs": [{"type": "bool"}]},
]


def setup_wallet(role: str, private_key: str) -> None:
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    acct = Account.from_key(private_key)
    address = acct.address

    token = w3.eth.contract(address=U_TOKEN, abi=ERC20_ABI)
    faucet = w3.eth.contract(address=U_FAUCET, abi=FAUCET_ABI)
    dec = token.functions.decimals().call()
    one_u = 10 ** dec

    print(f"\n[{role}] wallet: {address}")

    bnb_bal = w3.eth.get_balance(address)
    print(f"[{role}] BNB balance: {w3.from_wei(bnb_bal, 'ether'):.6f} tBNB")
    if bnb_bal < w3.to_wei(0.01, "ether"):
        print(f"[{role}] ⚠ LOW GAS — get tBNB from https://testnet.bnbchain.org/faucet-smart")

    u_bal = token.functions.balanceOf(address).call()
    print(f"[{role}] $U balance: {u_bal / one_u:.4f} $U")

    if u_bal < 5 * one_u:
        can_claim = faucet.functions.allowedToWithdraw(address).call()
        if can_claim:
            print(f"[{role}] claiming 10 $U from faucet...")
            nonce = w3.eth.get_transaction_count(address)
            tx = faucet.functions.requestTokens().build_transaction({
                "from": address,
                "nonce": nonce,
                "gas": 100_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = acct.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            if receipt.status == 1:
                u_bal = token.functions.balanceOf(address).call()
                print(f"[{role}] ✓ claimed — new $U balance: {u_bal / one_u:.4f} $U tx: {tx_hash.hex()}")
            else:
                print(f"[{role}] ✗ faucet claim failed: {tx_hash.hex()}")
        else:
            print(f"[{role}] faucet on cooldown (30-min window). Try again later.")
    else:
        print(f"[{role}] $U balance sufficient, skipping faucet claim")

    allowance = token.functions.allowance(address, COMMERCE).call()
    print(f"[{role}] current allowance for Commerce: {allowance / one_u:.4f} $U")

    if allowance < 100 * one_u:
        print(f"[{role}] approving Commerce contract for MAX_UINT256...")
        nonce = w3.eth.get_transaction_count(address)
        tx = token.functions.approve(COMMERCE, MAX_UINT256).build_transaction({
            "from": address,
            "nonce": nonce,
            "gas": 80_000,
            "gasPrice": w3.eth.gas_price,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status == 1:
            print(f"[{role}] ✓ approved — tx: {tx_hash.hex()}")
        else:
            print(f"[{role}] ✗ approve failed: {tx_hash.hex()}")
    else:
        print(f"[{role}] ✓ allowance already sufficient")


if __name__ == "__main__":
    provider_key = os.getenv("PROVIDER_PRIVATE_KEY")
    client_key = os.getenv("CLIENT_PRIVATE_KEY")

    if not provider_key or not client_key:
        print("Set PROVIDER_PRIVATE_KEY and CLIENT_PRIVATE_KEY in .env")
        sys.exit(1)

    setup_wallet("PROVIDER", provider_key)
    setup_wallet("CLIENT", client_key)
    print("\n✓ Both wallets funded and approved. Ready to proceed.")
