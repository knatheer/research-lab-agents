"""Shared settings for every lab. Values come from the .env file in the repo root."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
LIBRARY_DIR = ROOT / "library"
WORKSPACE_DIR = ROOT / "workspace"  # cleaned datasets and figures land here
OUTPUTS_DIR = ROOT / "outputs"  # manuscripts, run logs
WORKSPACE_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# LLM
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

# Who you are (shown on the Journal board in the capstone)
TEAM_NAME = os.getenv("TEAM_NAME", "unnamed-team")

# Network locations. Students run everything on 127.0.0.1.
# The Journal, Reviewer and Mock Bank can run on the instructor's laptop for the capstone.
HOST = os.getenv("HOST", "127.0.0.1")
LIBRARY_MCP_URL = os.getenv("LIBRARY_MCP_URL", "http://127.0.0.1:8001/mcp")
ARCHIVE_URL = os.getenv("ARCHIVE_URL", "http://127.0.0.1:8002")
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://127.0.0.1:4022")

EXPERIMENTER_URL = os.getenv("EXPERIMENTER_URL", "http://127.0.0.1:9101")
VERIFIER_URL = os.getenv("VERIFIER_URL", "http://127.0.0.1:9102")
WRITER_URL = os.getenv("WRITER_URL", "http://127.0.0.1:9103")
PUBLISHER_URL = os.getenv("PUBLISHER_URL", "http://127.0.0.1:9104")
JOURNAL_URL = os.getenv("JOURNAL_URL", "http://127.0.0.1:9200")
REVIEWER_URL = os.getenv("REVIEWER_URL", "http://127.0.0.1:9201")

# x402
NETWORK = "eip155:84532"  # Base Sepolia (testnet). Same value in mock and testnet mode.
PAYER_PRIVATE_KEY = os.getenv("PAYER_PRIVATE_KEY", "")
PAY_TO_ADDRESS = os.getenv("PAY_TO_ADDRESS", "")
MAX_PAYMENT_USD = os.getenv("MAX_PAYMENT_USD", "$1")


def port_of(url: str) -> int:
    """'http://127.0.0.1:9101' -> 9101"""
    return int(url.rstrip("/").rsplit(":", 1)[1].split("/")[0])
