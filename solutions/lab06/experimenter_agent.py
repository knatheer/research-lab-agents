"""Lab 6 solution: the Experimenter, now an A2A agent.

Same brain as Lab 3 (LLM + Lab Instruments over MCP), new front door (A2A),
built with common/a2a_kit.py so the file stays short.

Input : text = research question; data (optional) = {"feedback": <verifier report>}
Output: text = report; data = {"claim": <compare_groups output>, "cleaning": <clean_dataset output or null>}

Run:  uv run python solutions/lab06/experimenter_agent.py
"""

import json

from common.a2a_kit import AgentReply, build_card, serve_agent
from common.agent_loop import MCPToolbox, run_agent, stdio_server
from common.config import EXPERIMENTER_URL

SYSTEM = """You are the Experimenter in a research lab.
Answer the research question by running the statistical tools on the lab's datasets.
Never invent numbers. Finish with a short report: dataset used, exclusions applied
(with counts), n per group, mean difference with 95% CI, p-value, Cohen's d."""


async def handle(text: str, data: dict) -> AgentReply:
    task = text
    if data.get("feedback"):
        task += (
            "\n\nAn independent verifier rejected your previous analysis. Fix every issue, "
            "following the study protocol's exclusion rules, then re-run the primary analysis.\n"
            f"VERIFIER REPORT:\n{json.dumps(data['feedback'], indent=2)}"
        )
    async with MCPToolbox({"instruments": stdio_server("solutions/lab02/instruments_server.py")}) as tb:
        report = await run_agent(SYSTEM, task, tb, name="experimenter")
        claim = tb.last_result("compare_groups")
        cleaning = tb.last_result("clean_dataset")
    if claim is None:
        raise RuntimeError("The experimenter finished without running compare_groups.")
    return AgentReply(text=report, data={"claim": claim, "cleaning": cleaning})


card = build_card(
    name="Experimenter",
    description="Runs statistical experiments on the lab's datasets using the Lab Instruments MCP server.",
    url=EXPERIMENTER_URL,
    skills=[
        {
            "id": "run_experiment",
            "name": "Run an experiment",
            "description": "Answers a research question with a statistical analysis. Accepts verifier feedback in a data part.",
            "tags": ["experiment", "statistics"],
            "examples": ["Does NitroGrow increase wheat yield in nitrogrow_trial?"],
        }
    ],
)

if __name__ == "__main__":
    serve_agent(card, handle)
