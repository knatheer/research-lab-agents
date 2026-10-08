"""Lab 6 solution: the Writer, an A2A agent that drafts and revises manuscripts.

Uses two MCP servers:
  * Lab Instruments, only for its 'manuscript_draft' PROMPT (a reusable template)
  * Library, for its TOOLS (search_papers, get_abstract, and in Lab 7 get_full_text)

Input data: {"results": ..., "verification": ..., "reviews": [...]?, "previous_manuscript": "..."?}
Output    : text = manuscript (Markdown); data = {"title", "path", "version", "cited"}

Run:  uv run python solutions/lab06/writer_agent.py   (the Library server must be running)
"""

import json
import re

from mcp import Client

from common.a2a_kit import AgentReply, build_card, serve_agent
from common.agent_loop import MCPToolbox, run_agent, stdio_server
from common.config import LIBRARY_MCP_URL, OUTPUTS_DIR, WRITER_URL

SYSTEM = """You are the Writer in a research lab. You write the lab's manuscripts.
Use the library tools to find and read related work before writing. Cite papers as [LIB-xxx].
Use ONLY numbers from the verified results. Reply with the full manuscript in Markdown and nothing else."""

version = 0


async def handle(text: str, data: dict) -> AgentReply:
    global version
    # 1. Fetch the manuscript template (an MCP prompt) from the Lab Instruments server.
    async with Client(stdio_server("solutions/lab02/instruments_server.py")) as instruments:
        prompt = await instruments.get_prompt(
            "manuscript_draft",
            {
                "results_json": json.dumps(data.get("results", {}), indent=2),
                "verification_json": json.dumps(data.get("verification", {}), indent=2),
            },
        )
    task = prompt.messages[0].content.text

    # 2. Revision mode: add the reviewers' comments and the previous draft.
    if data.get("reviews"):
        task += (
            "\n\nThis is a REVISION. Revise the previous manuscript to address every reviewer comment. "
            f"\nREVIEWS:\n{json.dumps(data['reviews'], indent=2)}"
            f"\nPREVIOUS MANUSCRIPT:\n{data.get('previous_manuscript', '')}"
        )
    if text:
        task += f"\n\nNOTE FROM THE PI: {text}"

    # 3. Write, with the library's tools available.
    async with MCPToolbox({"library": LIBRARY_MCP_URL}) as tb:
        manuscript = await run_agent(SYSTEM, task, tb, name="writer", max_turns=20)

    version += 1
    path = OUTPUTS_DIR / f"manuscript_v{version}.md"
    path.write_text(manuscript, encoding="utf-8")
    title = next((ln.lstrip("# ").strip() for ln in manuscript.splitlines() if ln.startswith("# ")), "Untitled")
    cited = sorted(set(re.findall(r"LIB-\d{3}", manuscript)))
    print(f"[writer] saved {path.name} ({len(manuscript.split())} words, cites {cited})", flush=True)
    return AgentReply(text=manuscript, data={"title": title, "path": str(path), "version": version, "cited": cited})


card = build_card(
    name="Writer",
    description="Drafts and revises research manuscripts from verified results, with literature from the Library.",
    url=WRITER_URL,
    skills=[
        {
            "id": "write_manuscript",
            "name": "Write or revise a manuscript",
            "description": 'Data part: {"results", "verification"} for a first draft; add {"reviews", "previous_manuscript"} to revise.',
            "tags": ["writing", "manuscript"],
            "examples": ["Write the manuscript for these verified results."],
        }
    ],
)

if __name__ == "__main__":
    serve_agent(card, handle)
