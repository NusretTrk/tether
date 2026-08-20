"""
Watches for popups/dialogs/banners (e.g. "sign in again") via the target's
UIA-backed detector and reports newly-appeared ones. Synchronous/blocking
(UIA) — callers must run poll() in a worker thread.

Safety: this module only detects and reports. It never clicks anything
itself. Every button name it reports is still exposed for a human decision
- the owner tapping a button in the resulting Telegram alert is that
decision, not an automatic action tether takes on its own. See
SAFE_DIALOG_BUTTON_LABELS below for exactly what's ever offered as a tap
target, and transport/jobs.py::dialog_job for where the alert + keyboard
actually get built.
"""
from __future__ import annotations

from tether.targets.base import Dialog

# The explicit, reviewed allowlist the module docstring above refers to.
# detect_dialogs()'s button list is NOT scoped to the actual dialog - Claude
# Desktop's popups aren't a distinct UIA region, so a scan can return
# unrelated things that happen to be visible at the same time (sidebar
# session names, nav items - confirmed live: a real alert once listed
# "HalalO" and "Dostum Dostum Pro" alongside the real "Sign in again"
# button, both actually session names, not dialog actions). Tapping one of
# those by mistake, thinking it dismisses the dialog, would silently switch
# sessions instead - a correctness problem, not just a safety one.
#
# Rather than trying to fix the UIA scoping (the code that documents why
# that's not reliable here predates this feature and there's no live-tested
# alternative to replace it with), this filters by CONTENT: only offer a
# tap target for button text that's an exact, case-insensitive match against
# a short list of generic dialog-action phrases. A session/nav name is
# extremely unlikely to collide with one of these; if it ever does, the
# worst case is clicking a real, visible button with that exact label -
# not arbitrary code, not a different kind of action than the owner could
# already take by walking up to the screen themselves.
#
# Authentication-adjacent entries ("sign in", "sign in again") are included
# deliberately: clicking one only ever opens Claude's own sign-in flow (the
# same thing clicking it locally would do) - it does not supply credentials,
# approve a 2FA prompt, or bypass authentication on tether's behalf. If a
# future dialog type turns out to need something more sensitive than
# "starts a flow the owner still has to complete themselves", it should NOT
# be added here without the same review this list itself got.
SAFE_DIALOG_BUTTON_LABELS = frozenset({
    "ok", "cancel", "dismiss", "got it", "close", "not now", "later",
    "skip", "yes", "no", "allow", "deny", "continue", "try again", "retry",
    "reload", "relaunch", "restart", "update", "sign in", "sign in again",
    "sign out", "log in", "log out",
})


def safe_dialog_buttons(buttons: list[str]) -> list[str]:
    """The subset of a dialog's reported buttons that are safe to offer as
    a one-tap action, in the order they were seen. Case/whitespace
    insensitive on the match, but returns the button's real original text
    (needed to click the actual control by its exact name later)."""
    return [b for b in buttons if b.strip().lower() in SAFE_DIALOG_BUTTON_LABELS]


class DialogWatcher:
    def __init__(self, target):
        self._target = target
        self._seen: set[str] = set()

    def poll(self) -> list[Dialog]:
        dialogs = self._target.detect_dialogs()
        new = [d for d in dialogs if d.name not in self._seen]
        self._seen = {d.name for d in dialogs}
        return new
