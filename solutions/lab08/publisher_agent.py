"""Lab 8 solution: the Publisher, an A2A agent that pays and submits.

Discovers the Journal from its Agent Card, pays the Article Processing Charge with
x402 (first submission only), then submits through A2A and returns the decision.

Input data : {"manuscript": "...", "title": "...", "receipt": {...}?}   (receipt present = resubmission)
Output data: {"decision", "reviews", "receipt", "doi"?}

Run:  uv run python solutions/lab08/publisher_agent.py
"""

from common.a2a_kit import AgentReply, ask_agent, build_card, discover, serve_agent
from common.agent_loop import run_agent
from common.config import JOURNAL_URL, PUBLISHER_URL, TEAM_NAME
from common.x402_kit import paying_http_client, settlement_of


async def pay_apc(title: str) -> dict:
    """Pay the journal's APC with x402. Returns the journal's receipt."""
    async with paying_http_client(max_payment="$1") as http:
        r = await http.post(f"{JOURNAL_URL}/apc", json={"team": TEAM_NAME, "title": title})
    if r.status_code != 200:
        raise RuntimeError(f"APC payment failed: HTTP {r.status_code} {r.text[:200]}")
    receipt = r.json()
    receipt["transaction"] = settlement_of(r).get("transaction")
    print(f"[publisher] APC paid, submission {receipt['submission_id']}, tx {receipt['transaction']}", flush=True)
    return receipt


async def cover_letter(title: str) -> str:
    try:
        return await run_agent(
            "You write 3-sentence cover letters for journal submissions. Plain text only.",
            f"Cover letter for the manuscript '{title}' from team {TEAM_NAME}.",
            verbose=False,
        )
    except Exception:
        return f"Dear Editor, please consider our manuscript '{title}' for publication. Team {TEAM_NAME}."


async def handle(text: str, data: dict) -> AgentReply:
    manuscript, title = data["manuscript"], data.get("title", "Untitled")

    # 1. Discovery: confirm the journal offers manuscript submission.
    journal = await discover(JOURNAL_URL)
    skill = next((s for s in journal.skills if s.id == "submit_manuscript"), None)
    if skill is None:
        raise RuntimeError(f"{journal.name} does not accept submissions")
    print(f"[publisher] submitting to {journal.name}", flush=True)

    # 2. Payment: only the first time. The receipt covers the revision rounds.
    receipt = data.get("receipt") or await pay_apc(title)

    # 3. Submission over A2A.
    letter = await cover_letter(title)
    reply = await ask_agent(
        JOURNAL_URL,
        letter,
        {"manuscript": manuscript, "title": title, "team": TEAM_NAME, "receipt": receipt},
    )
    result = dict(reply.data) | {"receipt": receipt}
    return AgentReply(text=reply.text, data=result)


card = build_card(
    name="Publisher",
    description="Submits manuscripts to journals and pays submission fees with x402.",
    url=PUBLISHER_URL,
    skills=[
        {
            "id": "publish_manuscript",
            "name": "Publish a manuscript",
            "description": 'Data part {"manuscript", "title", "receipt"?}. Pays the APC if needed, submits, returns the decision.',
            "tags": ["publishing"],
        }
    ],
)

if __name__ == "__main__":
    serve_agent(card, handle)
