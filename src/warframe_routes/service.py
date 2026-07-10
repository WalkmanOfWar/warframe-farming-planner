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
    # This node is currently an open void fissure of this tier — running it as
    # a fissure farms the part AND cracks a relic in the same mission.
    live_fissure: str | None = None


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
    # Best node to farm this relic (fastest expected time per relic drop).
    farm_node: str | None = None   # e.g. "Void / Hepit"
    farm_mode: str | None = None   # e.g. "Capture"
    farm_chance: float | None = None  # drop chance % at that node
    owned: int = 0                 # copies already held (credit against farming)
    # Per-relic refinement advice: the refinement that minimizes expected time
    # for THIS relic's needed parts (Radiant boosts rares but hurts commons, so
    # the plan-wide choice is often wrong per relic). None = chosen one is best.
    best_refinement: str | None = None
    best_refinement_minutes: float | None = None
    # Live-fissure context: tier_live = a fissure of this relic's tier is open
    # right now (cracking is actionable); farm_node_live = the relic's best farm
    # node is itself an open fissure of the same tier — farm & crack together.
    tier_live: bool = False
    farm_node_live: bool = False


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
    # Vaulted parts rescueable from relics already in the player's inventory:
    # {"part", "relic", "owned", "chance"} — the relic no longer drops anywhere,
    # but held copies can still be cracked at a fissure.
    vaulted_crackable: list[dict] = field(default_factory=list)
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
    squad_radiant: bool = False             # whether 4× squad cracking was modelled
    total_minutes: float | None = None      # non-Prime missions + Prime parts
    # Needed relics or parts that also drop from transient/event objectives,
    # grouped by objective name: "Arbitrations (Rot B)" → ["Axi N3 Relic", ...]
    # Live invasions with matching rewards are merged in ("Invasion — <node>").
    event_source: dict[str, list[str]] = field(default_factory=dict)
    # Live void fissures for the tiers this plan needs: tier → fissure dicts
    # ({node, mission, hard, storm, expiry}) — "crack a Lith" is only actionable
    # when a Lith fissure is actually open somewhere.
    active_fissures: dict[str, list[dict]] = field(default_factory=dict)
    # Baro Ki'Teer stock matching needed items: {location, until, items: [...]}.
    baro: dict | None = None
    # Varzia's (Prime Resurgence) stock matching *fully-vaulted* needed
    # equipment — the only non-trade way to obtain it: {location, until,
    # items: [...]}.
    vault_trader: dict | None = None
    # Darvo's current daily deal, if it matches a needed item:
    # {item, discount, expiry}.
    daily_deal: dict | None = None
    # warframe.market average prices for a bounded set of expensive-to-farm
    # or unfarmable items (see select_price_candidates): display_name ->
    # {name, plat, tradable, url}. Populated by the caller (cli.py/web.py)
    # *after* plan_route returns — plan_route itself makes no network calls.
    market_prices: dict[str, dict] = field(default_factory=dict)

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


