"""Parse a private inventory export (loose parts the public profile can't see).

The public profile (`sync.py`) only reports *built/mastered* gear. The full
inventory — including loose Prime parts sitting unbuilt in your pockets — is only
available from the authenticated game endpoint
``mobile.warframe.com/api/inventory.php?accountId=...&nonce=...``. Read-only helpers
(AlecaFrame, Sainan's warframe-api-helper) grab that while the game is running and
save it as ``inventory.json``; this module consumes that file. No credentials are
handled here.

The inventory JSON is a flat object of arrays of ``{"ItemType": <uniqueName>,
"ItemCount": N, ...}``. We don't care which array an entry is in:

* any entry whose uniqueName resolves to a **masterable item** is owned equipment
  (handled by :func:`warframe_routes.sync.resolve_names`);
* any entry whose uniqueName is a **component recipe** is a loose part — mapped to
  the same display name the acquisition chain uses (the component's drop ``type``).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import requests

from . import items

# Same host warframe-api-helper uses for nonce-authenticated inventory pulls.
INVENTORY_URL = "https://mobile.warframe.com/api/inventory.php"
_ACCOUNT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")


def load_inventory(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_helper(helper_path: str, timeout: int = 90) -> dict:
    """Run warframe-api-helper (game must be open) and read the inventory it writes.

    The helper reads the running game's session token from memory and saves
    ``inventory.json`` into its working directory. We run it inside our cache dir
    and load that file — no credentials pass through us.
    """
    workdir = items.CACHE_DIR
    workdir.mkdir(parents=True, exist_ok=True)
    out_file = workdir / "inventory.json"
    before = out_file.stat().st_mtime if out_file.exists() else 0
    try:
        proc = subprocess.run(
            [helper_path], cwd=str(workdir),
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        raise ValueError(f"warframe-api-helper not found at {helper_path!r}.")
    except subprocess.TimeoutExpired:
        raise ValueError("warframe-api-helper timed out (is Warframe running?).")

    fresh = out_file.exists() and out_file.stat().st_mtime > before
    if not fresh:
        raise ValueError(
            "Helper did not produce a fresh inventory.json — make sure Warframe is "
            f"running and logged in. Helper output: {proc.stdout.strip() or '(none)'}"
        )
    return load_inventory(out_file)


def fetch_inventory(account_id: str, nonce: str, timeout: int = 30) -> dict:
    """Download the full inventory directly, given a live session nonce.

    ``accountId`` + ``nonce`` come from the running game (e.g. warframe-api-helper
    prints them as ``?accountId=...&nonce=...``). The nonce is invalidated when the
    game closes. No password is involved. Raises ValueError on a bad/expired token.
    """
    account_id = account_id.strip()
    if not _ACCOUNT_ID_RE.match(account_id):
        raise ValueError(f"{account_id!r} is not a 24-hex Account ID.")
    resp = requests.get(
        INVENTORY_URL,
        params={"accountId": account_id, "nonce": str(nonce).strip()},
        timeout=timeout,
    )
    if resp.status_code in (400, 401, 403):
        raise ValueError(
            "Inventory request rejected — the nonce is likely expired (close/reopen "
            "happens on game exit). Grab a fresh accountId+nonce while the game runs."
        )
    resp.raise_for_status()
    return resp.json()


def collect_item_types(inventory: dict) -> set[str]:
    """Every ItemType across all inventory arrays, regardless of category."""
    types: set[str] = set()
    for value in inventory.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            if isinstance(entry, dict) and entry.get("ItemType"):
                if entry.get("ItemCount", 1) != 0:
                    types.add(entry["ItemType"])
    return types


def build_component_index(items_data: list[dict]) -> dict[str, str]:
    """Map a component recipe's uniqueName -> the part's display name.

    The display name matches what the acquisition chain emits (the component's
    drop ``type``), so a loose part in the inventory lines up with a needed part.
    """
    index: dict[str, str] = {}
    for it in items_data:
        for comp in it.get("components") or []:
            uniq = comp.get("uniqueName")
            if not uniq or not items.is_part_component(uniq):
                continue
            disp = next(
                (d["type"] for d in (comp.get("drops") or [])
                 if isinstance(d, dict) and d.get("type")),
                items.part_display_name(it.get("name", ""), comp.get("name", "")),
            )
            index[uniq] = disp
    return index


def owned_parts(inventory: dict, items_data: list[dict]) -> set[str]:
    """Display names of loose component parts present in the inventory."""
    index = build_component_index(items_data)
    return {
        index[u] for u in collect_item_types(inventory) if u in index
    }


_REFINEMENTS = {"Intact", "Exceptional", "Flawless", "Radiant"}


def owned_relics(inventory: dict, items_data: list[dict]) -> dict[str, int]:
    """Count relics held in the inventory, keyed by normalized base relic name.

    Relics live in the items dataset as void projections named
    ``"<Tier> <Code> <Refinement>"`` (e.g. ``"Axi A1 Intact"``) with a
    ``/Types/Game/Projections/`` uniqueName. The plan refers to relics by their
    *base* display name (``"Axi A1 Relic"``, refinement stripped), so counts are
    summed across refinements: any held copy can be cracked (or refined first).
    """
    proj_index: dict[str, str] = {}  # uniqueName -> normalized base relic name
    for it in items_data:
        uniq = it.get("uniqueName") or ""
        name = it.get("name") or ""
        if "/Types/Game/Projections/" not in uniq or not name:
            continue
        words = name.split()
        if len(words) >= 2 and words[-1] in _REFINEMENTS:
            base = " ".join(words[:-1]) + " Relic"
            proj_index[uniq] = items.normalize(base)

    counts: dict[str, int] = {}
    for value in inventory.values():
        if not isinstance(value, list):
            continue
        for entry in value:
            if not isinstance(entry, dict):
                continue
            rnorm = proj_index.get(entry.get("ItemType", ""))
            if rnorm:
                counts[rnorm] = counts.get(rnorm, 0) + int(entry.get("ItemCount", 1) or 0)
    return {r: n for r, n in counts.items() if n > 0}


def pending_owned(
    inventory: dict, items_data: list[dict]
) -> tuple[set[str], set[str]]:
    """Equipment and parts currently building in the foundry (PendingRecipes).

    When the *main* blueprint of a warframe/weapon is building (component named
    "Blueprint"), all its sub-parts have already been consumed — the item is
    committed and should count as owned so it disappears from the farming route.
    When a *sub-component* (Chassis / Neuroptics / Systems …) is building, count
    it as an owned loose part.

    Returns ``(equipment_normalized_names, part_display_names)``.
    """
    recipe_meta: dict[str, tuple[str, str, str]] = {}  # uniq → (item_name, comp_name, part_disp)
    for it in items_data:
        item_name = it.get("name", "")
        for comp in it.get("components") or []:
            uniq = comp.get("uniqueName", "")
            if not uniq or "/Recipes/" not in uniq:
                continue
            drops = comp.get("drops") or []
            part_disp = next(
                (d["type"] for d in drops if isinstance(d, dict) and d.get("type")),
                items.part_display_name(item_name, comp.get("name", "")),
            )
            recipe_meta[uniq] = (item_name, comp.get("name", ""), part_disp)

    equipment: set[str] = set()
    parts: set[str] = set()
    for entry in inventory.get("PendingRecipes", []):
        if not isinstance(entry, dict):
            continue
        uniq = entry.get("ItemType", "")
        if uniq not in recipe_meta:
            continue
        item_name, comp_name, part_disp = recipe_meta[uniq]
        if comp_name == "Blueprint":
            equipment.add(items.normalize(item_name))
        else:
            parts.add(part_disp)
    return equipment, parts
