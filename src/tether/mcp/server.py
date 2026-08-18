"""
MCP server exposing `notify` and `ask` — replaces handing agents a raw
Telegram API URL with the token baked in (the old approach, which couldn't
be published and had to be re-taught to every agent). Agents call a tool;
the token stays in .env and is never exposed to them.

Registration (one-time, per docs/SETUP.md):
    claude mcp add tether -- python -m tether.mcp.server
"""
from __future__ import annotations

import asyncio
import time
import uuid

import httpx
from mcp.server.mcpserver import MCPServer

from tether.config import Config
from tether.mcp import shared_state

_cfg = Config.load()
_TOKEN = _cfg.secrets.bot_token
_CHAT_ID = _cfg.secrets.chat_id

server = MCPServer(
    name="tether",
    version="1.0.0",
    instructions=(
        "Notify or ask the PC operator via Telegram while they are away from "
        "the screen. Use `ask` whenever a decision genuinely needs the human "
        "instead of stalling or guessing."
    ),
)


async def _send_message(text: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
            data={"chat_id": _CHAT_ID, "text": text},
        )


@server.tool()
async def notify(message: str) -> str:
    """Send a message to the operator's Telegram. Returns immediately —
    does not wait for a reply. Use `ask` if you need one."""
    await _send_message(f"\U0001F514 {message}")
    return "sent"


@server.tool()
async def ask(question: str, timeout_seconds: int = 300) -> str:
    """Ask the operator a question via Telegram and WAIT for their reply
    before returning. Use this whenever a decision needs the human rather
    than stalling silently until they happen to check back.
    Returns their reply text, or a timeout notice if they don't answer."""
    question_id = uuid.uuid4().hex[:12]
    shared_state.write_pending(question_id, question)
    await _send_message(f"❓ {question}")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        answer = shared_state.read_and_clear_answer(question_id)
        if answer is not None:
            return answer
        await asyncio.sleep(1.0)

    shared_state.clear_pending(question_id)
    return f"(no answer within {timeout_seconds}s)"


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
