# Research Lab Agents: MCP, A2A and x402 hands-on workshop

Two days. Nine labs. One story: you build an autonomous research lab where AI agents
run an experiment, catch their own data errors, write a paper, pay for literature and
publication fees, and get peer reviewed.

| Protocol | Question it answers | Where you meet it |
|---|---|---|
| **MCP** (Model Context Protocol) | How does an agent use tools and data? | Labs 1 to 4 |
| **A2A** (Agent2Agent) | How do agents find and delegate to each other? | Labs 5 and 6 |
| **x402** (HTTP 402 payments) | How does an agent pay for something? | Labs 7 and 8 |

```
                         +-------------------- your laptop --------------------+
                         |                                                     |
  PI (orchestrator) --A2A--> Experimenter --MCP(stdio)--> Lab Instruments       |
         |               |       ^                                              |
         |--A2A--> Verifier (independent re-analysis, MCP)                      |
         |--A2A--> Writer --MCP(HTTP)--> Library --x402--> Paper Archive        |
         |--A2A--> Publisher --x402 (APC)--+                                    |
         |               +-----------------|-----------------------------------+
         |                                 v
         +------------------------- Journal  --A2A--> Reviewer   (instructor's laptop)
                                       |
                                    Mock Bank (x402 facilitator, shared ledger)
```

## Quick start (Windows, PowerShell)

```powershell
# 1. Install uv (Python package manager) once
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. In this folder
uv python install 3.12
uv sync
Copy-Item .env.example .env        # then put your OPENAI_API_KEY in .env
uv run python scripts/check_setup.py
```

## Folder map

| Folder | What is in it |
|---|---|
| `labs/` | **Your work.** Create your lab files here, following the lab guide. |
| `solutions/labNN/` | Reference solution for every lab. Use it when stuck, not before. |
| `common/` | Shared helpers: `config.py`, `agent_loop.py` (Lab 3), `a2a_kit.py` (Lab 5), `x402_kit.py` (Lab 7) |
| `services/mock_bank.py` | Local x402 facilitator with a visible ledger. No blockchain needed. |
| `instructor/` | Journal and Reviewer agents for the capstone (run by the instructor) |
| `data/` | The NitroGrow wheat trial dataset, data dictionary, study protocol |
| `library/papers.json` | Fictional literature corpus (10 papers) |
| `scripts/` | Setup checker, wallet generator, Lab 8 launcher, dataset generator |
| `tests/` | End-to-end tests with a scripted fake LLM (instructor) |
| `workspace/`, `outputs/` | Cleaned datasets, figures, manuscripts, run logs (generated) |

## Ports

| Port | Service | Lab |
|---|---|---|
| 8001 | Library MCP server (Streamable HTTP) | 4, 7 |
| 8002 | Paper Archive (x402 paywall) | 7 |
| 4022 | Mock Bank (x402 facilitator) | 7, 8 |
| 9101 to 9104 | Experimenter, Verifier, Writer, Publisher (A2A) | 5, 6, 8 |
| 9200, 9201 | Journal, Reviewer (A2A, instructor) | 8 |

## For instructors

* Run `uv run pytest -v` before each workshop. Expected: **14 passed**. It starts every service with a
  scripted fake LLM, so it needs no API key.
* Pinned versions: `mcp 2.3.0`, `a2a-sdk 1.2.2` (A2A spec 1.0), `x402 2.25.0` (protocol v2), `openai 3.26.0`.
  All three protocols move fast. Do not upgrade the week before a workshop.
* Capstone classroom setup is described at the top of `instructor/journal.py` and in the lab guide.
* The dataset is synthetic. `scripts/generate_data.py` documents the ground truth and the planted errors.
