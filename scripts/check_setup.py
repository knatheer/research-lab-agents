"""Lab 0: check that your machine is ready for the workshop.

Run:  uv run python scripts/check_setup.py
Every line should say OK. Fix any FAIL before the workshop starts.
"""

import asyncio
import importlib.metadata as md
import shutil
import socket
import sys

from common.config import MODEL, PAY_TO_ADDRESS, PAYER_PRIVATE_KEY, ROOT

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'OK' if ok else 'FAIL':>4}] {name}  {detail}", flush=True)


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


async def openai_ping() -> str:
    from openai import AsyncOpenAI

    r = await AsyncOpenAI().chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": "Reply with the single word OK."}]
    )
    return (r.choices[0].message.content or "").strip()


def main() -> None:
    check("Python 3.12", sys.version_info[:2] == (3, 12), sys.version.split()[0])
    for pkg in ("mcp", "a2a-sdk", "x402", "openai", "pandas", "scipy"):
        try:
            check(f"package {pkg}", True, md.version(pkg))
        except md.PackageNotFoundError:
            check(f"package {pkg}", False, "missing: run 'uv sync'")

    env = ROOT / ".env"
    check(".env file", env.exists(), "" if env.exists() else "copy .env.example to .env")
    import os

    key = os.getenv("OPENAI_API_KEY", "")
    check("OPENAI_API_KEY set", key.startswith("sk-"), "" if key else "add it to .env")
    if key:
        try:
            reply = asyncio.run(openai_ping())
            check(f"OpenAI call with model {MODEL}", True, f"model said: {reply[:20]!r}")
        except Exception as exc:
            check(f"OpenAI call with model {MODEL}", False, f"{type(exc).__name__}: {str(exc)[:150]}")

    npx = shutil.which("npx")
    check("Node.js (npx) for MCP Inspector", npx is not None, npx or "install Node.js LTS")
    check("Test wallet in .env", bool(PAYER_PRIVATE_KEY and PAY_TO_ADDRESS), "" if PAYER_PRIVATE_KEY else "run scripts/make_wallet.py (Lab 7)")

    busy = [p for p in (4022, 8001, 8002, 9101, 9102, 9103, 9104) if not port_free(p)]
    check("Lab ports free", not busy, f"in use: {busy}" if busy else "")

    failed = [n for n, ok, _ in results if not ok]
    print("\nAll good. See you at the workshop." if not failed else f"\n{len(failed)} check(s) failed: {failed}")


if __name__ == "__main__":
    main()
