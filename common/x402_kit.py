"""x402 helpers used from Lab 7 onward.

Buyer side:   paying_http_client()  -> httpx client that pays 402 responses automatically
Seller side:  x402_resource_server() -> x402 server object for the FastAPI middleware
Teaching:     decode_header()        -> base64 header to dict, to look inside the protocol
"""

from __future__ import annotations

import base64
import json

from eth_account import Account
from x402 import x402Client
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, x402HTTPClient
from x402.http.clients import x402HttpxClient
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.mechanisms.evm.exact.register import register_exact_evm_client
from x402.server import x402ResourceServer

from common.config import FACILITATOR_URL, MAX_PAYMENT_USD, NETWORK, PAYER_PRIVATE_KEY


def decode_header(value: str | None) -> dict:
    """x402 v2 headers (PAYMENT-REQUIRED, PAYMENT-SIGNATURE, PAYMENT-RESPONSE) are base64 JSON."""
    if not value:
        return {}
    return json.loads(base64.b64decode(value))


# ---------------------------------------------------------------- buyer side
def payer_account():
    if not PAYER_PRIVATE_KEY:
        raise RuntimeError("PAYER_PRIVATE_KEY is empty. Run: uv run python scripts/make_wallet.py")
    return Account.from_key(PAYER_PRIVATE_KEY)


def make_x402_client(max_payment: str = MAX_PAYMENT_USD) -> x402Client:
    """An x402 client that signs EVM 'exact' payments, with a per-payment spend cap."""
    client = x402Client().set_spend_controls({"max_amount_per_payment": max_payment})
    register_exact_evm_client(client, EthAccountSigner(payer_account()))
    return client


def paying_http_client(max_payment: str = MAX_PAYMENT_USD, timeout: float = 60) -> x402HttpxClient:
    """Use like httpx.AsyncClient. On HTTP 402 it signs a payment and retries once."""
    return x402HttpxClient(make_x402_client(max_payment), timeout=timeout)


def settlement_of(response) -> dict:
    """Read the PAYMENT-RESPONSE header (who paid, transaction hash). Empty if the call was free."""
    return decode_header(response.headers.get("PAYMENT-RESPONSE"))


# ---------------------------------------------------------------- seller side
def x402_resource_server(facilitator_url: str = FACILITATOR_URL) -> x402ResourceServer:
    """Server-side x402 object. It asks the facilitator to verify and settle payments."""
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url))
    server = x402ResourceServer(facilitator)
    server.register(NETWORK, ExactEvmServerScheme())
    return server


__all__ = [
    "decode_header",
    "payer_account",
    "make_x402_client",
    "paying_http_client",
    "settlement_of",
    "x402_resource_server",
    "x402HTTPClient",
]
