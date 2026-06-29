"""The set of all items worth farming — the default target when no wishlist.

The whole point of the tool is "get everything I don't have yet", so the default
target is every **masterable** item in the game (warframes, weapons, companions,
etc. — the things that count toward Mastery Rank). This is derived from the items
dataset already loaded by :func:`warframe_routes.items.load_items`, so it needs no
extra network call.

A wishlist file is only an optional way to narrow the target to specific items.
"""

from __future__ import annotations


def all_targets(items_data: list[dict]) -> set[str]:
    """Display names of every masterable item in the given dataset.

    Names are raw (not normalized); callers normalize on comparison.
    """
    return {
        it["name"]
        for it in items_data
        if isinstance(it, dict) and it.get("masterable") and it.get("name")
    }
