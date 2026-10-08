"""Lab 8 solution (capstone): the full research lifecycle.

  Experimenter <-> Verifier   (until the result is confirmed)
  Writer                      (buys papers via x402 inside the Library MCP server)
  Publisher -> Journal        (pays the APC via x402, gets peer review over A2A)
  Writer <-> Publisher        (revise and resubmit until accepted or rejected)

Start (one terminal each):
    uv run python services/mock_bank.py                  # skip if the instructor runs the bank + journal
    uv run python solutions/lab07/paper_archive.py
    uv run python solutions/lab07/library_server.py
    uv run python solutions/lab05/verifier_agent.py
    uv run python solutions/lab06/experimenter_agent.py
    uv run python solutions/lab06/writer_agent.py
    uv run python solutions/lab08/publisher_agent.py
Then:
    uv run python solutions/lab08/pi_full.py
"""

import asyncio
import json

from common.a2a_kit import ask_agent, discover
from common.config import EXPERIMENTER_URL, OUTPUTS_DIR, PUBLISHER_URL, VERIFIER_URL, WRITER_URL

QUESTION = "Does NitroGrow increase winter wheat yield? Use the nitrogrow_trial dataset."
MAX_VERIFY_ROUNDS = 3
MAX_REVISIONS = 2


def banner(msg: str) -> None:
    print("\n" + "=" * 70 + f"\n{msg}\n" + "=" * 70, flush=True)


async def find_agent(urls: list[str], tag: str) -> str:
    for url in urls:
        card = await discover(url)
        if any(tag in s.tags for s in card.skills):
            print(f"  {tag:<13} -> {card.name} ({url})")
            return url
    raise RuntimeError(f"No agent offers '{tag}'")


async def main() -> None:
    log: dict = {"question": QUESTION}

    banner("1. DISCOVERY")
    team = [EXPERIMENTER_URL, VERIFIER_URL, WRITER_URL, PUBLISHER_URL]
    experimenter = await find_agent(team, "experiment")
    verifier = await find_agent(team, "verification")
    writer = await find_agent(team, "writing")
    publisher = await find_agent(team, "publishing")

    banner("2. EXPERIMENT + VERIFICATION")
    feedback, verification = None, {}
    for round_no in range(1, MAX_VERIFY_ROUNDS + 1):
        exp = await ask_agent(experimenter, QUESTION, {"feedback": feedback} if feedback else None)
        ver = await ask_agent(verifier, "Please verify this result.", {"claim": exp.data["claim"]})
        verification = ver.data
        print(f"  round {round_no}: dataset={exp.data['claim']['dataset']}  verdict={verification['verdict']}")
        for issue in verification.get("issues", []):
            print("     -", issue)
        if verification["verdict"] == "confirmed":
            break
        feedback = verification
    else:
        print("Could not get a verified result. Stopping.")
        return
    log["verification"] = verification

    banner("3. WRITING")
    payload = {"results": verification["verified_results"], "verification": verification}
    draft = await ask_agent(writer, "Write the manuscript for these verified results.", payload)
    print(f"  draft v{draft.data['version']}: {draft.data['title']}  cites {draft.data['cited']}")

    banner("4. PUBLISHING")
    receipt = None
    for attempt in range(0, MAX_REVISIONS + 1):
        pub = await ask_agent(
            publisher,
            "Publish this manuscript.",
            {"manuscript": draft.text, "title": draft.data["title"], "receipt": receipt},
        )
        receipt = pub.data["receipt"]
        decision = pub.data["decision"]
        print(f"  submission {receipt['submission_id']} round {pub.data.get('round')}: {decision.upper()}")
        for review in pub.data.get("reviews", []):
            print(f"     {review['reviewer']}: {review['recommendation']}")
            for change in review.get("requested_changes", [])[:4]:
                print(f"        * {change}")
        log.setdefault("submissions", []).append(pub.data)

        if decision in ("accept", "reject", "desk_reject") or attempt == MAX_REVISIONS:
            break
        banner(f"5.{attempt + 1} REVISION")
        draft = await ask_agent(
            writer,
            "Revise the manuscript to address the reviews.",
            payload | {"reviews": pub.data["reviews"], "previous_manuscript": draft.text},
        )
        print(f"  draft v{draft.data['version']} ready")

    (OUTPUTS_DIR / "capstone_run_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    banner(f"FINAL: {decision.upper()}" + (f"  DOI {pub.data['doi']}" if pub.data.get("doi") else ""))


if __name__ == "__main__":
    asyncio.run(main())
