"""Lab 7 solution: the Library MCP server, now able to BUY full texts with x402.

New in Lab 7: the get_full_text tool. Open-access papers are fetched for free;
others are bought from the Paper Archive with x402, within a session budget.
The agent never sees the wallet. The MCP server holds it and enforces the budget.

From Lab 4:

Unlike Lab Instruments (a subprocess over stdio), this server is a long-running
web service. Many agents can share it at http://127.0.0.1:8001/mcp

Run:  uv run python solutions/lab07/library_server.py
"""

import json
import os
import re
from typing import Any

import httpx
from mcp.server import MCPServer

from common.config import ARCHIVE_URL, LIBRARY_DIR, LIBRARY_MCP_URL, port_of
from common.x402_kit import paying_http_client, settlement_of

mcp = MCPServer("Library", instructions="Search the lab's literature corpus. Cite papers by their id, e.g. [LIB-003].")

PAPERS = {p["id"]: p for p in json.loads((LIBRARY_DIR / "papers.json").read_text(encoding="utf-8"))["papers"]}


def _brief(p: dict) -> dict[str, Any]:
    return {
        "id": p["id"],
        "title": p["title"],
        "authors": p["authors"],
        "year": p["year"],
        "open_access": p["open_access"],
    }


@mcp.tool()
def search_papers(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Keyword search over titles and abstracts. Returns the best matches, best first."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    scored = []
    for p in PAPERS.values():
        text = (p["title"] + " " + p["abstract"]).lower()
        score = sum(text.count(w) for w in words)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [_brief(p) for _, p in scored[:max_results]]


@mcp.tool()
def get_abstract(paper_id: str) -> dict[str, Any]:
    """Return the abstract of one paper (free for every paper)."""
    p = PAPERS.get(paper_id)
    if not p:
        raise ValueError(f"No paper {paper_id}")
    return _brief(p) | {"venue": p["venue"], "abstract": p["abstract"]}


BUDGET_USD = float(os.getenv("LIBRARY_BUDGET_USD", "0.10"))
spent_usd = 0.0
purchases: dict[str, dict] = {}  # paper_id -> full text, so we never pay twice


@mcp.tool()
async def get_full_text(paper_id: str) -> dict[str, Any]:
    """Full text of a paper. Open-access papers are free. Others cost 0.02 USD, paid
    automatically with x402 from the lab's wallet, within the session budget."""
    global spent_usd
    p = PAPERS.get(paper_id)
    if not p:
        raise ValueError(f"No paper {paper_id}")
    if paper_id in purchases:
        return purchases[paper_id] | {"paid_usd": 0.0, "note": "already purchased"}

    if p["open_access"]:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(f"{ARCHIVE_URL}/open/{paper_id}")
        r.raise_for_status()
        return {"id": paper_id, "full_text": r.json()["full_text"], "paid_usd": 0.0}

    price = p["price_usd"]
    if spent_usd + price > BUDGET_USD + 1e-9:
        raise ValueError(f"Budget exceeded: spent {spent_usd:.2f} of {BUDGET_USD:.2f} USD. Use get_abstract instead.")

    async with paying_http_client(max_payment="$0.05") as http:
        r = await http.get(f"{ARCHIVE_URL}/fulltext/{paper_id}")
    if r.status_code != 200:
        raise ValueError(f"Purchase failed: HTTP {r.status_code} {r.text[:200]}")
    receipt = settlement_of(r)
    spent_usd += price
    result = {
        "id": paper_id,
        "full_text": r.json()["full_text"],
        "paid_usd": price,
        "transaction": receipt.get("transaction"),
        "budget_left_usd": round(BUDGET_USD - spent_usd, 2),
    }
    purchases[paper_id] = {"id": paper_id, "full_text": result["full_text"]}
    print(f"[library] bought {paper_id} for {price} USD, tx {result['transaction']}", flush=True)
    return result


@mcp.resource("library://papers/{paper_id}/citation", mime_type="text/plain")
def citation(paper_id: str) -> str:
    """APA-style citation for a paper."""
    p = PAPERS[paper_id]
    return f"{', '.join(p['authors'])} ({p['year']}). {p['title']}. {p['venue']}."


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=port_of(LIBRARY_MCP_URL.removesuffix("/mcp")))
