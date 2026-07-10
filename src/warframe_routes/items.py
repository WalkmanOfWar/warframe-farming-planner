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
ITEMS_FIELDS = "name,uniqueName,vaulted,type,masterable,components,imageName"

CACHE_DIR = Path.home() / ".cache" / "warframe-optimize-routes"
CACHE_FILE = CACHE_DIR / "items.v2.json"  # v2: added imageName field
CACHE_TTL_SECONDS = 24 * 60 * 60

# Relics appear in component drops with refinement suffixes; missionRewards uses
# the base name. Strip "(Exceptional|Flawless|Radiant)" to match the two.
_REFINEMENT_RE = re.compile(r"\s*\((?:Exceptional|Flawless|Radiant)\)\s*$")
_REFINEMENT_NAME_RE = re.compile(r"\((Exceptional|Flawless|Radiant)\)")


def base_relic_name(location: str) -> str:
    return _REFINEMENT_RE.sub("", location or "").strip()


def relic_refinement(location: str) -> str:
    """Refinement encoded in a relic drop location; bare name means Intact.

    'Axi N3 Relic' -> 'Intact';  'Axi N3 Relic (Radiant)' -> 'Radiant'.
    """
    m = _REFINEMENT_NAME_RE.search(location or "")
    return m.group(1) if m else "Intact"


def relic_tier(relic_display: str) -> str:
    """First token of a relic name is its tier, e.g. 'Axi C10 Relic' -> 'Axi'."""
    return (relic_display or "").split(" ", 1)[0]


# Direct (non-relic) component drops look like "Venus/Fossa (Assassination)",
# "Duviri/Endless: Tier 6 (Normal)" or, for endless nodes, with a trailing
# rotation: "Eris/Oestrus (Infested Salvage), Rotation C".
_LOCATION_RE = re.compile(r"^(?P<planet>[^/]+)/(?P<rest>.+)$")
_MODE_RE = re.compile(r"^(?P<node>.+?)\s*\((?P<mode>[^)]*)\)\s*$")
_ROTATION_RE = re.compile(r",\s*Rotation\s+(?P<rot>[A-C])\s*$", re.IGNORECASE)


def parse_location(location: str) -> tuple[str, str, str, str | None] | None:
    """Parse a mission drop location into (planet, node, game_mode, rotation).

    ``rotation`` is "A"/"B"/"C" for endless nodes that name one, else None.
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
    rotation = None
    rm = _ROTATION_RE.search(rest)
    if rm:
        rotation = rm.group("rot").upper()
        rest = rest[:rm.start()].strip()
    mm = _MODE_RE.match(rest)
    if mm:
        return planet, mm.group("node").strip(), mm.group("mode").strip(), rotation
    return planet, rest, "Unknown", rotation


def normalize(name: str) -> str:
    return (name or "").strip().casefold()


# A component counts as a farmable "part" (as opposed to a generic stackable
# resource like Cryotic/Neurodes/Orokin Cell) if its uniqueName matches one of
# these path markers. /Recipes/ covers ordinary Foundry blueprints; the second
# marker covers Necramech vault parts (Voidrig/Bonewidow/Morgha/Cortege) —
# one-per-item components exactly like a Chassis/Systems, but WFCD names them
# under /InfestedMicroplanet/Resources/Mechs/ since they're won from Isolation
# Vault runs rather than built in the Foundry from a bought blueprint. Without
# this they're indistinguishable from a generic resource and silently vanish
# from both the acquisition chain and owned-parts matching.
PART_PATH_MARKERS = ("/Recipes/", "/InfestedMicroplanet/Resources/Mechs/")


def is_part_component(uniq: str) -> bool:
    return any(marker in (uniq or "") for marker in PART_PATH_MARKERS)


def part_display_name(equip_name: str, comp_name: str) -> str:
    """Fallback display name for a part with no drop-table ``type`` string.

    Normally ``"<Equipment> <Component>"`` (e.g. "Volt Prime" + "Chassis" ->
    "Volt Prime Chassis"). Necramech vault-part components are a WFCD-dataset
    exception: their own ``name`` already includes the equipment name (e.g.
    "Voidrig Capsule", not "Capsule"), so blindly prefixing it again would
    produce "Voidrig Voidrig Capsule" — detect and skip the duplicate prefix.
    """
    comp_name = (comp_name or "").strip()
    equip_name = (equip_name or "").strip()
    if comp_name.casefold().startswith(equip_name.casefold()):
        return comp_name
    return f"{equip_name} {comp_name}".strip()


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
