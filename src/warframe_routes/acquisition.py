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
part only if `items.is_part_component` says so (`/Recipes/`, or a Necramech
vault part — see that function's docstring for why the latter needs its own
marker: no drop table lists Isolation Vault rewards, so without this a needed
Necramech part silently vanishes from the plan rather than being surfaced as
"no known source", which is what :mod:`service` does for it).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import effort
from .data import Node
from .items import (base_relic_name, is_part_component, normalize,
                     part_display_name, parse_location, relic_refinement)


@dataclass
class AcquisitionPlan:
    direct_nodes: list[Node]                  # non-Prime: nodes for set-cover
    direct_parts: set[str]                    # non-Prime farmable parts (normalized)
    prime_part_relics: dict[str, set[str]]    # norm part -> {relic display} in rotation
    part_display: dict[str, str]              # normalized part -> display name
    part_equipment: dict[str, str]            # normalized part -> owning equipment
    not_farmable: set[str] = field(default_factory=set)        # vaulted parts (norm)
    no_mission_source: set[str] = field(default_factory=set)   # equipment (display)
    orphan_parts: dict[str, str] = field(default_factory=dict) # norm -> display; parts
    # with /Recipes/ but no mission/relic drop (e.g. warframe main BPs from Market)
    special_source_parts: dict[str, set[str]] = field(default_factory=dict)
    # norm part -> {raw location strings} for non-standard sources (Sanctuary Onslaught,
    # Plains of Eidolon, etc.) whose location format doesn't match planet/node pattern

    # --- Drop chances for the expected-effort model (all chances are percent) ---
    node_part_chance: dict[str, dict[str, float]] = field(default_factory=dict)
    # node.key -> {norm part -> drop chance %} for non-Prime node drops
    node_rotation: dict[str, str | None] = field(default_factory=dict)
    # node.key -> rotation letter (A/B/C) or None for non-endless nodes
    part_relic_refine_chance: dict[str, dict[str, dict[str, float]]] = field(
        default_factory=dict)
    # norm part -> norm relic -> {refinement -> in-relic chance %}
    relic_source: dict[str, tuple[float, str, str | None, str | None]] = field(default_factory=dict)
    # norm relic -> (best acquisition chance %, game mode, rotation, node display name)

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


def _relic_drops(rewards):
    """Yield (norm relic, display, chance %, rotation) for every relic in a node's rewards."""
    if isinstance(rewards, dict):
        for rot_key, lst in rewards.items():
            if not isinstance(lst, list):
                continue
            rotation = rot_key.upper() if rot_key.upper() in ("A", "B", "C") else None
            for r in lst:
                name = r.get("itemName", "") if isinstance(r, dict) else ""
                if "Relic" in name:
                    base = base_relic_name(name)
                    yield normalize(base), base, (r.get("chance") or 0.0), rotation
    elif isinstance(rewards, list):
        for r in rewards:
            name = r.get("itemName", "") if isinstance(r, dict) else ""
            if "Relic" in name:
                base = base_relic_name(name)
                yield normalize(base), base, (r.get("chance") or 0.0), None


