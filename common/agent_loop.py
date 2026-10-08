"""The agent loop you build in Lab 3, packaged for reuse in later labs.

Two pieces:
  * MCPToolbox: connects to one or more MCP servers, lists their tools in
    OpenAI format, and routes tool calls to the right server.
  * run_agent(): the classic tool-calling loop. Ask the model, run the tools it
    asks for, feed results back, repeat until it answers in plain text.
"""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters
from openai import AsyncOpenAI

from common.config import MODEL, ROOT


def stdio_server(script: str | Path) -> StdioServerParameters:
    """Describe a local MCP server that runs as a subprocess over stdio."""
    path = Path(script)
    if not path.is_absolute():
        path = ROOT / path
    return StdioServerParameters(command=sys.executable, args=[str(path)], cwd=str(ROOT))


def mcp_tool_to_openai(tool: Any) -> dict:
    """Convert an MCP Tool into the 'tools' format of the OpenAI Chat Completions API."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def tool_result_to_text(result: Any, limit: int = 8000) -> str:
    """Flatten an MCP CallToolResult into a string the LLM can read."""
    if result.structured_content is not None:
        text = json.dumps(result.structured_content, indent=2, default=str)
    else:
        text = "\n".join(getattr(c, "text", str(c)) for c in result.content)
    if result.is_error:
        text = "TOOL ERROR: " + text
    return text[:limit]


@dataclass
class ToolCallRecord:
    server: str
    name: str
    arguments: dict
    output: str
    structured: Any = None


@dataclass
class MCPToolbox:
    """Async context manager holding live connections to several MCP servers.

    Example:
        async with MCPToolbox({"instruments": stdio_server("solutions/lab02/instruments_server.py")}) as tb:
            print(tb.openai_tools())
            print(await tb.call("list_datasets", {}))
    """

    servers: dict[str, Any]
    clients: dict[str, Client] = field(default_factory=dict)
    routes: dict[str, str] = field(default_factory=dict)  # tool name -> server name
    tools: list[Any] = field(default_factory=list)
    history: list[ToolCallRecord] = field(default_factory=list)

    async def __aenter__(self) -> "MCPToolbox":
        self._stack = AsyncExitStack()
        for name, target in self.servers.items():
            client = await self._stack.enter_async_context(Client(target))
            self.clients[name] = client
            listed = await client.list_tools()
            for tool in listed.tools:
                if tool.name in self.routes:
                    raise ValueError(f"Tool name clash: {tool.name} exists on two servers")
                self.routes[tool.name] = name
                self.tools.append(tool)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()

    def openai_tools(self) -> list[dict]:
        return [mcp_tool_to_openai(t) for t in self.tools]

    async def call(self, name: str, arguments: dict) -> str:
        server = self.routes.get(name)
        if server is None:
            return f"TOOL ERROR: unknown tool {name}"
        result = await self.clients[server].call_tool(name, arguments)
        text = tool_result_to_text(result)
        self.history.append(ToolCallRecord(server, name, arguments, text, result.structured_content))
        return text

    def last_result(self, tool_name: str) -> Any:
        """Structured output of the most recent successful call to tool_name, or None."""
        for rec in reversed(self.history):
            if rec.name == tool_name and not rec.output.startswith("TOOL ERROR"):
                return rec.structured
        return None


def _log(verbose: bool, msg: str) -> None:
    if verbose:
        print(msg, flush=True)


async def run_agent(
    system: str,
    task: str,
    toolbox: MCPToolbox | None = None,
    *,
    model: str | None = None,
    max_turns: int = 15,
    verbose: bool = True,
    name: str = "agent",
) -> str:
    """Run the tool-calling loop until the model replies without tool calls."""
    llm = AsyncOpenAI()
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
    tools = toolbox.openai_tools() if toolbox else None

    for turn in range(1, max_turns + 1):
        kwargs: dict[str, Any] = {"model": model or MODEL, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = await llm.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if not msg.tool_calls:
            _log(verbose, f"[{name}] done after {turn} turn(s)")
            return msg.content or ""

        # Keep the assistant's tool-call message in the history (required by the API).
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            _log(verbose, f"[{name}] -> {call.function.name}({json.dumps(args)[:200]})")
            output = await toolbox.call(call.function.name, args) if toolbox else "no tools"
            _log(verbose, f"[{name}] <- {output[:200].replace(chr(10), ' ')}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

    return "Stopped: reached max_turns without a final answer."
