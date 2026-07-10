"""Fetch and cache live worldstate data from WFCD.

``syndicateMissions`` tells us which open-world bounty jobs are currently active
and what items are in each job's reward pool.  We use this to filter out items
that only appear in event bounties (Ghoul Purge, Plague Star, …) when the event
is not running — so the router doesn't send players to a bounty that doesn't
exist today.

Further sections consumed via :func:`load_section`:

* ``fissures`` — which void-fissure tiers are open *right now* and where, so the
  Prime plan can say "a Lith Capture is live at Adaro" instead of only "farm a
  Lith fissure";
* ``voidTrader`` — Baro Ki'Teer's current stock, cross-referenced against
  needed no-mission-source gear;
* ``invasions`` — running invasions whose rewards (Wraith/Vandal parts, …)
  match needed items;
* ``vaultTrader`` — Varzia's Prime Resurgence stock, the only non-trade way to
  buy fully-vaulted Prime gear, cross-referenced against ``vaulted_equipment``;
* ``dailyDeals`` — Darvo's single rotating discounted item.

TTL is 15 minutes: open-world bounties rotate every 2.5–3 hours and fissures
every few minutes-to-hours, so this is a reasonable accuracy/traffic balance.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import requests

from .data import CACHE_DIR
from .items import normalize

WORLDSTATE_BASE = "https://api.warframestat.us/pc/"
SYNDICATE_MISSIONS_URL = WORLDSTATE_BASE + "syndicateMissions"
_CACHE_FILE = CACHE_DIR / "syndicateMissions.json"
_TTL = 15 * 60  # seconds


def load_section(name: str, force_refresh: bool = False):
    """Fetch one worldstate section (``fissures``, ``voidTrader``,
    ``invasions``, …), cached for 15 minutes per section."""
    cache_file = CACHE_DIR / f"ws_{name}.json"
    if not force_refresh and cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < _TTL:
            return json.loads(cache_file.read_text(encoding="utf-8"))
    resp = requests.get(WORLDSTATE_BASE + name, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


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


def _not_expired(iso: str | None) -> bool:
    if not iso:
        return True  # missing expiry — assume live rather than hide it
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except ValueError:
        return True


def active_fissures(fissures: list) -> list[dict]:
    """Live fissures as ``{tier, node, mission, hard, storm, expiry}`` dicts."""
    out: list[dict] = []
    for f in fissures or []:
        if not isinstance(f, dict) or not _not_expired(f.get("expiry")):
            continue
        tier = f.get("tier")
        if not tier:
            continue
        out.append({
            "tier": tier,
            "node": f.get("node", "?"),
            "mission": f.get("missionType", "?"),
            "hard": bool(f.get("isHard")),
            "storm": bool(f.get("isStorm")),
            "expiry": f.get("expiry"),
        })
    return out


def fissure_node_tiers(fissures_live: list[dict]) -> dict[str, str]:
    """Map ``"planet|node"`` (casefolded) → fissure tier for live non-storm
    fissures, so plan nodes can be matched against currently-open fissures.

    Worldstate names nodes ``"Adaro (Sedna)"``; the plan uses ``"Sedna - Adaro"``.
    """
    idx: dict[str, str] = {}
    for f in fissures_live:
        if f.get("storm"):
            continue  # Railjack void storms aren't the same node
        node = f.get("node", "")
        if "(" in node and node.endswith(")"):
            name, planet = node[:-1].rsplit("(", 1)
            idx[f"{planet.strip()}|{name.strip()}".casefold()] = f["tier"]
    return idx


def baro_stock(trader: dict) -> dict | None:
    """Baro's live inventory as ``{location, until, items: {norm: display}}``,
    or None when he isn't currently trading (inventory is empty between visits)."""
    if not isinstance(trader, dict):
        return None
    inv = trader.get("inventory") or []
    stock = {normalize(e["item"]): e["item"]
             for e in inv if isinstance(e, dict) and e.get("item")}
    if not stock or not _not_expired(trader.get("expiry")):
        return None
    return {"location": trader.get("location", "?"),
            "until": trader.get("expiry"), "items": stock}


def _is_equipment_uniq(uniq: str) -> bool:
    """True for a store uniqueName that is actual gear (frame/weapon), not a
    bundle package, skin, syandana, ephemera, or ship decoration."""
    if any(seg in uniq for seg in ("/Packages/", "/Skins/", "/Upgrades/", "ShipDecos")):
        return False
    return "/Powersuits/" in uniq or "/Weapons/" in uniq


def vault_trader_stock(trader: dict) -> dict | None:
    """Varzia's (Prime Resurgence) live stock as ``{location, until, items:
    {norm: display}}``, or None when she isn't currently trading.

    Prime Resurgence sells direct plat/Regal-Aya access to previously-vaulted
    Prime gear — the *only* way to get a fully-vaulted item without trading —
    so this is cross-referenced against ``vaulted_equipment``, not the normal
    drop-based plan. Store item names are inconsistent (``"Prime Corinth"``
    instead of ``"Corinth Prime"``, trailing ``" Weapon"``), so both the raw
    name and a word-order-flipped variant are indexed; bundle packages,
    skins, syandanas and other cosmetics are excluded.
    """
    if not isinstance(trader, dict):
        return None
    inv = trader.get("inventory") or []
    if not inv or not _not_expired(trader.get("expiry")):
        return None
    stock: dict[str, str] = {}
    for e in inv:
        if not isinstance(e, dict):
            continue
        raw = (e.get("item") or "").strip()
        uniq = e.get("uniqueName") or ""
        if not raw or not _is_equipment_uniq(uniq):
            continue
        candidates = [raw]
        if raw.endswith(" Weapon"):
            candidates.append(raw[: -len(" Weapon")].strip())
        if raw.startswith("Prime "):
            candidates.append(f"{raw[len('Prime '):]} Prime")
        for c in candidates:
            stock.setdefault(normalize(c), c)
    if not stock:
        return None
    return {"location": trader.get("location", "?"),
            "until": trader.get("expiry"), "items": stock}


def daily_deal(deals: list) -> dict | None:
    """Darvo's current single-item daily deal as ``{item, discount, expiry}``,
    or None when the feed is empty/expired."""
    for d in deals or []:
        if not isinstance(d, dict) or not d.get("item"):
            continue
        if not _not_expired(d.get("expiry")):
            continue
        return {"item": d["item"], "discount": d.get("discount"),
                "expiry": d.get("expiry")}
    return None


def invasion_rewards(invasions: list) -> dict[str, set[str]]:
    """Normalized reward item → {invasion descriptions} for running invasions."""
    result: dict[str, set[str]] = {}
    for inv in invasions or []:
        if not isinstance(inv, dict) or inv.get("completed"):
            continue
        node = inv.get("node", "?")
        for side in ("attacker", "defender"):
            reward = (inv.get(side) or {}).get("reward") or {}
            names = list(reward.get("items") or [])
            names += [c.get("type") or c.get("key", "")
                      for c in reward.get("countedItems") or []
                      if isinstance(c, dict)]
            faction = (inv.get(side) or {}).get("faction", "")
            desc = f"Invasion — {node} (side with {faction})" if faction else f"Invasion — {node}"
            for n in names:
                if n:
                    result.setdefault(normalize(n), set()).add(desc)
    return result
