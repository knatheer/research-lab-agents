"""Lab 4 solution: one agent, two MCP servers, two transports.

  instruments  -> stdio subprocess (local, private)
  library      -> Streamable HTTP at http://127.0.0.1:8001/mcp (shared service)

Start the library first:  uv run python solutions/lab04/library_server.py
Then:                      uv run python solutions/lab04/literature_experimenter.py
"""

import asyncio
import sys

from common.agent_loop import MCPToolbox, run_agent, stdio_server
from common.config import LIBRARY_MCP_URL

SYSTEM = """You are the Experimenter in a research lab.
Run the analysis with the instrument tools, then search the library for prior work
and say whether your result agrees with it. Cite papers as [LIB-xxx]. Never invent numbers."""


async def main(question: str) -> None:
    servers = {
        "instruments": stdio_server("solutions/lab02/instruments_server.py"),
        "library": LIBRARY_MCP_URL,  # a URL means Streamable HTTP
    }
    async with MCPToolbox(servers) as toolbox:
        print("Tools by server:", toolbox.routes, "\n")
        answer = await run_agent(SYSTEM, question, toolbox, name="experimenter")
        print("\n=== REPORT ===\n" + answer)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or (
        "Follow the study protocol to test whether NitroGrow increases wheat yield "
        "in nitrogrow_trial, then compare the effect size with published studies."
    )
    asyncio.run(main(q))
