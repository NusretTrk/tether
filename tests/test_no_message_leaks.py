"""
Structural guard on the security boundary.

Every Telegram handler must be wrapped in @restricted, and every explicit
send must target the configured chat id. These are checked by reading the
source rather than by running the bot, so a future edit that quietly drops
a decorator fails CI instead of silently exposing the machine to anyone who
finds the bot username.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "tether"
TRANSPORT = SRC / "transport"

# Not update handlers: error_handler is registered separately and targets the
# configured chat id explicitly; helpers starting with _ are called only from
# already-guarded handlers.
EXEMPT = {"error_handler", "restricted", "wrapper"}


def _handler_functions(path: pathlib.Path):
    """Yields (name, decorator_names) for every `async def f(update, ...)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        args = [a.arg for a in node.args.args]
        if not args or args[0] != "update":
            continue
        if node.name in EXEMPT or node.name.startswith("_"):
            continue
        decorators = {
            d.id if isinstance(d, ast.Name) else getattr(d, "attr", "")
            for d in node.decorator_list
        }
        yield node.name, decorators


def test_every_update_handler_is_restricted():
    unguarded = []
    for path in TRANSPORT.glob("*.py"):
        for name, decorators in _handler_functions(path):
            if "restricted" not in decorators:
                unguarded.append(f"{path.name}:{name}")
    assert not unguarded, (
        "these handlers accept updates without checking the chat id, which "
        f"would let anyone control the machine: {unguarded}"
    )


def test_handlers_module_defines_the_guard():
    """If restricted() ever stops comparing against the configured chat id,
    every other test here becomes meaningless."""
    src = (TRANSPORT / "handlers.py").read_text(encoding="utf-8")
    guard = src[src.index("def restricted("):src.index("def _ctx(")]
    assert "config.secrets.chat_id" in guard
    assert "return" in guard  # drops out rather than falling through


def test_guard_does_not_reply_to_strangers():
    """Replying confirms the bot exists and lets a stranger burn the rate
    limit. The rejection path must not send anything."""
    src = (TRANSPORT / "handlers.py").read_text(encoding="utf-8")
    guard = src[src.index("def restricted("):src.index("def _ctx(")]
    for leak in ("reply_text", "send_message", "send_photo"):
        assert leak not in guard, f"guard replies to unauthorized chats via {leak}"
