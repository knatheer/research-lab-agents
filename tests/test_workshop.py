"""End-to-end tests for the workshop solutions. Instructor use: run before every workshop.

    uv run pytest -v

Starts every service as a subprocess with a scripted fake LLM (tests/fake_openai.py),
so no OpenAI key or internet is needed. Runs on the default ports, so stop any
lab services you have running first.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values
from mcp import Client

ROOT = Path(__file__).resolve().parents[1]
FAKE_PORT = 7999

SERVICES = [
    ("fake_llm", [sys.executable, "-m", "uvicorn", "tests.fake_openai:app", "--port", str(FAKE_PORT)], FAKE_PORT),
    ("bank", [sys.executable, "services/mock_bank.py"], 4022),
    ("archive", [sys.executable, "solutions/lab07/paper_archive.py"], 8002),
    ("library", [sys.executable, "solutions/lab07/library_server.py"], 8001),
    ("verifier", [sys.executable, "solutions/lab05/verifier_agent.py"], 9102),
    ("experimenter", [sys.executable, "solutions/lab06/experimenter_agent.py"], 9101),
    ("writer", [sys.executable, "solutions/lab06/writer_agent.py"], 9103),
    ("publisher", [sys.executable, "solutions/lab08/publisher_agent.py"], 9104),
    ("reviewer", [sys.executable, "instructor/reviewer_agent.py"], 9201),
    ("journal", [sys.executable, "instructor/journal.py"], 9200),
]


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="session", autouse=True)
def services(tmp_path_factory):
    busy = [name for name, _, port in SERVICES if _port_open(port)]
    if busy:
        pytest.exit(f"Ports already in use by: {busy}. Stop your lab services first.", returncode=2)
    env = os.environ | {
        "OPENAI_BASE_URL": f"http://127.0.0.1:{FAKE_PORT}/v1",
        "OPENAI_API_KEY": "fake",
        "TEAM_NAME": "pytest",
        "PYTHONUTF8": "1",
    }
    dot = dotenv_values(ROOT / ".env") if (ROOT / ".env").exists() else {}
    if not (dot.get("PAYER_PRIVATE_KEY") and dot.get("PAY_TO_ADDRESS")):  # fresh clone: throwaway test wallets
        from eth_account import Account

        env |= {"PAYER_PRIVATE_KEY": Account.create().key.hex(), "PAY_TO_ADDRESS": Account.create().address}
    logs = tmp_path_factory.mktemp("logs")
    procs = []
    for name, cmd, port in SERVICES:
        out = open(logs / f"{name}.log", "w", encoding="utf-8")
        procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT))
        deadline = time.time() + 30
        while not _port_open(port):
            if time.time() > deadline:
                pytest.exit(f"{name} did not start; see {logs / (name + '.log')}", returncode=3)
            time.sleep(0.2)
    os.environ.update(env)
    yield
    for p in procs:
        p.terminate()
    for p in procs:
        p.wait(timeout=10)


def run(coro):
    return asyncio.run(coro)


def stdio(script: str):
    from common.agent_loop import stdio_server

    return stdio_server(script)


# ---------------------------------------------------------------- Lab 1 and 2: MCP server
def test_lab01_has_three_tools():
    async def go():
        async with Client(stdio("solutions/lab01/instruments_server.py")) as c:
            return sorted(t.name for t in (await c.list_tools()).tools)

    assert run(go()) == ["compare_groups", "describe_dataset", "list_datasets"]


def test_lab02_naive_vs_clean_results():
    async def go():
        async with Client(stdio("solutions/lab02/instruments_server.py")) as c:
            naive = (await c.call_tool("compare_groups", {"dataset": "nitrogrow_trial"})).structured_content
            qa = (await c.call_tool("check_data_quality", {"dataset": "nitrogrow_trial"})).structured_content
            ids = [v["id"] for v in qa["implausible_values"]]
            cleaned = (await c.call_tool("clean_dataset", {"dataset": "nitrogrow_trial", "drop_ids": ids})).structured_content
            clean = (await c.call_tool("compare_groups", {"dataset": "nitrogrow_trial_clean"})).structured_content
            return naive, qa, cleaned, clean

    naive, qa, cleaned, clean = run(go())
    assert naive["mean_diff"] == pytest.approx(276.9473)
    assert qa["duplicate_rows_extra"] == 4 and len(qa["missing_outcome_ids"]) == 2 and len(qa["implausible_values"]) == 5
    assert cleaned["rows_after"] == 113
    assert (clean["n_a"], clean["n_b"]) == (55, 58)
    assert clean["mean_diff"] == pytest.approx(0.3103)
    assert clean["p_value"] < 0.001


def test_lab02_resources_and_prompts():
    async def go():
        async with Client(stdio("solutions/lab02/instruments_server.py")) as c:
            proto = (await c.read_resource("lab://protocol")).contents[0].text
            dic = (await c.read_resource("lab://datasets/nitrogrow_trial/dictionary")).contents[0].text
            prompts = sorted(p.name for p in (await c.list_prompts()).prompts)
            return proto, dic, prompts

    proto, dic, prompts = run(go())
    assert "exclusion" in proto.lower() and "yield_t_ha" in dic
    assert prompts == ["analysis_plan", "manuscript_draft"]


# ---------------------------------------------------------------- Lab 3 and 4: agent loop, HTTP MCP
def test_lab03_experimenter_script_runs():
    out = subprocess.run(
        [sys.executable, "solutions/lab03/experimenter.py"], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert "EXPERIMENTER REPORT" in out.stdout


def test_lab04_library_over_http():
    async def go():
        async with Client("http://127.0.0.1:8001/mcp") as c:
            hits = (await c.call_tool("search_papers", {"query": "unit errors duplicate"})).structured_content
            cite = (await c.read_resource("library://papers/LIB-003/citation")).contents[0].text
            return hits["result"], cite

    hits, cite = run(go())
    assert hits[0]["id"] == "LIB-003"
    assert "Okafor" in cite


# ---------------------------------------------------------------- Lab 5 and 6: A2A
def test_lab05_verifier_flags_raw_and_confirms_clean():
    from common.a2a_kit import ask_agent

    async def claim(ds):
        async with Client(stdio("solutions/lab02/instruments_server.py")) as c:
            return (await c.call_tool("compare_groups", {"dataset": ds})).structured_content

    raw = run(ask_agent("http://127.0.0.1:9102", "verify", {"claim": run(claim("nitrogrow_trial"))}))
    assert raw.data["verdict"] == "issues_found" and len(raw.data["issues"]) == 3
    clean = run(ask_agent("http://127.0.0.1:9102", "verify", {"claim": run(claim("nitrogrow_trial_clean"))}))
    assert clean.data["verdict"] == "confirmed"
    assert clean.data["verified_results"]["n_a"] == 55  # whole floats converted back to int


def test_lab06_agent_cards_discoverable():
    from common.a2a_kit import discover

    names = {run(discover(f"http://127.0.0.1:{p}")).name for p in (9101, 9102, 9103, 9104, 9200, 9201)}
    assert names == {"Experimenter", "Verifier", "Writer", "Publisher", "Journal of Autonomous Agronomy", "Reviewer"}


def test_lab06_pipeline_produces_manuscript():
    out = subprocess.run([sys.executable, "solutions/lab06/pi.py"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    log = json.loads((ROOT / "outputs" / "pi_run_log.json").read_text(encoding="utf-8"))
    assert log["rounds"][-1]["verification"]["verdict"] == "confirmed"
    assert Path(log["manuscript"]["path"]).exists()


# ---------------------------------------------------------------- Lab 7: x402
def test_lab07_unpaid_request_gets_402():
    r = httpx.get("http://127.0.0.1:8002/fulltext/LIB-003")
    assert r.status_code == 402
    from common.x402_kit import decode_header

    offer = decode_header(r.headers["PAYMENT-REQUIRED"])["accepts"][0]
    assert offer["amount"] == "20000" and offer["network"] == "eip155:84532"


def test_lab07_paid_request_settles():
    from common.x402_kit import paying_http_client, settlement_of

    async def go():
        async with paying_http_client("$0.05") as http:
            return await http.get("http://127.0.0.1:8002/fulltext/LIB-007")

    r = run(go())
    assert r.status_code == 200
    assert settlement_of(r)["success"] is True


def test_lab07_spend_cap_blocks_payment():
    from common.x402_kit import paying_http_client

    async def go():
        async with paying_http_client("$0.01") as http:  # cap below the $0.02 price
            return await http.get("http://127.0.0.1:8002/fulltext/LIB-009")

    try:
        blocked = run(go()).status_code != 200
    except Exception:  # the x402 client refuses to sign above the cap
        blocked = True
    assert blocked


def test_lab07_cheating_is_rejected():
    out = subprocess.run(
        [sys.executable, "solutions/lab07/try_to_cheat.py"], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    lines = out.stdout.splitlines()
    assert "HTTP 200" in lines[0]
    assert all("HTTP 402" in ln for ln in lines[1:4]), out.stdout


# ---------------------------------------------------------------- Lab 8: capstone
def test_lab08_journal_desk_rejects_without_receipt():
    from common.a2a_kit import ask_agent

    reply = run(ask_agent("http://127.0.0.1:9200", "hi", {"manuscript": "x " * 200}))
    assert reply.data["decision"] == "desk_reject"


def test_lab08_capstone_gets_published():
    out = subprocess.run([sys.executable, "solutions/lab08/pi_full.py"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    assert "FINAL: ACCEPT" in out.stdout
    ledger = httpx.get("http://127.0.0.1:4022/ledger").json()
    assert any(t["usdc"] == "0.50" for t in ledger["transactions"])  # the APC was paid
