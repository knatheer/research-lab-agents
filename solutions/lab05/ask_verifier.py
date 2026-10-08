"""Lab 5 solution: an A2A client written with the raw a2a-sdk.

1. Discover the Verifier by fetching its Agent Card.
2. Send it a message with a data part (the claim).
3. Read the finished Task and its Artifact.

Run (with verifier_agent.py running):
    uv run python solutions/lab05/ask_verifier.py            # naive claim on raw data
    uv run python solutions/lab05/ask_verifier.py --clean    # claim on cleaned data
"""

import asyncio
import json
import sys

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_data_parts, get_text_parts, new_data_part, new_message, new_text_part
from a2a.types import Role, SendMessageRequest, TaskState
from google.protobuf.json_format import MessageToDict
from mcp import Client

from common.agent_loop import stdio_server
from common.config import VERIFIER_URL


async def make_claim(dataset: str) -> dict:
    """Produce a claim the same way the Experimenter would: run compare_groups via MCP."""
    async with Client(stdio_server("solutions/lab02/instruments_server.py")) as mcp:
        if dataset.endswith("_clean"):
            qa = (await mcp.call_tool("check_data_quality", {"dataset": "nitrogrow_trial"})).structured_content
            ids = [v["id"] for v in qa["implausible_values"]]
            await mcp.call_tool("clean_dataset", {"dataset": "nitrogrow_trial", "drop_ids": ids})
        return (await mcp.call_tool("compare_groups", {"dataset": dataset})).structured_content


async def main(dataset: str) -> None:
    async with httpx.AsyncClient(timeout=300) as http:
        # 1. Discovery
        card = await A2ACardResolver(httpx_client=http, base_url=VERIFIER_URL).get_agent_card()
        print("=== AGENT CARD ===")
        print(json.dumps(MessageToDict(card), indent=2))

        # 2. Build the message: a text part and a data part
        claim = await make_claim(dataset)
        print("\n=== CLAIM ===\n", json.dumps(claim, indent=2))
        message = new_message(
            [new_text_part(text="Please verify this result."), new_data_part({"claim": claim})],
            role=Role.ROLE_USER,
        )

        # 3. Send and read the Task
        client = await create_client(agent=card, client_config=ClientConfig(streaming=False, httpx_client=http))
        async for chunk in client.send_message(SendMessageRequest(message=message)):
            task = chunk.task
            print(f"\n=== TASK {task.id} -> {TaskState.Name(task.status.state)} ===")
            for artifact in task.artifacts:
                print(f"Artifact '{artifact.name}':")
                print("  text:", " ".join(get_text_parts(artifact.parts)))
                print("  data:", json.dumps(get_data_parts(artifact.parts), indent=2))
        await client.close()


if __name__ == "__main__":
    asyncio.run(main("nitrogrow_trial_clean" if "--clean" in sys.argv else "nitrogrow_trial"))
