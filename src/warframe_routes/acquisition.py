"""The acquisition chain: equipment -> parts -> where to get them.

Two very different farming models, because the game works differently:

* **Prime parts** come from **relics**, and you cannot farm a *specific* relic —
  you farm its **tier** (Lith/Meso/Neo/Axi) at a good node and crack relics at a
  void fissure. So for Primes we don't route mission nodes; we tell you, per part,
  which (in-rotation) relic drops it, and let the caller print a tier farming
  guide. Vaulted parts (no relic currently dropping) are reported separately.

* **Non-Prime parts** drop straight from a specific boss/mission node, so those
  *are* a fewest-missions set-cover over nodes (`direct_nodes`/`direct_parts`),
  fed to :func:`warframe_routes.optimize.optimize_route`.

Availability is decided by the live mission drop tables: a relic is in rotation
iff it currently appears as a mission reward. A component counts as a farmable
part only if its `uniqueName` is under `/Recipes/` (filters out raw resources).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .data import Node
from .items import base_relic_name, normalize, parse_location


@dataclass
class AcquisitionPlan:
    direct_nodes: list[Node]                  # non-Prime: nodes for set-cover
    direct_parts: set[str]                    # non-Prime farmable parts (normalized)
    prime_part_relics: dict[str, set[str]]    # norm part -> {relic display} in rotation
    part_display: dict[str, str]              # normalized part -> display name
    part_equipment: dict[str, str]            # normalized part -> owning equipment
    not_farmable: set[str] = field(default_factory=set)        # vaulted parts (norm)
    no_mission_source: set[str] = field(default_factory=set)   # equipment (display)

    def vaulted_equipment(self) -> set[str]:
        """Equipment whose every part is currently not farmable (fully vaulted)."""
        farmable = self.direct_parts | set(self.prime_part_relics)
        by_equip: dict[str, list[str]] = defaultdict(list)
        for part in farmable | self.not_farmable:
            by_equip[self.part_equipment[part]].append(part)
        return {
            equip for equip, parts in by_equip.items()
            if all(p in self.not_farmable for p in parts)
        }


def _relics_in_rewards(rewards) -> dict[str, str]:
    """Map normalized base relic name -> display name for a node's rewards."""
    if isinstance(rewards, dict):
        lists = rewards.values()
    elif isinstance(rewards, list):
        lists = [rewards]
    else:
        return {}
    found: dict[str, str] = {}
    for lst in lists:
        if not isinstance(lst, list):
            continue
        for r in lst:
            name = r.get("itemName", "") if isinstance(r, dict) else ""
            if "Relic" in name:
                base = base_relic_name(name)
                found[normalize(base)] = base
    return found


def build_plan(
    items: list[dict],
    mission_rewards_raw: dict,
    needed_equipment: set[str],
) -> AcquisitionPlan:
    """Construct the acquisition plan for a set of missing equipment (normalized)."""
    index = {normalize(it.get("name", "")): it for it in items if it.get("name")}

    part_relics: dict[str, set[str]] = defaultdict(set)   # norm part -> {norm relic}
    relic_display: dict[str, str] = {}                    # norm relic -> display
    part_display: dict[str, str] = {}
    part_equipment: dict[str, str] = {}
    direct_node_acc: dict[tuple[str, str], list] = {}     # (planet,node)->[p,n,m,parts]
    equipment_with_parts: set[str] = set()

    def register(pnorm, disp, equip):
        part_display[pnorm] = disp
        part_equipment[pnorm] = equip
        equipment_with_parts.add(equip)

    for equip_norm in needed_equipment:
        it = index.get(equip_norm)
        if not it:
            continue
        equip_name = it["name"]
        for comp in it.get("components") or []:
            # Real buildable parts live under /Recipes/; a component drop pointing
            # anywhere else (Cryotic, Neurodes, Salvage, ...) is a raw resource.
            if "/Recipes/" not in (comp.get("uniqueName") or ""):
                continue
            for drop in comp.get("drops") or []:
                loc = (drop or {}).get("location", "")
                disp = drop.get("type") or f"{equip_name} {comp.get('name', '')}".strip()
                pnorm = normalize(disp)
                if "Relic" in loc:
                    base = base_relic_name(loc)
                    rnorm = normalize(base)
                    part_relics[pnorm].add(rnorm)
                    relic_display[rnorm] = base
                    register(pnorm, disp, equip_name)
                else:
                    parsed = parse_location(loc)
                    if not parsed:
                        continue
                    planet, node_name, mode = parsed
                    slot = direct_node_acc.setdefault(
                        (planet, node_name), [planet, node_name, mode, set()])
                    slot[3].add(pnorm)
                    register(pnorm, disp, equip_name)

    # Which relics are currently in rotation (appear in the live drop tables)?
    available: dict[str, str] = {}
    root = mission_rewards_raw.get("missionRewards", mission_rewards_raw)
    for planet_nodes in root.values() if isinstance(root, dict) else []:
        if not isinstance(planet_nodes, dict):
            continue
        for node_data in planet_nodes.values():
            if isinstance(node_data, dict):
                available.update(_relics_in_rewards(node_data.get("rewards", {})))

    # Prime parts: keep only relics currently in rotation; vaulted parts split off.
    prime_part_relics: dict[str, set[str]] = {}
    not_farmable: set[str] = set()
    for pnorm, relics in part_relics.items():
        live = {available[r] for r in relics if r in available}
        if live:
            prime_part_relics[pnorm] = live
        else:
            not_farmable.add(pnorm)

    direct_parts = {p for _, _, _, parts in direct_node_acc.values() for p in parts}
    direct_nodes = [
        Node(planet=p, name=n, game_mode=m, items=frozenset(parts))
        for p, n, m, parts in direct_node_acc.values()
    ]

    no_mission_source = {
        index[e]["name"]
        for e in needed_equipment
        if e in index and index[e]["name"] not in equipment_with_parts
    }

    return AcquisitionPlan(
        direct_nodes=direct_nodes,
        direct_parts=direct_parts,
        prime_part_relics=prime_part_relics,
        part_display=part_display,
        part_equipment=part_equipment,
        not_farmable=not_farmable,
        no_mission_source=no_mission_source,
    )
