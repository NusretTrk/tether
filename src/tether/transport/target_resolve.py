"""Resolves which Target a remote text/photo message actually goes to.

A tiny module of its own rather than a method on AppState: text.py,
callbacks.py, and handlers.py (for /target itself) all need this, and
importing GenericTarget from state.py would be an awkward direction (state
is meant to be the passive data the rest of the app reads, not something
that reaches into targets/ itself).
"""
from __future__ import annotations


def active_target(state):
    """state.target (Claude Desktop) unless /target picked a named profile
    from settings.keypad_profiles - falls back to state.target if the name
    somehow no longer exists (profile removed from config after being
    selected) rather than erroring."""
    # getattr, not direct access: existing test doubles for `state` predate
    # this field, and "not present" should behave the same as "not set".
    name = getattr(state, "active_target_profile", None)
    if not name:
        return state.target
    profile = state.config.settings.keypad_profiles.get(name)
    if not profile or not profile.get("window_keyword"):
        return state.target
    from tether.targets.generic import GenericTarget
    return GenericTarget(profile["window_keyword"], state.config.settings.preserve_user_clipboard)
