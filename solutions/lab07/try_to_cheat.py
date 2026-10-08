"""Lab 7 solution (security exercise): try to cheat the paywall, and watch it fail.

We do the x402 steps by hand so we can tamper with them:
  1. Get the 402 and sign one valid payment.
  2. Use it once                      -> 200 (paid)
  3. Replay the same signed payment   -> rejected: nonce already used
  4. Pay a different paper with it    -> rejected: the nonce is already spent.
     (The signature covers payer, recipient, amount, validity window and nonce. Not the URL.)
  5. Forge the 'from' address         -> rejected: signature does not match

Run (Mock Bank and Paper Archive running):
    uv run python solutions/lab07/try_to_cheat.py
"""

import asyncio
import base64
import copy
import json

import httpx
from x402.http import x402HTTPClient

from common.config import ARCHIVE_URL
from common.x402_kit import decode_header, make_x402_client


def show(label: str, r: httpx.Response) -> None:
    detail = decode_header(r.headers.get("PAYMENT-REQUIRED")).get("error", "")
    print(f"{label:<38} -> HTTP {r.status_code} {detail}")


async def main() -> None:
    client = make_x402_client("$0.05")
    helper = x402HTTPClient(client)
    url = f"{ARCHIVE_URL}/fulltext/LIB-005"

    async with httpx.AsyncClient() as http:
        # 1. Ask, receive 402, sign ONE payment.
        r = await http.get(url)
        required = helper.get_payment_required_response(lambda n: r.headers.get(n))
        payload = await client.create_payment_payload(required)
        headers = helper.encode_payment_signature_header(payload)

        show("2. honest payment", await http.get(url, headers=headers))
        show("3. replay the same payment", await http.get(url, headers=headers))
        show("4. reuse it for another paper", await http.get(f"{ARCHIVE_URL}/fulltext/LIB-009", headers=headers))

        # 5. Forge: claim the money comes from someone else's wallet.
        name = next(iter(headers))
        forged = json.loads(base64.b64decode(headers[name]))
        forged = copy.deepcopy(forged)
        forged["payload"]["authorization"]["from"] = "0x000000000000000000000000000000000000bEEF"
        forged_header = {name: base64.b64encode(json.dumps(forged).encode()).decode()}
        show("5. forged 'from' address", await http.get(url, headers=forged_header))


if __name__ == "__main__":
    asyncio.run(main())
