"""Load the player's owned items and compute what still needs farming.

Warframe has no official public per-player inventory API, so owned items and
the wishlist are supplied by the player as local files. Both files are plain
JSON lists of item-name strings, e.g.::

    ["Volt Prime Neuroptics", "Soma Prime Barrel"]

Matching against drop-table names is done case-insensitively after trimming
whitespace, so the player's files do not have to match the API's exact casing.
"""

from __future__ import annotations

import json
from pathlib import Path

# Single source of truth for name matching, shared across the package.
from .items import normalize as _normalize


def load_item_list(path: str | Path) -> set[str]:
    """Load a JSON list of item names into a normalized set."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of item-name strings")
    return {_normalize(str(item)) for item in data}


def compute_needed(wishlist: set[str], owned: set[str]) -> set[str]:
    """Items the player wants but does not yet own (normalized names)."""
    return wishlist - owned
