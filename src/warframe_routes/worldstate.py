"""Fetch and cache live worldstate data from WFCD.

``syndicateMissions`` tells us which open-world bounty jobs are currently active
and what items are in each job's reward pool.  We use this to filter out items
that only appear in event bounties (Ghoul Purge, Plague Star, …) when the event
is not running — so the router doesn't send players to a bounty that doesn't
exist today.

TTL is 15 minutes: open-world bounties rotate every 2.5–3 hours, so this is a
reasonable balance between accuracy and network calls.
"""

from __future__ import annotations

import json
import time

import requests

from .data import CACHE_DIR
from .items import normalize

SYNDICATE_MISSIONS_URL = "https://api.warframestat.us/pc/syndicateMissions"
_CACHE_FILE = CACHE_DIR / "syndicateMissions.json"
_TTL = 15 * 60  # seconds


def load_syndicate_missions(force_refresh: bool = False) -> list:
    """Return the raw syndicateMissions list, cached for 15 minutes."""
    if not force_refresh and _CACHE_FILE.exists():
        if time.time() - _CACHE_FILE.stat().st_mtime < _TTL:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))

    resp = requests.get(SYNDICATE_MISSIONS_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    return data


def active_bounty_items(missions: list) -> set[str]:
    """Return normalized item names currently in any syndicate job reward pool."""
    result: set[str] = set()
    for mission in missions:
        if not isinstance(mission, dict):
            continue
        for job in mission.get("jobs", []):
            if not isinstance(job, dict):
                continue
            for item in job.get("rewardPool", []):
                if isinstance(item, str) and item:
                    result.add(normalize(item))
    return result
