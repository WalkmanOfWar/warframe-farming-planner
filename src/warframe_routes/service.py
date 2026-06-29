"""Shared route-planning service used by both the CLI and the web backend.

Takes already-resolved ownership/target sets and returns a structured
:class:`RouteResult` (no printing, no I/O). The CLI formats it as text; the web
backend serializes it to JSON. This is the single source of truth for *how* a
plan is assembled from a built :class:`~warframe_routes.acquisition.AcquisitionPlan`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import acquisition, effort, inventory, items, optimize

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


@dataclass
class PrimePart:
    part: str
    relics: list[str]
    tiers: list[str]
    # Cheapest relic to crack for this part + its expected effort (solo).
    best_relic: str | None = None
    runs: float | None = None          # total: relic farming + cracking
    minutes: float | None = None
    relic_farm_runs: float | None = None
    crack_runs: float | None = None


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
    # Parts with /Recipes/ but no mission/relic drop (e.g. Market-only gear),
    # grouped by owning equipment: equipment display → sorted part display names.
    no_part_source: dict[str, list[str]] = field(default_factory=dict)
    # Parts from non-standard sources (Sanctuary Onslaught, Plains, …) grouped by source
    special_source: dict[str, list[str]] = field(default_factory=dict)
    # display_name → https://cdn.warframestat.us/img/<imageName>
    images: dict[str, str] = field(default_factory=dict)
    # Expected-effort summary. refinement = relic refinement assumed for Primes.
    refinement: str = "Intact"
    total_minutes: float | None = None      # non-Prime missions + Prime parts

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


def _best_prime_relic(plan, pnorm: str, relics_display: list[str],
                      refinement: str) -> dict:
    """Pick the relic that minimizes expected total runs for a Prime part.

    For each candidate relic we need the part's in-relic chance at the chosen
    refinement (falling back to Intact, then any) and the relic's best
    acquisition node. Relics not currently farmable (no live source) are skipped.
    """
    best = {"relic": None, "total_runs": float("inf"), "minutes": float("inf"),
            "relic_farm_runs": float("inf"), "crack_runs": float("inf")}
    for rdisp in relics_display:
        rnorm = items.normalize(rdisp)
        refines = plan.part_relic_refine_chance.get(pnorm, {}).get(rnorm, {})
        d = refines.get(refinement) or refines.get("Intact") or (
            next(iter(refines.values()), 0.0))
        src = plan.relic_source.get(rnorm)
        if not d or not src:
            continue
        r_chance, r_mode = src
        e = effort.prime_part_runs(d, r_chance)
        minutes = (e["relic_farm_runs"] * effort.mode_minutes(r_mode)
                   + e["crack_runs"] * effort.FISSURE_MINUTES)
        if e["total_runs"] < best["total_runs"]:
            best = {"relic": rdisp, "minutes": minutes, **e}
    return best


def plan_route(
    *,
    owned: set[str],
    want: set[str],
    owned_parts: set[str],
    items_data: list[dict],
    mission_rewards: dict,
    refinement: str = "Intact",
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

    plan = acquisition.build_plan(items_data, mission_rewards, needed_equipment)

    # Subtract loose parts the player already holds.
    plan.direct_parts -= owned_parts
    plan.not_farmable -= owned_parts
    for p in owned_parts:
        plan.prime_part_relics.pop(p, None)
        plan.orphan_parts.pop(p, None)
        plan.special_source_parts.pop(p, None)

    disp = lambda p: plan.part_display.get(p, p)

    # Non-Prime: fewest-missions set cover over boss/mission nodes.
    if plan.direct_parts:
        route = optimize.optimize_route(plan.direct_nodes, plan.direct_parts)
        missions = []
        for step in route.steps:
            chances = plan.node_part_chance.get(step.node.key, {})
            covered = sorted(step.covers, key=disp)
            runs = effort.mission_runs([chances.get(p, 0.0) for p in covered])
            minutes = (runs * effort.mode_minutes(step.node.game_mode)
                       if runs != float("inf") else float("inf"))
            missions.append(Mission(
                node=step.node.key, game_mode=step.node.game_mode,
                parts=[disp(p) for p in covered],
                runs=_runs(runs), minutes=_mins(minutes),
                part_runs={disp(p): _runs(effort.part_runs(chances.get(p, 0.0)))
                           for p in covered},
            ))
        result.non_prime = missions
        result.non_prime_uncovered = sorted(disp(p) for p in route.uncovered)

    # Prime: per-part relics + the tiers they belong to.
    tiers_needed: set[str] = set()
    for pnorm in sorted(plan.prime_part_relics, key=disp):
        relics = sorted(plan.prime_part_relics[pnorm])
        part_tiers = sorted({items.relic_tier(r) for r in relics})
        tiers_needed.update(part_tiers)
        best = _best_prime_relic(plan, pnorm, relics, refinement)
        result.prime.append(PrimePart(
            part=disp(pnorm), relics=relics, tiers=part_tiers,
            best_relic=best["relic"],
            runs=_runs(best["total_runs"]),
            minutes=_mins(best["minutes"]),
            relic_farm_runs=_runs(best["relic_farm_runs"]),
            crack_runs=_runs(best["crack_runs"]),
        ))

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

    result.images = _build_image_map(items_data, result, plan.part_equipment)

    # Grand total estimated time = non-Prime missions + Prime parts. Skip
    # entries with unknown effort (None) rather than poisoning the sum.
    total = sum(m.minutes for m in result.non_prime if m.minutes is not None)
    total += sum(p.minutes for p in result.prime if p.minutes is not None)
    result.total_minutes = round(total, 1) if total else None
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