def _prime_relic_plan(plan, prime_needed: set[str], refinement: str,
                      squad_size: int = 1,
                      owned_relics: dict[str, int] | None = None):
    """Joint Prime plan: which relics to crack to get all needed Prime parts.

    Cracking a relic is one mutually-exclusive draw over its table — the same
    shape as a non-Prime node — so we reuse :func:`optimize.optimize_by_cost`,
    treating each in-rotation relic as a node whose items are the needed parts it
    contains. A relic yielding several needed parts is then farmed/cracked once
    for all of them (no per-part double-counting). Cost is expected **time**:
    ``cracks * ((1/r)*farm_mode_minutes + fissure_minutes)``.

    With ``squad_size > 1``, chances are boosted to the effective per-run
    probability of a squad sharing results (see :func:`effort.effective_squad_chance_pct`).

    ``owned_relics`` (normalized base relic name → count held in the player's
    inventory) credits copies you already hold: each owned copy is one crack
    that costs no farming, so a relic with enough stock in the vault costs only
    fissure time — and the optimizer will prefer it over farming a fresh one.

    Returns ``(relic_nodes_route, dchance, relic_effort)`` helpers so the
    caller can read effort per chosen relic; ``relic_effort(rnorm, cracks)``
    yields ``(farm_runs, minutes)`` with the owned credit applied.
    """
    owned_relics = owned_relics or {}
    def dchance(pnorm: str, rnorm: str, ref: str | None = None) -> float:
        refs = plan.part_relic_refine_chance.get(pnorm, {}).get(rnorm, {})
        raw = refs.get(ref or refinement) or refs.get("Intact") or next(
            iter(refs.values()), 0.0)
        if squad_size > 1:
            return effort.effective_squad_chance_pct(raw, squad_size)
        return raw

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

    def _farm_minutes_per_relic(rnorm: str) -> float:
        r_chance, r_mode, r_rot, _node = plan.relic_source[rnorm]
        if r_chance <= 0:
            return float("inf")
        rot_factor = effort.rotation_factor(r_rot)
        return (100.0 / r_chance) * effort.mode_minutes(r_mode) * rot_factor

    def relic_effort(rnorm: str, cracks: float) -> tuple[float, float]:
        """(relic-farm runs, total minutes) for ``cracks`` expected cracks,
        crediting owned copies — each held relic is a crack with no farm cost."""
        farm_needed = max(0.0, cracks - owned_relics.get(rnorm, 0))
        if farm_needed <= 0:
            return 0.0, cracks * effort.FISSURE_MINUTES
        fm = _farm_minutes_per_relic(rnorm)
        if fm == float("inf"):
            return float("inf"), float("inf")
        r_chance = plan.relic_source[rnorm][0]
        return (farm_needed * (100.0 / r_chance),
                farm_needed * fm + cracks * effort.FISSURE_MINUTES)

    def relic_cost(node, parts) -> float:
        rnorm = items.normalize(node.name)
        cracks = effort.mission_runs([dchance(p, rnorm) for p in parts])
        if cracks == float("inf"):
            return float("inf")
        return relic_effort(rnorm, cracks)[1]

    route = optimize.optimize_by_cost(relic_nodes, prime_needed, relic_cost)
    return route, dchance, relic_effort


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
    squad_radiant: bool = False,
    owned_relics: dict[str, int] | None = None,
    fissures: list | None = None,
    void_trader: dict | None = None,
    invasions: list | None = None,
    vault_trader: dict | None = None,
    daily_deals: list | None = None,
) -> RouteResult:
    """Assemble a full route plan from normalized ownership/target sets.

    ``refinement`` is the relic refinement assumed when estimating Prime-part
    effort (Intact/Exceptional/Flawless/Radiant); it does not change which
    missions are selected, only the expected-runs/time figures.

    ``squad_radiant`` models cracking in a squad of 4 sharing results: each
    fissure run yields 4 independent Radiant cracks, dramatically reducing
    expected runs for rare parts.

    ``owned_relics`` (normalized base relic name → count, from the private
    inventory) credits relics already held: they cost no farming, only the
    fissure crack — and vaulted parts whose relic sits in the vault are
    reported as still obtainable (``vaulted_crackable``).

    ``vault_trader`` (Varzia / Prime Resurgence) is cross-referenced against
    fully-vaulted needed equipment — the only non-trade way to obtain it.
    ``daily_deals`` (Darvo) is checked for a match against anything needed.
    """
    needed_equipment = inventory.compute_needed(want, owned)
    result = RouteResult(missing_equipment=len(needed_equipment),
                         refinement=refinement,
                         squad_radiant=squad_radiant)
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
        squad_size = 4 if squad_radiant else 1
        route, dchance, relic_effort = _prime_relic_plan(
            plan, prime_needed, refinement, squad_size=squad_size,
            owned_relics=owned_relics)
        relics_out: list[PrimeRelic] = []
        for step in route.steps:
            rnorm = items.normalize(step.node.name)
            cracks = effort.mission_runs(
                [dchance(p, rnorm) for p in step.covers])
            r_chance, r_mode, _r_rot, r_node = plan.relic_source[rnorm]
            farm_runs, minutes = relic_effort(rnorm, cracks)
            runs = farm_runs + cracks  # relic-farm runs + cracks
            tier = items.relic_tier(step.node.name)
            tiers_needed.add(tier)
            # Per-relic refinement advice: Radiant boosts rares but *lowers*
            # common chances, so the plan-wide refinement can be wrong for this
            # particular relic. Recommend the time-minimizing one when it beats
            # the chosen refinement meaningfully (> 1 minute).
            best_ref, best_min = None, None
            if minutes != float("inf"):
                for ref in effort.REFINEMENTS:
                    ref_cracks = effort.mission_runs(
                        [dchance(p, rnorm, ref) for p in step.covers])
                    if ref_cracks == float("inf"):
                        continue
                    ref_min = relic_effort(rnorm, ref_cracks)[1]
                    if best_min is None or ref_min < best_min:
                        best_ref, best_min = ref, ref_min
                if best_ref == refinement or (best_min is not None
                                              and minutes - best_min <= 1.0):
                    best_ref, best_min = None, None
            relics_out.append(PrimeRelic(
                relic=step.node.name, tier=tier,
                parts=sorted(disp(p) for p in step.covers),
                cracks=_runs(cracks), runs=_runs(runs), minutes=_mins(minutes),
                farm_node=r_node, farm_mode=r_mode,
                farm_chance=round(r_chance, 2) if r_chance else None,
                owned=(owned_relics or {}).get(rnorm, 0),
                best_refinement=best_ref,
                best_refinement_minutes=_mins(best_min)))
        # Fastest (cheapest) relics first; unobtainable last.
        relics_out.sort(key=lambda r: (r.minutes is None, r.minutes or 0))
        result.prime = relics_out

    result.tiers = [
        TierGuide(tier=t, where=RELIC_TIER_GUIDE.get(t, GENERIC_TIER_HINT))
        for t in sorted(tiers_needed)
    ]

    # Live fissures for the tiers this plan needs — "crack an Axi" is only
    # actionable when an Axi fissure is actually open right now.
    if fissures:
        live = worldstate.active_fissures(fissures)
        by_tier: dict[str, list[dict]] = {}
        for f in live:
            if f["tier"] in tiers_needed:
                by_tier.setdefault(f["tier"], []).append(f)
        for lst in by_tier.values():  # normal missions first, storms/SP last
            lst.sort(key=lambda f: (f["storm"], f["hard"], f["node"]))
        result.active_fissures = dict(sorted(by_tier.items()))

        # Double-dip: a route node that is an open fissure right now farms the
        # part AND cracks a relic in one mission. Match plan nodes ("Sedna -
        # Adaro · Rot B") against fissure nodes ("Adaro (Sedna)").
        node_tiers = worldstate.fissure_node_tiers(live)
        for m in result.non_prime:
            planet, _, name = m.node.partition(" - ")
            name = name.split(" · ")[0]
            m.live_fissure = node_tiers.get(f"{planet}|{name}".casefold())
        live_tiers = {f["tier"] for f in live if not f["storm"]}
        for pr in result.prime:
            pr.tier_live = pr.tier in live_tiers
            if pr.farm_node:  # "Void / Hepit" — is the farm node a live fissure
                p, _, n = pr.farm_node.partition(" / ")
                pr.farm_node_live = (
                    node_tiers.get(f"{p.strip()}|{n.strip()}".casefold()) == pr.tier)

    # Everything the player still needs, normalized — for Baro/invasion matching.
    needed_norms = set(plan.part_display) | set(needed_equipment)

    if void_trader is not None:
        stock = worldstate.baro_stock(void_trader)
        if stock:
            hits = sorted(stock["items"][n] for n in stock["items"] if n in needed_norms)
            if hits:
                result.baro = {"location": stock["location"],
                               "until": stock["until"], "items": hits}

    if daily_deals is not None:
        deal = worldstate.daily_deal(daily_deals)
        if deal and items.normalize(deal["item"]) in needed_norms:
            result.daily_deal = deal

    # Running invasions whose rewards match needed items → merged into
    # event_source so both UIs pick them up with no extra rendering path.
    invasion_hits: dict[str, list[str]] = {}
    if invasions:
        for norm, descs in worldstate.invasion_rewards(invasions).items():
            if norm in needed_norms:
                # Parts have a tracked display name; bare equipment falls back
                # to title-case (invasion rewards are simple ASCII names).
                name = plan.part_display.get(norm) or norm.title()
                for d in descs:
                    invasion_hits.setdefault(d, []).append(name)

    from collections import defaultdict as _dd

    result.vaulted_equipment = sorted(plan.vaulted_equipment())
    result.vaulted_part_count = len(plan.not_farmable)
    result.no_mission_source = sorted(plan.no_mission_source)

    # Vaulted parts the player can still crack: the relic no longer drops
    # anywhere, but copies already sitting in the vault work at any fissure.
    if owned_relics:
        crackable: list[dict] = []
        for pnorm in plan.not_farmable:
            for rnorm, refs in plan.part_relic_refine_chance.get(pnorm, {}).items():
                count = owned_relics.get(rnorm, 0)
                if count <= 0:
                    continue
                chance = refs.get(refinement) or refs.get("Intact") or next(
                    iter(refs.values()), 0.0)
                crackable.append({
                    "part": disp(pnorm),
                    "relic": rnorm.title(),
                    "owned": count,
                    "chance": round(chance, 2),
                })
        result.vaulted_crackable = sorted(
            crackable, key=lambda c: (-c["chance"], c["part"]))

    # Varzia (Prime Resurgence): the only non-trade rescue for equipment that
    # is otherwise fully vaulted (no relic drops anywhere right now).
    if vault_trader is not None and result.vaulted_equipment:
        vstock = worldstate.vault_trader_stock(vault_trader)
        if vstock:
            vaulted_norms = {items.normalize(e) for e in result.vaulted_equipment}
            hits = sorted(vstock["items"][n] for n in vstock["items"] if n in vaulted_norms)
            if hits:
                result.vault_trader = {"location": vstock["location"],
                                       "until": vstock["until"], "items": hits}

    # Market-only parts, grouped by owning equipment (e.g. Agkuza → Blade,
    # Guard, Handle, Blueprint) so the section reads per-weapon, not as a flat
    # alphabetical wall of "<X> Blueprint".
    part_map: dict[str, list[str]] = _dd(list)
    for pnorm, part_name in plan.orphan_parts.items():
        equip = plan.part_equipment.get(pnorm, part_name)
        part_map[equip].append(part_name)

    # Detect Duviri Circuit items: orphan parts whose parent equipment has a
    # Duviri-specific resource component (Pathos Clamp, Rune Marrow, etc.).
    # These aren't in the WFCD drop table but are obtainable via the Circuit.
    duviri_equip: set[str] = set()
    item_idx = {it.get("name", ""): it for it in items_data if it.get("name")}
    for equip_name in list(part_map.keys()):
        it = item_idx.get(equip_name)
        if not it:
            continue
        for comp in it.get("components") or []:
            if "/Gameplay/Duviri/" in (comp.get("uniqueName") or ""):
                duviri_equip.add(equip_name)
                break
    # Move Duviri equipment parts out of no_part_source → special_source.
    duviri_label = "Duviri Circuit (weekly rotation — check in-game)"
    for equip_name in duviri_equip:
        for pname in part_map.pop(equip_name, []):
            plan.special_source_parts.setdefault(
                items.normalize(pname), set()
            ).add(duviri_label)

    # Detect Necramech vault parts the same way: no drop table lists Isolation
    # Vault rewards (they're not standard mission rewards), so these orphan
    # parts (Voidrig/Bonewidow/Morgha/Cortege) would otherwise sit in the
    # generic "no known source" bucket looking Market-only, when they're
    # actually won from a specific, farmable in-game activity.
    necramech_equip: set[str] = set()
    for equip_name in list(part_map.keys()):
        it = item_idx.get(equip_name)
        if not it:
            continue
        for comp in it.get("components") or []:
            if "/InfestedMicroplanet/Resources/Mechs/" in (comp.get("uniqueName") or ""):
                necramech_equip.add(equip_name)
                break
    necramech_label = "Necramech gear — Isolation Vault (Cambion Drift, Deimos); check in-game"
    for equip_name in necramech_equip:
        for pname in part_map.pop(equip_name, []):
            plan.special_source_parts.setdefault(
                items.normalize(pname), set()
            ).add(necramech_label)

    result.no_part_source = {
        eq: sorted(parts) for eq, parts in sorted(part_map.items())
    }

    # Group special-source parts by location string. Normalise raw location
    # strings from the items dataset into cleaner human-readable labels.
    def _source_label(loc: str) -> str:
        loc = loc.strip()
        if loc.startswith("Kahl's Garrison"):
            return "Kahl's Garrison (weekly)"
        if "WF1999 Bounty" in loc or "llvania" in loc:
            return "1999 Calendar Bounties (Höllvania)"
        return loc

    src_map: dict[str, list[str]] = _dd(list)
    for pnorm, locs in plan.special_source_parts.items():
        part_name = disp(pnorm)
        for loc in locs:
            src_map[_source_label(loc)].append(part_name)
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

    for desc, its in sorted(invasion_hits.items()):
        result.event_source.setdefault(desc, sorted(set(its)))

    return result


