"""INSTRUCTOR SERVICE: the Journal of Autonomous Agronomy.

One web app, three faces:
  * POST /apc        x402-paywalled ($0.50). Pay the Article Processing Charge, get a receipt.
  * A2A agent at /   skill 'submit_manuscript': send manuscript + receipt, get peer review and a decision.
  * GET  /board      live board of submissions and published papers (project it in class).

Editorial policy:
  round 1      -> decision = the stricter of the two reviews
  round 2, 3   -> accept if the methods checklist passes completely, else major revision
  after 3      -> reject
One APC receipt covers up to 3 rounds of the same submission.

Classroom setup (instructor laptop on the LAN):
    set in .env:  JOURNAL_PUBLIC_URL=http://<your-LAN-IP>:9200   BIND_HOST=0.0.0.0
    uv run python services/mock_bank.py          (BANK_HOST=0.0.0.0 to share the ledger page)
    uv run python instructor/reviewer_agent.py
    uv run python instructor/journal.py
Students set JOURNAL_URL=http://<your-LAN-IP>:9200 in their .env.
"""

import hashlib
import hmac
import html
import os
import secrets
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from x402.http import PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig

from common.a2a_kit import AgentReply, ask_agent, build_app, build_card
from common.config import JOURNAL_URL, NETWORK, REVIEWER_URL, port_of
from common.x402_kit import x402_resource_server

PUBLIC_URL = os.getenv("JOURNAL_PUBLIC_URL", JOURNAL_URL)
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")
APC_PRICE = os.getenv("APC_PRICE", "$0.50")
JOURNAL_WALLET = os.getenv("JOURNAL_PAY_TO", "0x00000000000000000000000000000000004A0a1e")
SECRET = secrets.token_bytes(32)  # signs receipts; new on every restart
MAX_ROUNDS = 3

submissions: dict[str, dict] = {}  # submission_id -> record
published: list[dict] = []


