"""Lab 4 solution: the Library MCP server, served over Streamable HTTP.

Unlike Lab Instruments (a subprocess over stdio), this server is a long-running
web service. Many agents can share it at http://127.0.0.1:8001/mcp

Run:  uv run python solutions/lab04/library_server.py
"""

import json
import re
from typing import Any

from mcp.server import MCPServer

from common.config import LIBRARY_DIR, LIBRARY_MCP_URL, port_of

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


@mcp.resource("library://papers/{paper_id}/citation", mime_type="text/plain")
def citation(paper_id: str) -> str:
    """APA-style citation for a paper."""
    p = PAPERS[paper_id]
    return f"{', '.join(p['authors'])} ({p['year']}). {p['title']}. {p['venue']}."


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=port_of(LIBRARY_MCP_URL.removesuffix("/mcp")))
