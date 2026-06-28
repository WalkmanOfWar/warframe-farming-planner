"""The set of all items worth farming — the default target when no wishlist.

The whole point of the tool is "get everything I don't have yet", so the default
target is every **masterable** item in the game (warframes, weapons, companions,
etc. — the things that count toward Mastery Rank), pulled from the warframestat
items dataset. The player's owned items are then subtracted from this.

A wishlist file is only an optional way to narrow the target to specific items.
"""

from __future__ import annotations

import requests

ITEMS_URL = "https://api.warframestat.us/items"


def fetch_all_targets(timeout: int = 60) -> set[str]:
    """Return display names of every masterable item in the game.

    Names are raw (not normalized); callers normalize on comparison.
    """
    resp = requests.get(
        ITEMS_URL,
        params={"only": "name,masterable"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return {
        item["name"]
        for item in resp.json()
        if isinstance(item, dict) and item.get("masterable") and item.get("name")
    }
