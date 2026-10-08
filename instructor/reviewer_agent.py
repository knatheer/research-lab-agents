"""INSTRUCTOR SERVICE: the Reviewer agent (A2A). The Journal calls it for peer review.

Returns two reviews:
  * Reviewer 1 "Methods checklist": deterministic rules (reporting standards, LIB-008)
  * Reviewer 2 "Domain expert": an LLM review in JSON. Falls back to a canned review if no API key.

Run:  uv run python instructor/reviewer_agent.py
"""

import json
import re

from common.a2a_kit import AgentReply, build_card, serve_agent
from common.agent_loop import run_agent
from common.config import REVIEWER_URL

CHECKLIST = [
    ("exclusions_reported", r"duplicat", "Report the number of duplicate rows removed."),
    ("missing_reported", r"missing", "Report how many rows had a missing outcome."),
    ("unit_errors_reported", r"implausible|unit error|kg/ha", "Report the implausible values (unit errors) that were excluded."),
    ("ci_reported", r"95\s*%?\s*(ci|confidence)|confidence interval", "Give the mean difference with a 95% confidence interval."),
    ("p_value_reported", r"\bp\s*[=<]", "Report the p-value of the primary analysis."),
    ("effect_size_reported", r"cohen", "Report an effect size (Cohen's d)."),
    ("limitations_discussed", r"limitation", "Add a limitations paragraph (e.g. number of sites)."),
    ("references_present", r"\[LIB-\d{3}\]", "Cite related work."),
]

SYSTEM_R2 = """You are Reviewer 2, a domain expert in agronomy, reviewing a short manuscript for a journal.
Return ONLY a JSON object with keys:
recommendation (one of "accept", "minor_revision", "major_revision", "reject"),
summary (2 sentences), strengths (list), weaknesses (list), requested_changes (list).
Be fair and specific. Do not request new experiments; ask for clearer reporting and discussion."""


def checklist_review(manuscript: str) -> dict:
    text = manuscript.lower()
    passed, missing = [], []
    for key, pattern, request in CHECKLIST:
        (passed if re.search(pattern, text, re.I) else missing).append((key, request))
    n_missing = len(missing)
    rec = "accept" if n_missing == 0 else "minor_revision" if n_missing <= 2 else "major_revision"
    return {
        "reviewer": "Reviewer 1 (methods checklist)",
        "recommendation": rec,
        "passed": [k for k, _ in passed],
        "requested_changes": [r for _, r in missing],
    }


async def llm_review(manuscript: str) -> dict:
    try:
        raw = await run_agent(SYSTEM_R2, manuscript, verbose=False, name="reviewer2")
        start, end = raw.find("{"), raw.rfind("}")
        review = json.loads(raw[start : end + 1])
    except Exception as exc:
        review = {
            "recommendation": "minor_revision",
            "summary": f"Automated fallback review ({type(exc).__name__}).",
            "strengths": [],
            "weaknesses": [],
            "requested_changes": ["Discuss how the result compares with prior multi-site studies."],
        }
    review["reviewer"] = "Reviewer 2 (domain expert)"
    return review


async def handle(text: str, data: dict) -> AgentReply:
    manuscript = data.get("manuscript") or text
    reviews = [checklist_review(manuscript), await llm_review(manuscript)]
    summary = "; ".join(f"{r['reviewer']}: {r['recommendation']}" for r in reviews)
    return AgentReply(text=summary, data={"reviews": reviews})


card = build_card(
    name="Reviewer",
    description="Peer review service for the Journal of Autonomous Agronomy.",
    url=REVIEWER_URL,
    skills=[
        {
            "id": "review_manuscript",
            "name": "Peer review",
            "description": 'Data part {"manuscript": "<markdown>"}. Returns two reviews with recommendations.',
            "tags": ["review"],
        }
    ],
)

if __name__ == "__main__":
    import os

    serve_agent(card, handle, host=os.getenv("BIND_HOST", "127.0.0.1"))
