"""A thin wrapper over the a2a-sdk, written after Lab 5.

In Lab 5 you write an A2A server and client "by hand" with the raw SDK.
This module packages exactly that code so Labs 6 to 8 stay short:

    serve_agent(card, handler)          -> run an A2A server for an async handler
    await ask_agent(url, text, data)    -> send a message, wait, get AgentReply back
    await discover(url)                 -> fetch an Agent Card

A handler is: async def handler(text: str, data: dict) -> AgentReply
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx
import uvicorn
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import (
    get_data_parts,
    get_message_text,
    get_text_parts,
    new_data_part,
    new_message,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Role,
    SendMessageRequest,
    TaskState,
)
from starlette.applications import Starlette


@dataclass
class AgentReply:
    text: str
    data: dict = field(default_factory=dict)


Handler = Callable[[str, dict], Awaitable[AgentReply]]


# ---------------------------------------------------------------- server side
def build_card(
    name: str,
    description: str,
    url: str,
    skills: list[dict],
    version: str = "1.0.0",
) -> AgentCard:
    """skills: [{"id": ..., "name": ..., "description": ..., "tags": [...], "examples": [...]}]"""
    return AgentCard(
        name=name,
        description=description,
        version=version,
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=url, protocol_version="1.0")],
        skills=[AgentSkill(**s) for s in skills],
    )


class HandlerExecutor(AgentExecutor):
    """Turns a plain async handler into an A2A AgentExecutor."""

    def __init__(self, handler: Handler, agent_name: str) -> None:
        self.handler = handler
        self.agent_name = agent_name

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        await updater.update_status(TaskState.TASK_STATE_WORKING, message=new_text_message("Working on it..."))

        text = get_message_text(context.message) or ""
        data_parts = get_data_parts(context.message.parts)
        data = data_parts[0] if data_parts and isinstance(data_parts[0], dict) else {}
        print(f"[{self.agent_name}] task {task.id[:8]} received: {text[:120]!r}", flush=True)

        try:
            reply = await self.handler(text, data)
        except Exception as exc:  # report failures to the caller instead of hanging
            traceback.print_exc()
            await updater.update_status(
                TaskState.TASK_STATE_FAILED, message=new_text_message(f"{type(exc).__name__}: {exc}")
            )
            return

        parts = [new_text_part(text=reply.text, media_type="text/plain")]
        if reply.data:
            parts.append(new_data_part(reply.data, media_type="application/json"))
        await updater.add_artifact(parts=parts, name="result")
        await updater.update_status(TaskState.TASK_STATE_COMPLETED, message=new_text_message("Done."))
        print(f"[{self.agent_name}] task {task.id[:8]} completed", flush=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel is not supported")


def build_app(card: AgentCard, handler: Handler) -> Starlette:
    request_handler = DefaultRequestHandler(
        agent_executor=HandlerExecutor(handler, card.name),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(request_handler, "/")
    return Starlette(routes=routes)


def serve_agent(card: AgentCard, handler: Handler, host: str = "127.0.0.1") -> None:
    url = card.supported_interfaces[0].url
    port = int(url.rstrip("/").rsplit(":", 1)[1])
    print(f"[{card.name}] A2A server on {url}  (card: {url}/.well-known/agent-card.json)", flush=True)
    uvicorn.run(build_app(card, handler), host=host, port=port, log_level="warning")


# ---------------------------------------------------------------- client side
async def discover(url: str) -> AgentCard:
    async with httpx.AsyncClient(timeout=10) as http:
        return await A2ACardResolver(httpx_client=http, base_url=url).get_agent_card()


async def ask_agent(url: str, text: str, data: dict | None = None, timeout: float = 600) -> AgentReply:
    """Send one message to an A2A agent and wait for the finished task."""
    card = await discover(url)
    http = httpx.AsyncClient(timeout=timeout)
    client = await create_client(agent=card, client_config=ClientConfig(streaming=False, httpx_client=http))
    parts = [new_text_part(text=text or "See the attached data part.")]
    if data:
        parts.append(new_data_part(data))
    message = new_message(parts, role=Role.ROLE_USER)

    reply = AgentReply(text="")
    try:
        async for chunk in client.send_message(SendMessageRequest(message=message)):
            if not chunk.HasField("task"):
                if chunk.HasField("message"):
                    reply.text = get_message_text(chunk.message) or ""
                continue
            task = chunk.task
            if task.status.state == TaskState.TASK_STATE_FAILED:
                raise RuntimeError(f"{card.name} failed: {get_message_text(task.status.message)}")
            for artifact in task.artifacts:
                reply.text = "\n".join(get_text_parts(artifact.parts))
                found = get_data_parts(artifact.parts)
                if found and isinstance(found[0], dict):
                    reply.data = _ints(dict(found[0]))
    finally:
        await client.close()
        await http.aclose()
    return reply



def _ints(value: Any) -> Any:
    """A2A data parts travel as protobuf Struct, where every number is a float.
    Turn whole-number floats back into ints (55.0 -> 55) so results read naturally."""
    if isinstance(value, dict):
        return {k: _ints(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_ints(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value