def sign(submission_id: str) -> str:
    return hmac.new(SECRET, submission_id.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- A2A: submission handling
async def handle(text: str, data: dict) -> AgentReply:
    receipt = data.get("receipt") or {}
    sid = receipt.get("submission_id", "")
    if not sid or not hmac.compare_digest(sign(sid), receipt.get("token", "")):
        return AgentReply(
            text=f"Desk reject: no valid APC receipt. First pay the APC: POST {PUBLIC_URL}/apc (x402, {APC_PRICE}).",
            data={"decision": "desk_reject", "reason": "missing_or_invalid_receipt"},
        )
    rec = submissions[sid]
    if rec["status"] in ("accepted", "rejected"):
        return AgentReply(text=f"Submission {sid} is already {rec['status']}.", data={"decision": rec["status"]})
    manuscript = data.get("manuscript", "")
    if len(manuscript.split()) < 150:
        return AgentReply(text="Desk reject: manuscript too short (under 150 words).", data={"decision": "desk_reject"})

    rec["round"] += 1
    rec["title"] = data.get("title") or rec["title"]
    review = await ask_agent(REVIEWER_URL, "Please review this manuscript.", {"manuscript": manuscript})
    reviews = review.data["reviews"]
    checklist, expert = reviews[0], reviews[1]

    order = ["accept", "minor_revision", "major_revision", "reject"]
    if rec["round"] == 1:
        decision = max(checklist["recommendation"], expert["recommendation"], key=order.index)
        decision = "major_revision" if decision == "reject" else decision  # no reject on round 1
    elif checklist["recommendation"] == "accept":
        decision = "accept"
    elif rec["round"] >= MAX_ROUNDS:
        decision = "reject"
    else:
        decision = "major_revision"

    rec["status"] = {"accept": "accepted", "reject": "rejected"}.get(decision, "in revision")
    rec["history"].append({"round": rec["round"], "decision": decision, "time": datetime.now().strftime("%H:%M:%S")})
    result = {"decision": decision, "round": rec["round"], "submission_id": sid, "reviews": reviews}
    if decision == "accept":
        doi = f"10.5555/jaa.2026.{len(published) + 1:03d}"
        rec["doi"] = doi
        published.append({"doi": doi, "title": rec["title"], "team": rec["team"], "payer": rec["payer"],
                          "rounds": rec["round"], "time": datetime.now().strftime("%H:%M:%S")})
        result["doi"] = doi
    print(f"[journal] {rec['team']} round {rec['round']}: {decision}", flush=True)

    letter = f"Decision on '{rec['title']}' (submission {sid}, round {rec['round']}): {decision.upper()}."
    if decision == "accept":
        letter += f" Congratulations. Your paper is published with DOI {result['doi']}."
    elif decision != "reject":
        letter += f" Please revise and resubmit with the same receipt ({MAX_ROUNDS - rec['round']} round(s) left)."
    return AgentReply(text=letter, data=result)


card = build_card(
    name="Journal of Autonomous Agronomy",
    description=(
        f"Peer-reviewed journal. Submission requires an Article Processing Charge of {APC_PRICE} USDC "
        f"paid with x402 at POST {PUBLIC_URL}/apc, which returns a receipt."
    ),
    url=PUBLIC_URL,
    skills=[
        {
            "id": "submit_manuscript",
            "name": "Submit a manuscript",
            "description": (
                'Data part {"manuscript": "<markdown>", "title": "...", "team": "...", '
                '"receipt": {"submission_id": "...", "token": "..."}}. Returns decision and reviews.'
            ),
            "tags": ["publishing", "peer-review", "x402"],
        }
    ],
)

# ---------------------------------------------------------------- HTTP app (x402 + A2A + board)
app = FastAPI(title="Journal of Autonomous Agronomy")
app.add_middleware(
    PaymentMiddlewareASGI,
    routes={
        "POST /apc": RouteConfig(
            accepts=[PaymentOption(scheme="exact", pay_to=JOURNAL_WALLET, price=APC_PRICE, network=NETWORK)],
            mime_type="application/json",
            description="Article Processing Charge (covers up to 3 review rounds)",
        )
    },
    server=x402_resource_server(),
)


class APCRequest(BaseModel):
    team: str
    title: str = "Untitled"


@app.post("/apc")
def pay_apc(body: APCRequest, request: Request) -> dict:
    payer = request.state.payment_payload.payload["authorization"]["from"]
    sid = f"S{len(submissions) + 1:03d}-{secrets.token_hex(2)}"
    submissions[sid] = {"team": body.team, "title": body.title, "payer": payer, "round": 0, "status": "paid", "history": []}
    print(f"[journal] APC paid by {body.team} ({payer[:10]}...) -> {sid}", flush=True)
    return {"submission_id": sid, "token": sign(sid), "payer": payer, "apc": APC_PRICE}


@app.get("/board", response_class=HTMLResponse)
def board() -> str:
    pub = "".join(
        f"<tr><td>{p['time']}</td><td><b>{html.escape(p['title'])}</b></td><td>{html.escape(p['team'])}</td>"
        f"<td>{p['rounds']}</td><td><code>{p['doi']}</code></td></tr>"
        for p in reversed(published)
    )
    subs = "".join(
        f"<tr><td>{sid}</td><td>{html.escape(s['team'])}</td><td>{html.escape(s['title'][:60])}</td>"
        f"<td>{s['round']}</td><td>{s['status']}</td></tr>"
        for sid, s in reversed(list(submissions.items()))
    )
    return f"""<html><head><meta http-equiv="refresh" content="4"><title>Journal board</title>
<style>body{{font-family:system-ui;margin:24px}}td,th{{padding:6px 12px;border-bottom:1px solid #ddd;text-align:left}}</style></head>
<body><h1>Journal of Autonomous Agronomy</h1><p>APC {APC_PRICE} via x402. Submissions: {len(submissions)}. Published: {len(published)}.</p>
<h2>Published</h2><table><tr><th>Time</th><th>Title</th><th>Team</th><th>Rounds</th><th>DOI</th></tr>{pub}</table>
<h2>All submissions</h2><table><tr><th>ID</th><th>Team</th><th>Title</th><th>Round</th><th>Status</th></tr>{subs}</table></body></html>"""


# Mount the A2A agent (Agent Card + JSON-RPC endpoint) on the same app.
app.router.routes.extend(build_app(card, handle).routes)

if __name__ == "__main__":
    print(f"[journal] {PUBLIC_URL}  board: {PUBLIC_URL}/board  APC {APC_PRICE} -> {JOURNAL_WALLET}", flush=True)
    uvicorn.run(app, host=BIND_HOST, port=port_of(PUBLIC_URL), log_level="warning")
