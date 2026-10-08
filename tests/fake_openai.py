"""A scripted, OpenAI-compatible Chat Completions server for offline tests.

It is NOT an LLM. It picks tool calls from simple rules based on which tools
are offered, so the real agent code (OpenAI SDK, MCP, A2A, x402) can be tested
end to end without an API key. Point the SDK at it with OPENAI_BASE_URL.
"""

import json
import re
import time
import uuid

from fastapi import FastAPI

app = FastAPI()


def _tool_msg(name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_" + uuid.uuid4().hex[:8], "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }


def _reply(message: dict) -> dict:
    return {
        "id": "chatcmpl-fake", "object": "chat.completion", "created": int(time.time()), "model": "fake",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _tool_outputs(messages: list[dict]) -> list[str]:
    return [m.get("content") or "" for m in messages if m.get("role") == "tool"]


def _manuscript(text: str) -> str:
    diff = re.search(r'"mean_diff":\s*([-0-9.]+)', text)
    p = re.search(r'"p_value":\s*([-0-9.e]+)', text)
    d = diff.group(1) if diff else "0.31"
    pv = p.group(1) if p else "0.0004"
    filler = " ".join(["The verified analysis supports a modest but agronomically relevant yield gain."] * 12)
    return f"""# NitroGrow increases winter wheat yield: a verified multi-site trial

## Abstract
NitroGrow increased mean yield by {d} t/ha (Welch t-test, p = {pv}).

## Introduction
Biostimulants can raise yield [LIB-001]. Data-entry errors are common in field trials [LIB-003].

## Methods
We applied the pre-registered exclusion rules: 4 duplicate rows, 2 missing outcomes and
5 implausible yields (unit errors) were excluded. Primary analysis: Welch two-sample t-test.

## Results
Mean difference {d} t/ha, 95% CI reported in the verified results, p = {pv}, Cohen's d reported.

## Discussion
The effect agrees with [LIB-001]. Limitation: only four sites [LIB-005].
{filler}

## References
[LIB-001] [LIB-003] [LIB-005]
"""


@app.post("/v1/chat/completions")
async def chat(body: dict) -> dict:
    messages = body["messages"]
    tools = {t["function"]["name"] for t in body.get("tools") or []}
    system = (messages[0].get("content") or "") if messages else ""
    user = " ".join(m.get("content") or "" for m in messages if m.get("role") == "user")
    step = sum(1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls"))
    outs = _tool_outputs(messages)

    if "compare_groups" in tools:
        careful = any(w in user.lower() for w in ("protocol", "issue", "exclusion", "clean"))
        plan = ["check", "clean", "compare_clean"] if careful else ["describe", "compare_raw"]
        if "search_papers" in tools:
            plan.append("search")
        if step < len(plan):
            action = plan[step]
            if action == "describe":
                return _reply(_tool_msg("describe_dataset", {"dataset": "nitrogrow_trial"}))
            if action == "compare_raw":
                return _reply(_tool_msg("compare_groups", {"dataset": "nitrogrow_trial"}))
            if action == "check":
                return _reply(_tool_msg("check_data_quality", {"dataset": "nitrogrow_trial"}))
            if action == "clean":
                q = json.loads(outs[-1])
                ids = [x["id"] for x in q["implausible_values"]]
                return _reply(_tool_msg("clean_dataset", {"dataset": "nitrogrow_trial", "drop_ids": ids}))
            if action == "compare_clean":
                return _reply(_tool_msg("compare_groups", {"dataset": "nitrogrow_trial_clean"}))
            if action == "search":
                return _reply(_tool_msg("search_papers", {"query": "biostimulant wheat yield"}))
        last_compare = next((o for o in reversed(outs) if '"mean_diff"' in o), "{}")
        return _reply({"role": "assistant", "content": "Experimenter report. Result: " + last_compare})

    if "search_papers" in tools:
        plan = [("search_papers", {"query": "biostimulant wheat yield"}),
                ("get_abstract", {"paper_id": "LIB-003"})]
        if "get_full_text" in tools:
            plan.append(("get_full_text", {"paper_id": "LIB-001"}))
        if step < len(plan):
            return _reply(_tool_msg(*plan[step]))
        return _reply({"role": "assistant", "content": _manuscript(user)})

    if "json" in system.lower() and "review" in system.lower():
        review = {"recommendation": "minor_revision", "summary": "Sound analysis.",
                  "strengths": ["Exclusions reported"], "weaknesses": ["Few sites"],
                  "requested_changes": ["Discuss site heterogeneity"]}
        return _reply({"role": "assistant", "content": json.dumps(review)})

    if "revise" in user.lower() or "manuscript" in system.lower():
        return _reply({"role": "assistant", "content": _manuscript(user)})

    return _reply({"role": "assistant", "content": "Summary: " + user[:300]})
