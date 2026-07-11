"""Auto-sync owned items from a player's public Warframe profile.

Warframe exposes a public profile endpoint keyed by **Account ID** (a 24-hex
Mongo ObjectId — the ``gid`` cookie on warframe.com, or the id logged in
``%localappdata%\\Warframe\\EE.log``). This is *not* the in-game username.

    https://api.warframe.com/cdn/getProfileViewingData.php?playerId=<ID>

The response shape (confirmed against WFCD/profile-parser) is::

    { "Results": [ { "DisplayName": ...,
                     "LoadOutInventory": { "XPInfo": [ {"ItemType": "<uniqueName>",
                                                        "XP": <int>}, ... ] } } ] }

``XPInfo`` lists every item the player has gained mastery affinity on — i.e.
everything they have built/owned. ``ItemType`` is an internal uniqueName such as
``/Lotus/Powersuits/Volt/VoltPrime``; :func:`resolve_names` turns those into
display names ("Volt Prime") via the warframestat items dataset so they line up
with drop-table item names.

Note: mastery is tracked per *built equipment*, not per Prime *component*. So a
player who has mastered "Volt Prime" owns the finished frame, which implies they
no longer need any of its parts. Expanding owned equipment into the parts it
subsumes is the optimizer's job, not this module's.
"""

from __future__ import annotations

import re

import requests

from . import items

PROFILE_URL = "https://api.warframe.com/cdn/getProfileViewingData.php"

ACCOUNT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")


class InvalidAccountId(ValueError):
    pass


def fetch_profile(account_id: str, timeout: int = 30) -> dict:
    """Fetch the raw public profile JSON for an Account ID."""
    account_id = account_id.strip()
    if not ACCOUNT_ID_RE.match(account_id):
        raise InvalidAccountId(
            f"{account_id!r} is not a 24-hex Account ID. This is NOT your "
            "username — find it in the 'gid' cookie on warframe.com or in EE.log."
        )
    resp = requests.get(PROFILE_URL, params={"playerId": account_id}, timeout=timeout)
    # A well-formed but non-existent Account ID doesn't 404 here — the API
    # returns 409 Conflict instead. Both mean "no such account," not a
    # transient failure, so both become the same clean InvalidAccountId
    # rather than an uncaught HTTPError with a raw traceback.
    if resp.status_code in (404, 409):
        raise InvalidAccountId(f"No public profile found for Account ID {account_id}.")
    resp.raise_for_status()
    return resp.json()


def owned_unique_names(profile: dict) -> set[str]:
    """Extract the set of mastered/owned item uniqueNames from a profile."""
    results = profile.get("Results") or []
    if not results:
        return set()
    xp_info = (results[0].get("LoadOutInventory") or {}).get("XPInfo") or []
    return {
        entry["ItemType"]
        for entry in xp_info
        if isinstance(entry, dict) and entry.get("ItemType")
    }


def resolve_names(unique_names: set[str], items_data: list[dict] | None = None) -> set[str]:
    """Map internal uniqueNames to display names via the items dataset.

    Uses the same cached dataset as the rest of the pipeline. Only **masterable
    equipment** is considered, so mastered star-chart nodes (which also grant MR
    and share display names with frames, e.g. the "Caliban" node) cannot leak in
    as owned gear. Unknown uniqueNames are skipped; returned names are raw.
    """
    if not unique_names:
        return set()
    data = items_data if items_data is not None else items.load_items()
    by_unique = {
        it["uniqueName"]: it["name"]
        for it in data
        if it.get("masterable") and it.get("uniqueName") and it.get("name")
        and it.get("type") != "Node"
    }
    return {by_unique[u] for u in unique_names if u in by_unique}


def fetch_owned(account_id: str) -> set[str]:
    """Convenience: Account ID -> set of owned item display names."""
    profile = fetch_profile(account_id)
    return resolve_names(owned_unique_names(profile))
