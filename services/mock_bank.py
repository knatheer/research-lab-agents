"""Mock Bank: a local x402 facilitator for the classroom. No blockchain, no real money.

A facilitator is the party a seller asks "is this payment valid?" (/verify) and
"please execute it" (/settle). On a real network the facilitator submits the
signed USDC authorization to the blockchain. This mock does every check a real
facilitator does, but settles in an in-memory ledger instead of on-chain:

  * EIP-712 signature recovers to the payer address (real cryptography)
  * pays the right seller, the right amount, the right token, on the right network
  * authorization is inside its validity window
  * nonce not used before (replay protection)
  * payer has enough balance

Every new wallet starts with 5.00 mock USDC. Open http://127.0.0.1:4022 to watch the ledger.

Run:  uv run python services/mock_bank.py
To use the real Base Sepolia testnet instead, set FACILITATOR_URL=https://x402.org/facilitator
in the SELLER's .env. The buyer code does not change.
"""

import secrets
import time
from datetime import datetime

import uvicorn
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from common.config import FACILITATOR_URL, NETWORK, port_of

USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
START_BALANCE = 5_000_000  # 5.00 USDC in atomic units (6 decimals)

app = FastAPI(title="Mock Bank (x402 facilitator)")
balances: dict[str, int] = {}
used_nonces: set[str] = set()
transactions: list[dict] = []


def usd(atomic: int) -> str:
    return f"{atomic / 1_000_000:.2f}"


def _balance(addr: str) -> int:
    return balances.setdefault(addr.lower(), START_BALANCE)


def _check(body: dict) -> tuple[bool, str, str, int]:
    """Return (ok, reason, payer, amount)."""
    payload, req = body["paymentPayload"], body["paymentRequirements"]
    auth = payload["payload"]["authorization"]
    payer = auth["from"]
    value = int(auth["value"])
    now = int(time.time())

    if req.get("scheme") != "exact" or req.get("network") != NETWORK:
        return False, "unsupported_scheme_or_network", payer, value
    if req["asset"].lower() != USDC_BASE_SEPOLIA.lower():
        return False, "wrong_asset", payer, value

    typed = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": req["extra"]["name"],
            "version": req["extra"]["version"],
            "chainId": int(req["network"].split(":")[1]),
            "verifyingContract": req["asset"],
        },
        "message": {
            "from": auth["from"],
            "to": auth["to"],
            "value": value,
            "validAfter": int(auth["validAfter"]),
            "validBefore": int(auth["validBefore"]),
            "nonce": auth["nonce"],
        },
    }
    try:
        signer = Account.recover_message(encode_typed_data(full_message=typed), signature=payload["payload"]["signature"])
    except Exception:
        return False, "invalid_signature", payer, value
    if signer.lower() != payer.lower():
        return False, "invalid_signature", payer, value
    if auth["to"].lower() != req["payTo"].lower():
        return False, "wrong_recipient", payer, value
    if value < int(req["amount"]):
        return False, "insufficient_amount", payer, value
    if not int(auth["validAfter"]) <= now < int(auth["validBefore"]):
        return False, "authorization_expired", payer, value
    if auth["nonce"] in used_nonces:
        return False, "nonce_already_used (replay)", payer, value
    if _balance(payer) < value:
        return False, "insufficient_funds", payer, value
    return True, "", payer, value


@app.get("/supported")
def supported() -> dict:
    return {"kinds": [{"x402Version": 2, "scheme": "exact", "network": NETWORK}], "extensions": [], "signers": {}}


@app.post("/verify")
def verify(body: dict) -> dict:
    ok, reason, payer, value = _check(body)
    print(f"[bank] verify {payer[:10]}... {usd(value)} USDC -> {'OK' if ok else reason}", flush=True)
    return {"isValid": True, "payer": payer} if ok else {"isValid": False, "invalidReason": reason, "payer": payer}


@app.post("/settle")
def settle(body: dict) -> dict:
    ok, reason, payer, value = _check(body)
    req = body["paymentRequirements"]
    if not ok:
        print(f"[bank] settle REFUSED: {reason}", flush=True)
        return {"success": False, "errorReason": reason, "transaction": "", "network": req["network"], "payer": payer}
    auth = body["paymentPayload"]["payload"]["authorization"]
    used_nonces.add(auth["nonce"])
    balances[payer.lower()] = _balance(payer) - value
    seller = req["payTo"].lower()
    balances[seller] = balances.get(seller, 0) + value  # sellers start at 0
    tx = "0x" + secrets.token_hex(32)
    resource = (body["paymentPayload"].get("resource") or {}).get("url", "")
    transactions.append(
        {"time": datetime.now().strftime("%H:%M:%S"), "from": payer, "to": req["payTo"], "usdc": usd(value), "tx": tx, "resource": resource}
    )
    print(f"[bank] SETTLED {usd(value)} USDC {payer[:10]}... -> {req['payTo'][:10]}...  tx {tx[:12]}...", flush=True)
    return {"success": True, "transaction": tx, "network": req["network"], "payer": payer}


@app.get("/ledger")
def ledger() -> dict:
    return {"balances": {a: usd(b) for a, b in balances.items()}, "transactions": transactions}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    rows = "".join(
        f"<tr><td>{t['time']}</td><td>{t['from'][:10]}...</td><td>{t['to'][:10]}...</td>"
        f"<td>{t['usdc']}</td><td>{t['resource']}</td><td><code>{t['tx'][:14]}...</code></td></tr>"
        for t in reversed(transactions)
    )
    bals = "".join(f"<tr><td><code>{a}</code></td><td>{usd(b)}</td></tr>" for a, b in balances.items())
    return f"""<html><head><meta http-equiv="refresh" content="3"><title>Mock Bank</title>
<style>body{{font-family:system-ui;margin:24px}}td,th{{padding:4px 10px;border-bottom:1px solid #ddd}}</style></head>
<body><h1>Mock Bank: x402 ledger (mock USDC)</h1>
<h2>Transactions</h2><table><tr><th>Time</th><th>From</th><th>To</th><th>USDC</th><th>Resource</th><th>Tx</th></tr>{rows}</table>
<h2>Balances</h2><table><tr><th>Wallet</th><th>USDC</th></tr>{bals}</table></body></html>"""


if __name__ == "__main__":
    import os

    host = os.getenv("BANK_HOST", "127.0.0.1")
    port = port_of(FACILITATOR_URL) if "127.0.0.1" in FACILITATOR_URL or "localhost" in FACILITATOR_URL else 4022
    print(f"[bank] Mock Bank on http://{host}:{port}  (ledger page: http://127.0.0.1:{port})", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")
