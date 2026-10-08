"""Lab 7 solution: the Paper Archive, a paywalled web API using x402.

  GET /catalog          free   list of papers with price
  GET /open/{id}        free   full text of open-access papers
  GET /fulltext/{id}    $0.02  full text of any paper, paid with x402

No accounts, no API keys, no checkout page: the price is announced in an HTTP 402
response and paid by the client in the retry. That is the whole of x402.

Start the Mock Bank first (services/mock_bank.py), then:
    uv run python solutions/lab07/paper_archive.py
"""

import json

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from x402.http import PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig

from common.config import ARCHIVE_URL, LIBRARY_DIR, NETWORK, PAY_TO_ADDRESS, port_of
from common.x402_kit import x402_resource_server

if not PAY_TO_ADDRESS:
    raise SystemExit("PAY_TO_ADDRESS is empty. Run: uv run python scripts/make_wallet.py")

PAPERS = {p["id"]: p for p in json.loads((LIBRARY_DIR / "papers.json").read_text(encoding="utf-8"))["papers"]}

app = FastAPI(title="Paper Archive")

# 1. Price list: which routes cost money, how much, paid to whom, on which network.
routes = {
    "GET /fulltext/*": RouteConfig(
        accepts=[PaymentOption(scheme="exact", pay_to=PAY_TO_ADDRESS, price="$0.02", network=NETWORK)],
        mime_type="application/json",
        description="Full text of one research paper",
    ),
}

# 2. The middleware answers 402 to unpaid requests and asks the facilitator
#    (the Mock Bank, or x402.org on testnet) to verify and settle paid ones.
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=x402_resource_server())


@app.get("/catalog")
def catalog() -> list[dict]:
    return [
        {"id": p["id"], "title": p["title"], "open_access": p["open_access"], "price_usd": 0 if p["open_access"] else 0.02}
        for p in PAPERS.values()
    ]


@app.get("/open/{paper_id}")
def open_access(paper_id: str) -> dict:
    p = PAPERS.get(paper_id)
    if not p:
        raise HTTPException(404, "No such paper")
    if not p["open_access"]:
        raise HTTPException(403, "Not open access. Use /fulltext/{id} (paid).")
    return {"id": p["id"], "title": p["title"], "full_text": p["full_text"]}


@app.get("/fulltext/{paper_id}")
def full_text(paper_id: str, request: Request) -> dict:
    # Only reached after the middleware verified the payment.
    p = PAPERS.get(paper_id)
    if not p:
        raise HTTPException(404, "No such paper")
    payer = request.state.payment_payload.payload["authorization"]["from"]
    print(f"[archive] sold {paper_id} to {payer}", flush=True)
    return {"id": p["id"], "title": p["title"], "full_text": p["full_text"], "licensed_to": payer}


if __name__ == "__main__":
    print(f"[archive] Paper Archive on {ARCHIVE_URL}  (seller wallet {PAY_TO_ADDRESS})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port_of(ARCHIVE_URL), log_level="info")
