"""Lab 7 solution: buying a paper with x402, step by step.

Part A shows the raw protocol with plain httpx so you can see every header.
Part B does the same purchase with the x402 client in three lines.

Run (Mock Bank and Paper Archive must be running):
    uv run python solutions/lab07/buy_paper.py LIB-003
"""

import asyncio
import json
import sys

import httpx

from common.config import ARCHIVE_URL
from common.x402_kit import decode_header, paying_http_client, payer_account, settlement_of


async def part_a_look_inside(paper_id: str) -> None:
    print("=" * 60 + "\nPART A: ask without paying\n" + "=" * 60)
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{ARCHIVE_URL}/fulltext/{paper_id}")
    print("Status:", r.status_code, r.reason_phrase)
    required = decode_header(r.headers.get("PAYMENT-REQUIRED"))
    print("PAYMENT-REQUIRED header, decoded:")
    print(json.dumps(required, indent=2))
    offer = required["accepts"][0]
    print(f"\nThe seller wants {int(offer['amount']) / 1e6:.2f} USDC on {offer['network']} paid to {offer['payTo']}")


async def part_b_pay(paper_id: str) -> None:
    print("\n" + "=" * 60 + "\nPART B: pay with x402\n" + "=" * 60)
    print("Paying from wallet:", payer_account().address)
    async with paying_http_client(max_payment="$0.05") as http:
        r = await http.get(f"{ARCHIVE_URL}/fulltext/{paper_id}")
    print("Status:", r.status_code)
    body = r.json()
    print("Title:", body["title"])
    print("Text :", body["full_text"][:200], "...")
    print("Settlement (PAYMENT-RESPONSE header):", json.dumps(settlement_of(r), indent=2))


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "LIB-003"
    asyncio.run(part_a_look_inside(pid))
    asyncio.run(part_b_pay(pid))
