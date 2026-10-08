"""Lab 3 solution: the Experimenter agent.

An MCP *client* (connects to the Lab Instruments server over stdio) plus an
OpenAI tool-calling loop. Everything is in one file on purpose so you can
see every step. Lab 4 onward reuses the same logic from common/agent_loop.py.

Run:  uv run python solutions/lab03/experimenter.py "Does NitroGrow increase wheat yield?"
"""

import asyncio
import json
import sys

from mcp import Client
from openai import AsyncOpenAI

from common.agent_loop import stdio_server
from common.config import MODEL

SERVER = "solutions/lab02/instruments_server.py"

SYSTEM = """You are the Experimenter in a research lab.
You answer research questions by running statistical tools on the lab's datasets.
Use the tools. Never invent numbers. When you are done, give a short report with
the dataset you used, n per group, the mean difference with 95% CI, and the p-value."""


def to_openai_tool(tool) -> dict:
    # Step 3: an MCP tool already has a name, a description and a JSON Schema
    # for its inputs. That is exactly what OpenAI function calling needs.
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


async def main(question: str) -> None:
    llm = AsyncOpenAI()  # reads OPENAI_API_KEY from the environment (.env)

    # Step 1: start the MCP server as a subprocess and connect to it.
    async with Client(stdio_server(SERVER)) as mcp_client:
        # Step 2: discover the tools at runtime. The agent has no hard-coded tool list.
        listed = await mcp_client.list_tools()
        tools = [to_openai_tool(t) for t in listed.tools]
        print(f"Connected. {len(tools)} tools: {[t['function']['name'] for t in tools]}\n")

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ]

        # Step 4: the agent loop.
        for turn in range(1, 16):
            response = await llm.chat.completions.create(model=MODEL, messages=messages, tools=tools)
            msg = response.choices[0].message

            if not msg.tool_calls:  # the model answered in plain text: we are done
                print("\n=== EXPERIMENTER REPORT ===\n")
                print(msg.content)
                return

            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                print(f"[turn {turn}] calling {call.function.name}({args})")

                # Step 5: the MCP call. The LLM decided WHAT to call, MCP does the calling.
                result = await mcp_client.call_tool(call.function.name, args)
                if result.structured_content is not None:
                    output = json.dumps(result.structured_content)
                else:
                    output = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                print(f"          -> {output[:150]}")

                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        print("Stopped after 15 turns without a final answer.")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Does NitroGrow increase wheat yield in the nitrogrow_trial dataset?"
    asyncio.run(main(q))