# Below this expected-minutes threshold, farming is assumed to still be the
# reasonable default — only genuinely expensive items get a market lookup.
PRICE_CHECK_MIN_MINUTES = 120.0
# Hard cap on outbound price-check requests per plan (no bulk endpoint exists,
# so this bounds added latency as much as it bounds request volume).
PRICE_CHECK_MAX_ITEMS = 15


def select_price_candidates(
    result: RouteResult,
    min_minutes: float = PRICE_CHECK_MIN_MINUTES,
    max_items: int = PRICE_CHECK_MAX_ITEMS,
) -> list[str]:
    """Pick a bounded set of item names worth a market.fetch_prices lookup.

    Two kinds of candidate, both meaning "farming this is a bad deal":
    *fully-vaulted* equipment (there is no farm route at all — every such
    item is included, unconditionally) and individual parts belonging to a
    relic/mission whose *total* expected time is at or above ``min_minutes``
    (a part is only as easy as the slowest thing sharing its crack/run).
    Ranked by that parent time, highest first, then capped at ``max_items``
    to bound the number of outbound requests — pure, no I/O.
    """
    ranked: list[tuple[float, str]] = [
        (float("inf"), name) for name in result.vaulted_equipment
    ]
    for pr in result.prime:
        if pr.minutes is not None and pr.minutes >= min_minutes:
            ranked.extend((pr.minutes, part) for part in pr.parts)
    for m in result.non_prime:
        if m.minutes is not None and m.minutes >= min_minutes:
            ranked.extend((m.minutes, part) for part in m.parts)
    ranked.sort(key=lambda c: -c[0])

    seen: set[str] = set()
    out: list[str] = []
    for _, name in ranked:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= max_items:
            break
    return out


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
