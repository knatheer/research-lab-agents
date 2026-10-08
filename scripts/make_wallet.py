"""Create two test wallets and store them in .env.

  PAYER_PRIVATE_KEY : the wallet your agents spend from (buyer)
  PAY_TO_ADDRESS    : the wallet your Paper Archive gets paid into (seller)

These are throwaway TEST keys. Never send real funds to them, never reuse them
on a real network, never commit .env to git.

Run:  uv run python scripts/make_wallet.py
"""

from eth_account import Account

from common.config import ROOT

env_path = ROOT / ".env"
text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""


def set_var(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            if line.strip() != f"{key}=":
                print(f"{key} already set, leaving it unchanged.")
                return content
            lines[i] = f"{key}={value}"
            return "\n".join(lines) + "\n"
    return content.rstrip("\n") + f"\n{key}={value}\n"


buyer = Account.create()
seller = Account.create()
text = set_var(text, "PAYER_PRIVATE_KEY", buyer.key.hex())
text = set_var(text, "PAYER_ADDRESS", buyer.address)
text = set_var(text, "PAY_TO_ADDRESS", seller.address)
env_path.write_text(text, encoding="utf-8")

print("Wallets written to .env")
print(f"  Buyer  (PAYER_ADDRESS) : {buyer.address}")
print(f"  Seller (PAY_TO_ADDRESS): {seller.address}")
print("Optional testnet mode: get test USDC for the BUYER address at https://faucet.circle.com (Base Sepolia).")
