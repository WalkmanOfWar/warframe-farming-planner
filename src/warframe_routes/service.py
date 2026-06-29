"""Shared route-planning service used by both the CLI and the web backend.

Takes already-resolved ownership/target sets and returns a structured
:class:`RouteResult` (no printing, no I/O). The CLI formats it as text; the web
backend serializes it to JSON. This is the single source of truth for *how* a
plan is assembled from a built :class:`~warframe_routes.acquisition.AcquisitionPlan`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import acquisition, inventory, items, optimize

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


@dataclass
class PrimePart:
    part: str
    relics: list[str]
    tiers: list[str]


@dataclass
class TierGuide:
    tier: str
    where: str


@dataclass
class RouteResult:
    missing_equipment: int
    non_prime: list[Mission] = field(default_factory=list)
    non_prime_uncovered: list[str] = field(default_factory=list)
    prime: list[PrimePart] = field(default_factory=list)
    tiers: list[TierGuide] = field(default_factory=list)
    vaulted_equipment: list[str] = field(default_factory=list)
    vaulted_part_count: int = 0
    no_mission_source: list[str] = field(default_factory=list)
    # Parts with /Recipes/ but no mission/relic drop (e.g. warframe main BPs from Market)
    no_part_source: list[str] = field(default_factory=list)
    # display_name → https://cdn.warframestat.us/img/<imageName>
    images: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def plan_route(
    *,
    owned: set[str],
    want: set[str],
    owned_parts: set[str],
    items_data: list[dict],
    mission_rewards: dict,
) -> RouteResult:
    """Assemble a full route plan from normalized ownership/target sets."""
    needed_equipment = inventory.compute_needed(want, owned)
    result = RouteResult(missing_equipment=len(needed_equipment))
    if not needed_equipment:
        return result

    plan = acquisition.build_plan(items_data, mission_rewards, needed_equipment)

    # Subtract loose parts the player already holds.
    plan.direct_parts -= owned_parts
    plan.not_farmable -= owned_parts
    for p in owned_parts:
        plan.prime_part_relics.pop(p, None)
        plan.orphan_parts.pop(p, None)

    disp = lambda p: plan.part_display.get(p, p)

    # Non-Prime: fewest-missions set cover over boss/mission nodes.
    if plan.direct_parts:
        route = optimize.optimize_route(plan.direct_nodes, plan.direct_parts)
        result.non_prime = [
            Mission(node=step.node.key, game_mode=step.node.game_mode,
                    parts=sorted(disp(p) for p in step.covers))
            for step in route.steps
        ]
        result.non_prime_uncovered = sorted(disp(p) for p in route.uncovered)

    # Prime: per-part relics + the tiers they belong to.
    tiers_needed: set[str] = set()
    for pnorm in sorted(plan.prime_part_relics, key=disp):
        relics = sorted(plan.prime_part_relics[pnorm])
        part_tiers = sorted({items.relic_tier(r) for r in relics})
        tiers_needed.update(part_tiers)
        result.prime.append(
            PrimePart(part=disp(pnorm), relics=relics, tiers=part_tiers))

    result.tiers = [
        TierGuide(tier=t, where=RELIC_TIER_GUIDE.get(t, GENERIC_TIER_HINT))
        for t in sorted(tiers_needed)
    ]

    result.vaulted_equipment = sorted(plan.vaulted_equipment())
    result.vaulted_part_count = len(plan.not_farmable)
    result.no_mission_source = sorted(plan.no_mission_source)
    result.no_part_source = sorted(plan.orphan_parts.values())
    result.images = _build_image_map(items_data, result, plan.part_equipment)
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
    for pp in result.prime:
        relevant.add(pp.part)
    relevant.update(result.vaulted_equipment)
    relevant.update(result.no_mission_source)
    relevant.update(result.no_part_source)

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
