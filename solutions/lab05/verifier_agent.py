"""Lab 5 solution: the Verifier, an A2A agent written with the raw a2a-sdk.

Role: an independent lab that checks the Experimenter's claim BEFORE anything is written up.
  1. Reproduce: re-run the same test on the same dataset and compare the numbers.
  2. Audit: run data-quality checks on the dataset the claim used.
  3. Verdict: "confirmed" or "issues_found", plus a short note written by the LLM.

The checks are deterministic code calling MCP tools. The LLM only writes the prose.
That is a deliberate design choice: verification must not depend on a model's mood.

Run:  uv run python solutions/lab05/verifier_agent.py
Card: http://127.0.0.1:9102/.well-known/agent-card.json
"""

import json

import uvicorn
from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, TaskState
from mcp import Client
from starlette.applications import Starlette

from common.agent_loop import run_agent, stdio_server
from common.config import VERIFIER_URL, port_of

INSTRUMENTS = "solutions/lab02/instruments_server.py"
TOLERANCE = 1e-3


# ---------------------------------------------------------------- 1. the agent's actual work
async def verify_claim(claim: dict) -> tuple[str, dict]:
    dataset = claim.get("dataset", "")
    issues: list[str] = []
    async with Client(stdio_server(INSTRUMENTS)) as mcp:
        # Reproduce
        rerun = (await mcp.call_tool("compare_groups", {"dataset": dataset})).structured_content
        if rerun is None:
            return "Could not re-run the analysis.", {"verdict": "error", "issues": [f"unknown dataset {dataset}"]}
        reproducible = abs(rerun["mean_diff"] - float(claim.get("mean_diff", 1e9))) < TOLERANCE
        if not reproducible:
            issues.append(f"Not reproducible: claimed mean_diff {claim.get('mean_diff')} but re-run gives {rerun['mean_diff']}.")

        # Audit
        qa = (await mcp.call_tool("check_data_quality", {"dataset": dataset})).structured_content
        if qa["duplicate_ids"]:
            issues.append(f"{qa['duplicate_rows_extra']} duplicate rows (plot_id {', '.join(qa['duplicate_ids'])}).")
        if qa["missing_outcome_ids"]:
            issues.append(f"{len(qa['missing_outcome_ids'])} rows with missing yield ({', '.join(qa['missing_outcome_ids'])}).")
        if qa["implausible_values"]:
            vals = ", ".join(f"{v['id']}={v['value']}" for v in qa["implausible_values"])
            issues.append(f"{len(qa['implausible_values'])} implausible yields above 15 t/ha, likely kg/ha unit errors ({vals}).")

    verdict = "confirmed" if not issues else "issues_found"
    data = {
        "verdict": verdict,
        "reproducible": reproducible,
        "dataset_checked": dataset,
        "issues": issues,
        "recommended_action": (
            "None. Results may be written up."
            if verdict == "confirmed"
            else "Apply the protocol exclusion rules with clean_dataset, then re-run compare_groups on the cleaned dataset."
        ),
        "verified_results": rerun if verdict == "confirmed" else None,
    }

    # The LLM writes a short human-readable note. If it fails, we still return the verdict.
    try:
        note = await run_agent(
            "You are a research verifier. Write a 3-sentence verification note for the lab's PI. Be factual.",
            json.dumps(data),
            verbose=False,
        )
    except Exception as exc:  # no key, no network, ...
        note = f"Verdict: {verdict}. Issues: {issues or 'none'}. (LLM note unavailable: {type(exc).__name__})"
    return note, data


# ---------------------------------------------------------------- 2. the A2A executor
class VerifierExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # a) Every request becomes a Task. Create it if the client did not send one.
        task = context.current_task or new_task_from_user_message(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        await updater.update_status(TaskState.TASK_STATE_WORKING, message=new_text_message("Verifying claim..."))

        # b) Read the input. We expect a data part: {"claim": {...compare_groups output...}}
        data_parts = get_data_parts(context.message.parts)
        claim = (data_parts[0] or {}).get("claim") if data_parts else None
        if not claim:
            await updater.update_status(
                TaskState.TASK_STATE_FAILED,
                message=new_text_message('Send a data part like {"claim": <compare_groups output>}'),
            )
            return
        print(f"[verifier] checking claim on dataset {claim.get('dataset')}", flush=True)

        # c) Do the work, publish the result as an Artifact, mark the task completed.
        note, result = await verify_claim(claim)
        await updater.add_artifact(
            parts=[new_text_part(text=note), new_data_part(result, media_type="application/json")],
            name="verification_report",
        )
        await updater.update_status(TaskState.TASK_STATE_COMPLETED, message=new_text_message(f"Verdict: {result['verdict']}"))
        print(f"[verifier] verdict: {result['verdict']}", flush=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------- 3. the Agent Card
card = AgentCard(
    name="Verifier",
    description="Independent verification lab. Re-runs a statistical claim from raw data and audits data quality.",
    version="1.0.0",
    default_input_modes=["application/json"],
    default_output_modes=["text/plain", "application/json"],
    capabilities=AgentCapabilities(streaming=False),
    supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=VERIFIER_URL, protocol_version="1.0")],
    skills=[
        AgentSkill(
            id="verify_result",
            name="Verify a statistical result",
            description='Input: data part {"claim": <compare_groups output>}. Output: verdict, issues, recommended action.',
            tags=["verification", "reproducibility", "data-quality"],
            examples=['{"claim": {"dataset": "nitrogrow_trial", "mean_diff": 0.31}}'],
        )
    ],
)

# ---------------------------------------------------------------- 4. wire it up and serve
if __name__ == "__main__":
    handler = DefaultRequestHandler(agent_executor=VerifierExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/")
    print(f"[verifier] A2A server on {VERIFIER_URL}", flush=True)
    uvicorn.run(Starlette(routes=routes), host="127.0.0.1", port=port_of(VERIFIER_URL), log_level="warning")
