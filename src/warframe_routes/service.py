"""Shared route-planning service used by both the CLI and the web backend.

Takes already-resolved ownership/target sets and returns a structured
:class:`RouteResult` (no printing, no I/O). The CLI formats it as text; the web
backend serializes it to JSON. This is the single source of truth for *how* a
plan is assembled from a built :class:`~warframe_routes.acquisition.AcquisitionPlan`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import acquisition, effort, inventory, items, optimize, worldstate
from .data import Node

# Best community spots to farm each relic tier (you farm a tier, not a relic).
RELIC_TIER_GUIDE = {
    "Lith": "Hepit (Void) - Capture, fast",
    "Meso": "Ukko (Void) - Capture  /  Olympus (Mars) - Disruption, Rot C",
    "Neo": "Ukko (Void) - Capture  /  Ur (Uranus) - Disruption, Rot B/C",
    "Axi": "Apollo (Lua) - Disruption, Rot B/C",
    "Requiem": "Kuva Siphon / Kuva Flood missions",
}
GENERIC_TIER_HINT = "farm this tier at any matching void fissure"


@dataclass
class Mission:
    node: str
    game_mode: str
    parts: list[str]
    # Expected effort (None = unobtainable / unknown chance). runs = expected
    # reward rolls to collect every listed part; minutes = runs * mode time.
    runs: float | None = None
    minutes: float | None = None
    part_runs: dict[str, float | None] = field(default_factory=dict)
    rotation: str | None = None   # "A"/"B"/"C" for endless nodes, else None


@dataclass
class PrimeRelic:
    """One relic to crack in the joint Prime plan, with the needed parts it yields.

    Cracking a relic is a single mutually-exclusive draw over its table, so a
    relic that contains several needed parts is farmed/cracked *once* for all of
    them — not once per part. ``cracks`` is the expected number of cracks (and
    relics consumed); ``runs`` adds the relic-farming runs; ``minutes`` is the
    total time.
    """
    relic: str
    tier: str
    parts: list[str]
    cracks: float | None = None
    runs: float | None = None
    minutes: float | None = None


@dataclass
class TierGuide:
    tier: str
    where: str


@dataclass
class RouteResult:
    missing_equipment: int
    non_prime: list[Mission] = field(default_factory=list)
    non_prime_uncovered: list[str] = field(default_factory=list)
    prime: list[PrimeRelic] = field(default_factory=list)
    prime_part_count: int = 0               # distinct Prime parts still needed
    tiers: list[TierGuide] = field(default_factory=list)
    vaulted_equipment: list[str] = field(default_factory=list)
    vaulted_part_count: int = 0
    no_mission_source: list[str] = field(default_factory=list)
    # Parts with /Recipes/ but no mission/relic drop (e.g. Market-only gear),
    # grouped by owning equipment: equipment display → sorted part display names.
    no_part_source: dict[str, list[str]] = field(default_factory=dict)
    # Parts from non-standard sources (Sanctuary Onslaught, Plains, …) grouped by source
    special_source: dict[str, list[str]] = field(default_factory=dict)
    # display_name → https://cdn.warframestat.us/img/<imageName>
    images: dict[str, str] = field(default_factory=dict)
    # display_name → WFCD type string (e.g. "Warframe", "Melee", "Rifle", …)
    # populated for all items in no_part_source and no_mission_source.
    item_types: dict[str, str] = field(default_factory=dict)
    # Expected-effort summary. refinement = relic refinement assumed for Primes.
    refinement: str = "Intact"
    total_minutes: float | None = None      # non-Prime missions + Prime parts
    # Needed relics or parts that also drop from transient/event objectives,
    # grouped by objective name: "Arbitrations (Rot B)" → ["Axi N3 Relic", ...]
    event_source: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _runs(x: float | None) -> float | None:
    """Round expected runs for output; map inf/unobtainable to None (JSON null)."""
    if x is None or x == float("inf"):
        return None
    return round(x, 1)


def _mins(x: float | None) -> float | None:
    if x is None or x == float("inf"):
        return None
    return round(x, 1)


def _prime_relic_plan(plan, prime_needed: set[str], refinement: str):
    """Joint Prime plan: which relics to crack to get all needed Prime parts.

    Cracking a relic is one mutually-exclusive draw over its table — the same
    shape as a non-Prime node — so we reuse :func:`optimize.optimize_by_cost`,
    treating each in-rotation relic as a node whose items are the needed parts it
    contains. A relic yielding several needed parts is then farmed/cracked once
    for all of them (no per-part double-counting). Cost is expected **time**:
    ``cracks * ((1/r)*farm_mode_minutes + fissure_minutes)``.

    Returns ``(relic_nodes_route, dchance, per_crack_time)`` helpers so the
    caller can read effort per chosen relic.
    """
    def dchance(pnorm: str, rnorm: str) -> float:
        refs = plan.part_relic_refine_chance.get(pnorm, {}).get(rnorm, {})
        return refs.get(refinement) or refs.get("Intact") or next(
            iter(refs.values()), 0.0)

    relic_disp: dict[str, str] = {}
    relic_items: dict[str, set[str]] = {}
    for pnorm, relics in plan.prime_part_relics.items():
        if pnorm not in prime_needed:
            continue
        for rdisp in relics:
            rnorm = items.normalize(rdisp)
            if rnorm in plan.relic_source:
                relic_disp[rnorm] = rdisp
                relic_items.setdefault(rnorm, set()).add(pnorm)

    relic_nodes = [
        Node(planet="Void", name=relic_disp[rn], game_mode="Fissure",
             items=frozenset(parts))
        for rn, parts in relic_items.items()
    ]

    def per_crack_time(rnorm: str) -> float:
        r_chance, r_mode, r_rot = plan.relic_source[rnorm]
        if r_chance <= 0:
            return float("inf")
        rot_factor = effort.rotation_factor(r_rot)
        return (100.0 / r_chance) * effort.mode_minutes(r_mode) * rot_factor + effort.FISSURE_MINUTES

    def relic_cost(node, parts) -> float:
        rnorm = items.normalize(node.name)
        cracks = effort.mission_runs([dchance(p, rnorm) for p in parts])
        if cracks == float("inf"):
            return float("inf")
        return cracks * per_crack_time(rnorm)

    route = optimize.optimize_by_cost(relic_nodes, prime_needed, relic_cost)
    return route, dchance, per_crack_time


def _build_transient_map(transient_rewards: list) -> dict[str, set[str]]:
    """Build norm_item → {objective descriptions} from transientRewards data."""
    result: dict[str, set[str]] = {}
    for obj in transient_rewards:
        if not isinstance(obj, dict):
            continue
        name = obj.get("objectiveName", "")
        for r in obj.get("rewards", []):
            if not isinstance(r, dict):
                continue
            item = r.get("itemName", "")
            if not item:
                continue
            rot = r.get("rotation", "")
            obj_desc = f"{name} (Rot {rot})" if rot else name
            norm = items.normalize(item)
            result.setdefault(norm, set()).add(obj_desc)
            # Also index relic by its base name (strips refinement suffix).
            if "Relic" in item:
                base_norm = items.normalize(items.base_relic_name(item))
                result.setdefault(base_norm, set()).add(obj_desc)
    return result


def plan_route(
    *,
    owned: set[str],
    want: set[str],
    owned_parts: set[str],
    items_data: list[dict],
    mission_rewards: dict,
    refinement: str = "Intact",
    transient_rewards: list | None = None,
    syndicate_missions: list | None = None,
) -> RouteResult:
    """Assemble a full route plan from normalized ownership/target sets.

    ``refinement`` is the relic refinement assumed when estimating Prime-part
    effort (Intact/Exceptional/Flawless/Radiant); it does not change which
    missions are selected, only the expected-runs/time figures.
    """
    needed_equipment = inventory.compute_needed(want, owned)
    result = RouteResult(missing_equipment=len(needed_equipment),
                         refinement=refinement)
    if not needed_equipment:
        return result

    active_bounty = (worldstate.active_bounty_items(syndicate_missions)
                     if syndicate_missions is not None else None)
    plan = acquisition.build_plan(items_data, mission_rewards, needed_equipment,
                                  active_bounty=active_bounty)

    # Subtract loose parts the player already holds.
    plan.direct_parts -= owned_parts
    plan.not_farmable -= owned_parts
    for p in owned_parts:
        plan.prime_part_relics.pop(p, None)
        plan.orphan_parts.pop(p, None)
        plan.special_source_parts.pop(p, None)

    disp = lambda p: plan.part_display.get(p, p)

    # Non-Prime: route by least expected *time*, not fewest missions. When a
    # part drops at several nodes the optimizer picks the cheapest one (higher
    # chance and/or faster mode), assigning each part to exactly one node.
    if plan.direct_parts:
        def node_cost(node, parts):
            chances = plan.node_part_chance.get(node.key, {})
            runs = effort.mission_runs([chances.get(p, 0.0) for p in parts])
            if runs == float("inf"):
                return float("inf")
            rot = plan.node_rotation.get(node.key)
            return runs * effort.mode_minutes(node.game_mode) * effort.rotation_factor(rot)

        route = optimize.optimize_by_cost(plan.direct_nodes, plan.direct_parts,
                                          node_cost)
        missions = []
        for step in route.steps:
            chances = plan.node_part_chance.get(step.node.key, {})
            covered = sorted(step.covers, key=disp)
            runs = effort.mission_runs([chances.get(p, 0.0) for p in covered])
            rot = plan.node_rotation.get(step.node.key)
            minutes = (runs * effort.mode_minutes(step.node.game_mode) * effort.rotation_factor(rot)
                       if runs != float("inf") else float("inf"))
            missions.append(Mission(
                node=step.node.key, game_mode=step.node.game_mode,
                parts=[disp(p) for p in covered],
                runs=_runs(runs), minutes=_mins(minutes),
                part_runs={disp(p): _runs(effort.part_runs(chances.get(p, 0.0)))
                           for p in covered},
                rotation=rot,
            ))
        # Show the heaviest missions first so the time sink is obvious.
        missions.sort(key=lambda m: (m.minutes is None, -(m.minutes or 0)))
        result.non_prime = missions
        result.non_prime_uncovered = sorted(disp(p) for p in route.uncovered)

    # Prime: one joint plan over relics (a relic that drops several needed parts
    # is cracked once for all of them — see _prime_relic_plan).
    prime_needed = set(plan.prime_part_relics)
    result.prime_part_count = len(prime_needed)
    tiers_needed: set[str] = set()
    if prime_needed:
        route, dchance, per_crack_time = _prime_relic_plan(
            plan, prime_needed, refinement)
        relics_out: list[PrimeRelic] = []
        for step in route.steps:
            rnorm = items.normalize(step.node.name)
            cracks = effort.mission_runs(
                [dchance(p, rnorm) for p in step.covers])
            r_chance, _, _ = plan.relic_source[rnorm]
            minutes = cracks * per_crack_time(rnorm)
            runs = cracks * (100.0 / r_chance + 1.0)  # relic-farm runs + cracks
            tier = items.relic_tier(step.node.name)
            tiers_needed.add(tier)
            relics_out.append(PrimeRelic(
                relic=step.node.name, tier=tier,
                parts=sorted(disp(p) for p in step.covers),
                cracks=_runs(cracks), runs=_runs(runs), minutes=_mins(minutes)))
        # Fastest (cheapest) relics first; unobtainable last.
        relics_out.sort(key=lambda r: (r.minutes is None, r.minutes or 0))
        result.prime = relics_out

    result.tiers = [
        TierGuide(tier=t, where=RELIC_TIER_GUIDE.get(t, GENERIC_TIER_HINT))
        for t in sorted(tiers_needed)
    ]

    from collections import defaultdict as _dd

    result.vaulted_equipment = sorted(plan.vaulted_equipment())
    result.vaulted_part_count = len(plan.not_farmable)
    result.no_mission_source = sorted(plan.no_mission_source)

    # Market-only parts, grouped by owning equipment (e.g. Agkuza → Blade,
    # Guard, Handle, Blueprint) so the section reads per-weapon, not as a flat
    # alphabetical wall of "<X> Blueprint".
    part_map: dict[str, list[str]] = _dd(list)
    for pnorm, part_name in plan.orphan_parts.items():
        equip = plan.part_equipment.get(pnorm, part_name)
        part_map[equip].append(part_name)
    result.no_part_source = {
        eq: sorted(parts) for eq, parts in sorted(part_map.items())
    }

    # Group special-source parts by location string, sorted.
    src_map: dict[str, list[str]] = _dd(list)
    for pnorm, locs in plan.special_source_parts.items():
        part_name = disp(pnorm)
        for loc in locs:
            src_map[loc].append(part_name)
    result.special_source = {src: sorted(set(parts)) for src, parts in sorted(src_map.items())}

    # Type index: normalized name → WFCD type string, for UI grouping.
    type_idx: dict[str, str] = {
        items.normalize(it.get("name", "")): it.get("type", "")
        for it in items_data if it.get("name")
    }
    type_map: dict[str, str] = {}
    for equip in result.no_part_source:
        t = type_idx.get(items.normalize(equip))
        if t:
            type_map[equip] = t
    for item in result.no_mission_source:
        t = type_idx.get(items.normalize(item))
        if t:
            type_map[item] = t
    result.item_types = type_map

    result.images = _build_image_map(items_data, result, plan.part_equipment)

    # Grand total estimated time = non-Prime missions + Prime parts. Skip
    # entries with unknown effort (None) rather than poisoning the sum.
    total = sum(m.minutes for m in result.non_prime if m.minutes is not None)
    total += sum(p.minutes for p in result.prime if p.minutes is not None)
    result.total_minutes = round(total, 1) if total else None

    # Cross-reference needed relics and parts against transient/event rewards so
    # the user knows which currently-running events yield things they need.
    if transient_rewards:
        from collections import defaultdict as _dd2
        tmap = _build_transient_map(transient_rewards)
        ev: dict[str, list[str]] = _dd2(list)
        # Prime relics being farmed.
        for pr in result.prime:
            rnorm = items.normalize(pr.relic)
            for obj in tmap.get(rnorm, ()):
                ev[obj].append(pr.relic)
        # Non-prime parts.
        for m in result.non_prime:
            for part in m.parts:
                for obj in tmap.get(items.normalize(part), ()):
                    ev[obj].append(part)
        # Special-source parts.
        for parts in result.special_source.values():
            for part in parts:
                for obj in tmap.get(items.normalize(part), ()):
                    ev[obj].append(part)
        result.event_source = {obj: sorted(set(ps)) for obj, ps in sorted(ev.items())}

    return result


_CDN = "https://cdn.warframestat.us/img/"


def _build_image_map(
    items_data: list[dict],
    result: RouteResult,
    part_equipment: dict[str, str],
) -> dict[str, str]:
    """Return display_name → CDN URL for every name that appears in the result.

    Parts (e.g. "Caliban Prime Neuroptics") rarely have their own imageName, so
    we fall back to the parent equipment's image via part_equipment (which maps
    normalized part name → normalized equipment name).
    """
    relevant: set[str] = set()
    for m in result.non_prime:
        relevant.update(m.parts)
    for pr in result.prime:
        relevant.update(pr.parts)
    relevant.update(result.vaulted_equipment)
    relevant.update(result.no_mission_source)
    for parts in result.no_part_source.values():
        relevant.update(parts)
    for parts in result.special_source.values():
        relevant.update(parts)

    # normalized name → CDN URL (equipment names and component names)
    norm_to_url: dict[str, str] = {}
    for it in items_data:
        if not isinstance(it, dict):
            continue
        eq_name = it.get("name") or ""
        img = it.get("imageName") or ""
        if eq_name and img:
            norm_to_url[items.normalize(eq_name)] = _CDN + img
        for comp in it.get("components") or []:
            cname = comp.get("name") or ""
            cimg = comp.get("imageName") or ""
            if cname and cimg and eq_name:
                norm_to_url[items.normalize(f"{eq_name} {cname}")] = _CDN + cimg

    out: dict[str, str] = {}
    for name in relevant:
        norm = items.normalize(name)
        words = norm.split()

        # For Blueprint items the WFCD component imageName is a generic schematic.
        # Prefer the progressive prefix (finds the specific component or warframe
        # portrait) over the schematic direct hit.
        #   "Citrine Blueprint"          → "citrine"          (warframe portrait)
        #   "Citrine Chassis Blueprint"  → "citrine chassis"  (chassis icon)
        #   "Ambassador Barrel Blueprint"→ "ambassador barrel"(gun part icon)
        if words and words[-1] == "blueprint":
            w = list(words)
            found = False
            while len(w) > 1:
                w.pop()
                prefix = " ".join(w)
                if prefix in norm_to_url:
                    out[name] = norm_to_url[prefix]
                    found = True
                    break
            if found:
                continue
            # Fall through to direct hit if no prefix matched (e.g. single-word
            # equipment names, though that would be unusual).

        # Direct hit: exact match on equipment or component imageName.
        if norm in norm_to_url:
            out[name] = norm_to_url[norm]
            continue

        # Progressive prefix for non-Blueprint names.
        w = list(words)
        found = False
        while len(w) > 1:
            w.pop()
            prefix = " ".join(w)
            if prefix in norm_to_url:
                out[name] = norm_to_url[prefix]
                found = True
                break
        if found:
            continue

        # Last resort: look up the parent equipment via part_equipment mapping.
        eq_disp = part_equipment.get(norm)
        if eq_disp:
            eq_n = items.normalize(eq_disp)
            if eq_n in norm_to_url:
                out[name] = norm_to_url[eq_n]

    return out