def build_plan(
    items: list[dict],
    mission_rewards_raw: dict,
    needed_equipment: set[str],
    active_bounty: set[str] | None = None,
) -> AcquisitionPlan:
    """Construct the acquisition plan for a set of missing equipment (normalized)."""
    index = {normalize(it.get("name", "")): it for it in items if it.get("name")}

    part_relics: dict[str, set[str]] = defaultdict(set)   # norm part -> {norm relic}
    relic_display: dict[str, str] = {}                    # norm relic -> display
    part_display: dict[str, str] = {}
    part_equipment: dict[str, str] = {}
    direct_node_acc: dict[tuple[str, str], list] = {}     # (planet,node)->[p,n,m,parts]
    equipment_with_parts: set[str] = set()
    routed_parts: set[str] = set()   # parts placed in prime or non-prime routes
    special_source_parts: dict[str, set[str]] = defaultdict(set)  # norm part -> {locations}
    # Chance accumulators for the effort model (percent).
    node_part_chance_acc: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    part_relic_chance_acc: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict))

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
            # Real buildable parts live under /Recipes/ (or are Necramech vault
            # parts, see items.is_part_component); a component drop pointing
            # anywhere else (Cryotic, Neurodes, Salvage, ...) is a raw resource.
            if not is_part_component(comp.get("uniqueName") or ""):
                continue
            for drop in comp.get("drops") or []:
                loc = (drop or {}).get("location", "")
                disp = drop.get("type") or part_display_name(equip_name, comp.get("name", ""))
                pnorm = normalize(disp)
                chance = (drop or {}).get("chance") or 0.0
                if "Relic" in loc:
                    base = base_relic_name(loc)
                    rnorm = normalize(base)
                    part_relics[pnorm].add(rnorm)
                    relic_display[rnorm] = base
                    part_relic_chance_acc[pnorm][rnorm][relic_refinement(loc)] = chance
                    register(pnorm, disp, equip_name)
                    routed_parts.add(pnorm)
                else:
                    parsed = parse_location(loc)
                    if parsed:
                        planet, node_name, mode, rotation = parsed
                        # When live worldstate is available and the mode is a bounty
                        # type, only include the drop if the item is in the current
                        # active pool. Event bounties (Ghoul Purge, Plague Star, …)
                        # are absent from the worldstate when the event is not running.
                        is_bounty = "Bounty" in mode
                        if (is_bounty and active_bounty is not None
                                and pnorm not in active_bounty):
                            # Item not in any current bounty pool → event-only source.
                            # Redirect to special_source so it appears in the UI with
                            # a note rather than silently disappearing.
                            label = f"{node_name} (event bounty — not currently active)"
                            special_source_parts[pnorm].add(label)
                            register(pnorm, disp, equip_name)
                            routed_parts.add(pnorm)
                            continue
                        # Different rotations of one node are distinct reward
                        # pools, so they stay distinct "nodes" (and cost more
                        # time the deeper the rotation).
                        disp_name = (f"{node_name} · Rot {rotation}"
                                     if rotation else node_name)
                        key = (planet, disp_name)
                        slot = direct_node_acc.setdefault(
                            key, [planet, disp_name, mode, rotation, set()])
                        slot[4].add(pnorm)
                        # Keep the best (highest) chance if a part lists the node twice.
                        prev = node_part_chance_acc[key].get(pnorm, 0.0)
                        node_part_chance_acc[key][pnorm] = max(prev, chance)
                        register(pnorm, disp, equip_name)
                        routed_parts.add(pnorm)
                    elif loc.strip():
                        # Non-standard source: Sanctuary Onslaught, Plains of Eidolon,
                        # Elite Sanctuary Onslaught, etc. — has a location string but not
                        # in planet/node format. Track for display; don't try to route.
                        special_source_parts[pnorm].add(loc.strip())
                        register(pnorm, disp, equip_name)
                        routed_parts.add(pnorm)

    # Detect orphan parts: have /Recipes/ and zero drop locations at all.
    # Classic example: warframe main blueprints sold only in the Market.
    # Parts with unrecognized drop locations (e.g. Sanctuary Onslaught for Baruuk)
    # are NOT orphans — they have a source, we just can't route them as missions.
    orphan_parts: dict[str, str] = {}
    for equip_norm in needed_equipment:
        it = index.get(equip_norm)
        if not it:
            continue
        equip_name = it["name"]
        for comp in it.get("components") or []:
            if not is_part_component(comp.get("uniqueName") or ""):
                continue
            drops = comp.get("drops") or []
            disp = (
                next((d.get("type") for d in drops if d.get("type")), None)
                or part_display_name(equip_name, comp.get("name", ""))
            )
            pnorm = normalize(disp)
            if pnorm not in routed_parts:
                # Only Market-only if truly no drop locations in the dataset.
                has_location = any((d or {}).get("location", "").strip() for d in drops)
                if not has_location:
                    orphan_parts[pnorm] = disp
                    part_display[pnorm] = disp
                    part_equipment[pnorm] = equip_name
                    equipment_with_parts.add(equip_name)

    # Which relics are currently in rotation (appear in the live drop tables)?
    # Also record, per relic, the best (highest-chance) node to farm it and that
    # node's game mode — needed to estimate relic-acquisition effort.
    # For each relic keep the node that's *fastest* to farm it, i.e. minimizes
    # expected time per relic = (1/chance) * mode_minutes — not merely the highest
    # drop chance. A quick Capture at 6% beats a slow Survival-rot-C at 10%.
    available: dict[str, str] = {}
    relic_source: dict[str, tuple[float, str, str | None, str | None]] = {}
    relic_best_time: dict[str, float] = {}
    root = mission_rewards_raw.get("missionRewards", mission_rewards_raw)
    for planet, planet_nodes in (root.items() if isinstance(root, dict) else []):
        if not isinstance(planet_nodes, dict):
            continue
        for node_key, node_data in planet_nodes.items():
            if not isinstance(node_data, dict):
                continue
            mode = node_data.get("gameMode", "Unknown")
            node_label = f"{planet} / {node_key}"
            for rnorm, display, chance, rotation in _relic_drops(node_data.get("rewards", {})):
                available[rnorm] = display
                if chance <= 0:
                    relic_source.setdefault(rnorm, (chance, mode, rotation, node_label))
                    continue
                rot_factor = effort.rotation_factor(rotation)
                farm_time = (100.0 / chance) * effort.mode_minutes(mode) * rot_factor
                if farm_time < relic_best_time.get(rnorm, float("inf")):
                    relic_best_time[rnorm] = farm_time
                    relic_source[rnorm] = (chance, mode, rotation, node_label)

    # Prime parts: keep only relics currently in rotation; vaulted parts split off.
    prime_part_relics: dict[str, set[str]] = {}
    not_farmable: set[str] = set()
    for pnorm, relics in part_relics.items():
        live = {available[r] for r in relics if r in available}
        if live:
            prime_part_relics[pnorm] = live
        else:
            not_farmable.add(pnorm)

    direct_parts = {p for _, _, _, _, parts in direct_node_acc.values() for p in parts}
    node_rotation = {
        f"{planet} - {disp_name}": rotation
        for planet, disp_name, _, rotation, _ in direct_node_acc.values()
    }
    direct_nodes = [
        Node(planet=p, name=n, game_mode=m, items=frozenset(parts))
        for p, n, m, _, parts in direct_node_acc.values()
    ]
    # Re-key node->part chances by Node.key ("planet - name") for the service.
    node_part_chance = {
        f"{planet} - {node_name}": dict(chances)
        for (planet, node_name), chances in node_part_chance_acc.items()
    }
    part_relic_refine_chance = {
        p: {r: dict(refs) for r, refs in relics.items()}
        for p, relics in part_relic_chance_acc.items()
    }

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
        orphan_parts=orphan_parts,
        special_source_parts=dict(special_source_parts),
        node_part_chance=node_part_chance,
        node_rotation=node_rotation,
        part_relic_refine_chance=part_relic_refine_chance,
        relic_source=relic_source,
    )
