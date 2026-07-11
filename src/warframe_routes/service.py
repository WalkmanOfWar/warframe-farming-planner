"""Shared route-planning service used by both the CLI and the web backend.

Takes already-resolved ownership/target sets and returns a structured
:class:`RouteResult` (no printing, no I/O). The CLI formats it as text; the web
backend serializes it to JSON. This is the single source of truth for *how* a
plan is assembled from a built :class:`~warframe_routes.acquisition.AcquisitionPlan`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import acquisition, blueprint_costs, effort, inventory, items, optimize, worldstate
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
class BuyVsFarm:
    """One priced item paired with what farming it would actually cost, so the
    player can judge the trade themselves — this never claims a guaranteed time
    save, since a relic/mission's minutes cover *all* needed parts it yields,
    not just this one (see ``shared_with``)."""
    item: str
    plat: int
    tradable: bool
    url: str | None
    minutes: float | None   # None only for vaulted equipment (no farm route exists at all)
    source: str | None      # the relic/node this part farms from, or None if vaulted
    shared_with: int = 0    # other needed parts sharing that same relic/mission run


@dataclass
class PriorityAction:
    """One "what to do right now" call-out, ranked by how time-sensitive it
    is. Built purely from signals plan_route already computed (Baro/Darvo
    stock, live fissures, event/invasion matches, squad-friendly modes) —
    no extra data source, this only re-reads/re-ranks the plan. (Varzia is
    deliberately excluded — see plan_route's docstring.)
    ``urgency``: "now" (expires today — Darvo, Baro, an open fissure right
    now), "soon" (rotates over days — invasions), or "squad" (not
    time-limited, but meaningfully faster with 4 players)."""
    urgency: str
    title: str
    detail: str
    expiry: str | None = None


@dataclass
class ResourceNeed:
    """Total raw crafting resources (Orokin Cell, Ferrite, Neurodes, ...)
    needed to build every still-missing item in the plan, from a completely
    separate data source (the Warframe Wiki's blueprint module — WFCD does
    not track this at all; see blueprint_costs.py). ``owned``/``short_by``
    are None when no private inventory was supplied (gross need only)."""
    resource: str
    need: int
    owned: int | None = None
    short_by: int | None = None


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
    # Needed equipment that requires already owning another weapon to build
    # (Akbolto -> Bolto, Dual Raza -> Dual Kamas, Paracesis -> Galatine, …):
    # equipment display name -> prerequisite weapon display name.
    equipment_prerequisites: dict[str, str] = field(default_factory=dict)
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
    # Darvo's current daily deal, if it matches a needed item:
    # {item, discount, expiry}.
    daily_deal: dict | None = None
    # warframe.market average prices for a bounded set of expensive-to-farm
    # or unfarmable items (see select_price_candidates): display_name ->
    # {name, plat, tradable, url}. Populated by the caller (cli.py/web.py)
    # *after* plan_route returns — plan_route itself makes no network calls.
    market_prices: dict[str, dict] = field(default_factory=dict)
    # market_prices ranked against what farming each item actually costs, worst
    # farm (or unfarmable) first — see build_buy_vs_farm(). Populated by the
    # caller alongside market_prices, right after fetch_prices() returns.
    buy_vs_farm: list[BuyVsFarm] = field(default_factory=list)
    # Display names of every still-missing equipment (unfiltered by whether
    # any of its parts could be routed) — the input build_resource_needs()
    # needs, since crafting requires every sub-part regardless of where (or
    # whether) this tool found a farm route for it.
    missing_equipment_names: list[str] = field(default_factory=list)
    # Total raw crafting resources needed for every missing item, from a
    # separate data source than the rest of this tool — see
    # build_resource_needs(). Populated by the caller after plan_route
    # returns, same reasoning as market_prices/buy_vs_farm.
    resource_needs: list[ResourceNeed] = field(default_factory=list)
    # Total credits to build everything missing (same blueprint data + same
    # partial coverage as resource_needs) — see total_credits_needed().
    credits_needed: int | None = None
    # True when ownership came only from the public profile (--account-id
    # with no --helper/--nonce/--inventory) — misses loose parts and
    # built-but-unmastered gear. Set by plan_route itself from its
    # account_id_given/has_full_inventory args (not by the caller — cli.py
    # and web.py both need this and previously duplicated the same gating
    # expression); False whenever a full private inventory was used, or no
    # account was given at all.
    partial_inventory: bool = False
    # "Do this now / soon / with a squad" digest — see build_priority_actions().
    # Set by plan_route itself (not the caller): it only re-reads fields the
    # rest of this function already computed, no extra I/O.
    priority_actions: list[PriorityAction] = field(default_factory=list)

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
        rot_factor = effort.rotation_factor(r_rot, r_mode)
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
    daily_deals: list | None = None,
    account_id_given: bool = False,
    has_full_inventory: bool = False,
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

    ``daily_deals`` (Darvo) is checked for a match against anything needed.

    Varzia (Prime Resurgence) is deliberately **not** cross-referenced here:
    her Prime Warframe/Weapon *set* listings are Regal Aya only — a
    real-money premium currency, not the free/farmable Aya used for Void
    Relics — so unlike Baro (Credits+Ducats) or Darvo (Credits/Platinum),
    "buy it from Varzia" isn't a farming alternative this tool can suggest
    without contradicting its own "no real money" stance (see the login.php
    sync rejection in CLAUDE.md for the same reasoning).

    ``account_id_given``/``has_full_inventory`` set ``RouteResult.
    partial_inventory`` (true iff an account was given but ownership never
    came from a full private inventory — --helper/--nonce/--inventory).
    Computed here instead of by the caller so cli.py and web.py don't each
    reimplement the same gating logic.
    """
    needed_equipment = inventory.compute_needed(want, owned)
    item_by_norm = {items.normalize(it.get("name", "")): it.get("name", "")
                    for it in items_data if it.get("name")}
    result = RouteResult(missing_equipment=len(needed_equipment),
                         refinement=refinement,
                         squad_radiant=squad_radiant,
                         partial_inventory=account_id_given and not has_full_inventory,
                         missing_equipment_names=sorted(
                             item_by_norm[e] for e in needed_equipment if e in item_by_norm))
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
            return runs * effort.mode_minutes(node.game_mode) * effort.rotation_factor(rot, node.game_mode)

        route = optimize.optimize_by_cost(plan.direct_nodes, plan.direct_parts,
                                          node_cost)
        missions = []
        for step in route.steps:
            chances = plan.node_part_chance.get(step.node.key, {})
            covered = sorted(step.covers, key=disp)
            runs = effort.mission_runs([chances.get(p, 0.0) for p in covered])
            rot = plan.node_rotation.get(step.node.key)
            minutes = (runs * effort.mode_minutes(step.node.game_mode)
                       * effort.rotation_factor(rot, step.node.game_mode)
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
        # Not every live fissure is worth the same trip: cracking is a rush-in,
        # grab-reactant-fast job, so Capture/Exterminate (~1.5-3 min/crack) beat
        # Disruption/Excavation (~4 min), which beat Defense/Interception/
        # Skirmish (~5-6 min) — reuse effort.MODE_MINUTES (already the
        # calibrated per-mode time) rather than a second hardcoded ranking.
        # Only the fastest 3 per tier are ever displayed, so this ordering IS
        # the recommendation: a slow mode only surfaces when nothing faster is
        # currently live for that tier, never displacing a faster live option.
        for lst in by_tier.values():  # fastest crack first; normal before storms/SP
            lst.sort(key=lambda f: (f["storm"], f["hard"], effort.mode_minutes(f["mission"]), f["node"]))
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
    result.equipment_prerequisites = dict(plan.equipment_prerequisites)

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

    invasion_parts = {name for names in invasion_hits.values() for name in names}
    result.priority_actions = build_priority_actions(result, invasion_parts=invasion_parts)

    return result


def build_priority_actions(
    result: RouteResult, invasion_parts: set[str] | None = None
) -> list[PriorityAction]:
    """Rank plan_route's live-worldstate signals into "do this now" / "do
    this soon" / "better with a squad" — a synthesis, not a new data source.
    Pure: only reads fields plan_route already populated on ``result`` plus
    ``invasion_parts`` (the item names plan_route's own invasion_hits already
    matched). Called from inside plan_route itself, right before it returns,
    since everything it reads is already computed by that point.

    ``invasion_parts`` is passed explicitly rather than re-derived from
    ``result.event_source`` by matching an "Invasion — " string prefix:
    that dict also holds non-invasion transient/event entries (bounties,
    Kahl's Garrison, ...) built the same way, so filtering by wording
    would silently break if worldstate.invasion_rewards()'s description
    format ever changes.

    "now" = expires within roughly a day (Darvo, Baro, a fissure that's
    open right now — the plan's own live_fissure/farm_node_live flags).
    "soon" = rotates over days to weeks, no fixed deadline (invasions).
    "squad" = not time-limited at all, just meaningfully faster/better
    with 4 players (Radiant relics, endless-mode rotations). Varzia is
    deliberately not a signal here — see plan_route's docstring.
    """
    actions: list[PriorityAction] = []

    if result.daily_deal:
        d = result.daily_deal
        actions.append(PriorityAction(
            urgency="now",
            title=f"Darvo's Daily Deal: {d['item']}",
            detail=f"{d['discount']}% off — Darvo's deals last one day only.",
            expiry=d.get("expiry"),
        ))

    if result.baro:
        actions.append(PriorityAction(
            urgency="now",
            title=f"Baro Ki'Teer has {len(result.baro['items'])} item(s) you need",
            detail=f"At {result.baro['location']} — he leaves in about two days "
                   "and his stock rotates every visit.",
            expiry=result.baro.get("until"),
        ))

    live_fissure_nodes = [m.node for m in result.non_prime if m.live_fissure]
    if live_fissure_nodes:
        shown = ", ".join(live_fissure_nodes[:5])
        more = "…" if len(live_fissure_nodes) > 5 else ""
        actions.append(PriorityAction(
            urgency="now",
            title=f"{len(live_fissure_nodes)} route node(s) are open fissures right now",
            detail=f"Bring a relic and crack it in the same run as the part farm: "
                   f"{shown}{more}.",
        ))

    live_relic_farms = [pr.relic for pr in result.prime if pr.farm_node_live]
    if live_relic_farms:
        shown = ", ".join(live_relic_farms[:5])
        more = "…" if len(live_relic_farms) > 5 else ""
        actions.append(PriorityAction(
            urgency="now",
            title=f"{len(live_relic_farms)} relic farm node(s) are open fissures right now",
            detail=f"Farm and crack together in one run: {shown}{more}.",
        ))

    invasion_parts_sorted = sorted(invasion_parts or set())
    if invasion_parts_sorted:
        shown = ", ".join(invasion_parts_sorted[:5])
        more = "…" if len(invasion_parts_sorted) > 5 else ""
        actions.append(PriorityAction(
            urgency="soon",
            title=f"{len(invasion_parts_sorted)} needed item(s) are current invasion rewards",
            detail=f"Invasions resolve in hours to a couple of days, then are gone: "
                   f"{shown}{more}.",
        ))

    if not result.squad_radiant:
        # best_refinement is computed at whatever squad_size the plan already
        # uses (1, since squad_radiant is off here) — so "Radiant" here means
        # the tool's own math already found Radiant fastest solo for this
        # relic. Don't claim solo isn't worth it; that would contradict the
        # plan's own recommendation. Squad cracking is still worth flagging:
        # it multiplies rare-part rolls further on top of that.
        radiant_worth_it = [pr.relic for pr in result.prime if pr.best_refinement == "Radiant"]
        if radiant_worth_it:
            actions.append(PriorityAction(
                urgency="squad",
                title=f"{len(radiant_worth_it)} relic(s) farm fastest as Radiant",
                detail="Refine to Radiant when cracking these — already the fastest "
                       "option for the parts you need. Enable 4× squad radiant "
                       "cracking too: sharing cracks across a squad multiplies your "
                       "rare-part rolls.",
            ))

    squad_modes = sorted({
        m.game_mode for m in result.non_prime if m.game_mode in effort.ENDLESS_MODES
    } | {
        pr.farm_mode for pr in result.prime if pr.farm_mode in effort.ENDLESS_MODES
    })
    if squad_modes:
        actions.append(PriorityAction(
            urgency="squad",
            title=f"{len(squad_modes)} endless mode(s) in this route reward teamwork",
            detail=", ".join(squad_modes) + " — a full squad clears rotations faster "
                   "and more reliably (more hands on simultaneous objectives).",
        ))

    order = {"now": 0, "soon": 1, "squad": 2}
    actions.sort(key=lambda a: order.get(a.urgency, 99))
    return actions


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


def build_buy_vs_farm(result: RouteResult, prices: dict[str, dict]) -> list[BuyVsFarm]:
    """Pair each priced item (from :func:`select_price_candidates` +
    ``market.fetch_prices``) with what farming it actually costs, ranked worst
    farm first — the practical "what's most worth buying instead" answer.

    Pure, no I/O: ``prices`` is already-fetched. Vaulted equipment sorts first
    (no farm route exists at all, buying/trading is the *only* option); the
    rest sorts by descending relic/mission minutes. A part that shares its
    relic/mission with other needed parts is flagged via ``shared_with`` —
    buying it doesn't remove that run from the plan if you still need the
    others, so the "minutes" figure is what farming that *run* costs, not a
    guaranteed save from buying this one part.
    """
    part_source: dict[str, tuple[float | None, str, int]] = {}
    for pr in result.prime:
        for p in pr.parts:
            part_source[p] = (pr.minutes, pr.relic, len(pr.parts))
    for m in result.non_prime:
        for p in m.parts:
            part_source[p] = (m.minutes, m.node, len(m.parts))

    out: list[BuyVsFarm] = []
    for name, price in prices.items():
        if name in result.vaulted_equipment:
            out.append(BuyVsFarm(item=name, plat=price["plat"], tradable=price["tradable"],
                                 url=price.get("url"), minutes=None, source=None))
            continue
        src = part_source.get(name)
        if not src:
            continue
        minutes, source, shared = src
        out.append(BuyVsFarm(item=name, plat=price["plat"], tradable=price["tradable"],
                             url=price.get("url"), minutes=minutes, source=source,
                             shared_with=shared - 1))

    out.sort(key=lambda b: (b.minutes is not None, -(b.minutes or 0)))
    return out


def resource_needs_and_credits(
    equipment_names: list[str],
    blueprints: dict[str, dict],
    owned_resources: dict[str, int] | None = None,
) -> tuple[list[ResourceNeed], int]:
    """Sum both raw crafting-resource needs and total credits across every
    still-missing item, in a single walk of the blueprint tree.

    Pure, no I/O — ``blueprints`` is already-fetched (blueprint_costs.
    load_blueprints); called from cli.py/web.py after plan_route returns,
    same reasoning as select_price_candidates/build_buy_vs_farm. An
    equipment name with no match in ``blueprints`` (~30% of the catalog —
    this data source's coverage is inherently partial, see blueprint_costs.py)
    contributes nothing rather than a guess. Callers previously did this as
    two separate passes (build_resource_needs() + total_credits_needed(),
    always called back to back) — each re-walking the same recursive
    blueprint_costs.expand_full_cost() tree and re-scanning
    find_blueprint_key() for the same names; this does it once.

    ``owned_resources`` (from private_inventory.owned_resources, when a live
    inventory was supplied) computes ``short_by`` — the actual "what am I
    missing" answer; without it, only the gross ``need`` is known and
    ``owned``/``short_by`` stay None. Sorted by shortfall (or gross need)
    descending, so the resource actually blocking you floats to the top.
    """
    index = blueprint_costs.build_key_index(blueprints)
    totals: dict[str, int] = {}
    credits_total = 0
    for name in equipment_names:
        key = blueprint_costs.find_blueprint_key(name, blueprints, index)
        if not key:
            continue
        resources, credits = blueprint_costs.expand_full_cost(key, blueprints)
        credits_total += credits
        for res, cnt in resources.items():
            totals[res] = totals.get(res, 0) + cnt

    out: list[ResourceNeed] = []
    for res, need in totals.items():
        if owned_resources is None:
            out.append(ResourceNeed(resource=res, need=need))
        else:
            owned = owned_resources.get(res, 0)
            out.append(ResourceNeed(resource=res, need=need, owned=owned,
                                    short_by=max(0, need - owned)))

    if owned_resources is None:
        out.sort(key=lambda r: -r.need)
    else:
        out.sort(key=lambda r: (-(r.short_by or 0), -r.need))
    return out, credits_total


def build_resource_needs(
    equipment_names: list[str],
    blueprints: dict[str, dict],
    owned_resources: dict[str, int] | None = None,
) -> list[ResourceNeed]:
    """Resource-only wrapper around resource_needs_and_credits(), for
    callers that don't also need the credits total (production code that
    needs both should call resource_needs_and_credits() directly instead of
    pairing this with total_credits_needed() — see that function's note)."""
    resource_needs, _credits = resource_needs_and_credits(
        equipment_names, blueprints, owned_resources)
    return resource_needs


def total_credits_needed(equipment_names: list[str], blueprints: dict[str, dict]) -> int:
    """Credits-only wrapper around resource_needs_and_credits(), for callers
    that don't also need the resource breakdown."""
    _resource_needs, credits = resource_needs_and_credits(equipment_names, blueprints)
    return credits


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
