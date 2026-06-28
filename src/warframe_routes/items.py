"""The full item dataset (with components/recipes), cached on disk.

Used by the acquisition chain to expand finished equipment into the parts you
must farm and to find which relics drop each part. Pulled once from the
warframestat items API (a ~9 MB slim projection) and cached like the drop data.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ITEMS_URL = "https://api.warframestat.us/items"
ITEMS_FIELDS = "name,uniqueName,vaulted,type,masterable,components"

CACHE_DIR = Path.home() / ".cache" / "warframe-optimize-routes"
CACHE_FILE = CACHE_DIR / "items.json"
CACHE_TTL_SECONDS = 24 * 60 * 60

# Relics appear in component drops with refinement suffixes; missionRewards uses
# the base name. Strip "(Exceptional|Flawless|Radiant)" to match the two.
_REFINEMENT_RE = re.compile(r"\s*\((?:Exceptional|Flawless|Radiant)\)\s*$")


def base_relic_name(location: str) -> str:
    return _REFINEMENT_RE.sub("", location or "").strip()


def relic_tier(relic_display: str) -> str:
    """First token of a relic name is its tier, e.g. 'Axi C10 Relic' -> 'Axi'."""
    return (relic_display or "").split(" ", 1)[0]


# Direct (non-relic) component drops look like "Venus/Fossa (Assassination)" or
# "Duviri/Endless: Tier 6 (Normal)": "<planet>/<node> (<mode>)".
_LOCATION_RE = re.compile(r"^(?P<planet>[^/]+)/(?P<rest>.+)$")
_MODE_RE = re.compile(r"^(?P<node>.+?)\s*\((?P<mode>[^)]*)\)\s*$")


def parse_location(location: str) -> tuple[str, str, str] | None:
    """Parse a mission drop location into (planet, node, game_mode).

    Returns None for locations that are not mission nodes (e.g. relics, or
    sources like market/clan that have no "<planet>/<node>" shape).
    """
    if not location or "Relic" in location or "/" not in location:
        return None
    m = _LOCATION_RE.match(location.strip())
    if not m:
        return None
    planet = m.group("planet").strip()
    rest = m.group("rest").strip()
    mm = _MODE_RE.match(rest)
    if mm:
        return planet, mm.group("node").strip(), mm.group("mode").strip()
    return planet, rest, "Unknown"


def normalize(name: str) -> str:
    return (name or "").strip().casefold()


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    return (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_TTL_SECONDS


def load_items(force_refresh: bool = False) -> list[dict]:
    """Return the slim item dataset, using the on-disk cache when fresh."""
    if not force_refresh and _cache_is_fresh():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    resp = requests.get(ITEMS_URL, params={"only": ITEMS_FIELDS}, timeout=120)
    resp.raise_for_status()
    raw = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(raw), encoding="utf-8")
    return raw
