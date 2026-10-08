"""Lab 6 solution: the Principal Investigator (PI), an A2A orchestrator.

The PI does no science itself. It discovers the lab's agents by their Agent
Cards and delegates: Experimenter -> Verifier (loop until confirmed) -> Writer.

Start first (one terminal each):
    uv run python solutions/lab04/library_server.py
    uv run python solutions/lab05/verifier_agent.py
    uv run python solutions/lab06/experimenter_agent.py
    uv run python solutions/lab06/writer_agent.py
Then:
    uv run python solutions/lab06/pi.py
"""

import asyncio
import json

from common.a2a_kit import ask_agent, discover
from common.config import EXPERIMENTER_URL, OUTPUTS_DIR, VERIFIER_URL, WRITER_URL

QUESTION = "Does NitroGrow increase winter wheat yield? Use the nitrogrow_trial dataset."
MAX_VERIFY_ROUNDS = 3


def banner(msg: str) -> None:
    print("\n" + "=" * 70 + f"\n{msg}\n" + "=" * 70, flush=True)


async def find_agent(urls: list[str], skill_tag: str) -> str:
    """Pick the first agent whose card advertises a skill with this tag."""
    for url in urls:
        card = await discover(url)
        for skill in card.skills:
            if skill_tag in skill.tags:
                print(f"  {skill_tag:<14} -> {card.name} at {url} (skill '{skill.id}')")
                return url
    raise RuntimeError(f"No agent offers '{skill_tag}'")


async def main() -> None:
    log: dict = {"question": QUESTION, "rounds": []}

    banner("1. DISCOVERY: reading Agent Cards")
    known = [EXPERIMENTER_URL, VERIFIER_URL, WRITER_URL]
    experimenter = await find_agent(known, "experiment")
    verifier = await find_agent(known, "verification")
    writer = await find_agent(known, "writing")

    feedback = None
    verification: dict = {}
    claim: dict = {}
    for round_no in range(1, MAX_VERIFY_ROUNDS + 1):
        banner(f"2.{round_no} EXPERIMENT (round {round_no})")
        exp = await ask_agent(experimenter, QUESTION, {"feedback": feedback} if feedback else None)
        claim = exp.data["claim"]
        print(exp.text[:800])

        banner(f"3.{round_no} VERIFICATION (round {round_no})")
        ver = await ask_agent(verifier, "Please verify this result.", {"claim": claim})
        verification = ver.data
        print(f"Verdict: {verification['verdict']}")
        for issue in verification.get("issues", []):
            print("  -", issue)
        log["rounds"].append({"claim": claim, "verification": verification})

        if verification["verdict"] == "confirmed":
            break
        feedback = verification
    else:
        print("Verification failed after all rounds. Nothing will be written.")
        return

    banner("4. WRITING the manuscript")
    draft = await ask_agent(writer, "Write the manuscript for these verified results.", {"results": verification["verified_results"], "verification": verification})
    print(f"Title: {draft.data['title']}\nSaved: {draft.data['path']}\nCites: {draft.data['cited']}")
    log["manuscript"] = draft.data

    (OUTPUTS_DIR / "pi_run_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    banner("DONE. See outputs/ for the manuscript and the run log.")


if __name__ == "__main__":
    asyncio.run(main())
