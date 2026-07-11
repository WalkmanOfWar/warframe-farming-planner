# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python CLI (`wfroutes`) that recommends **fewest-mission Warframe farming routes**.
The primary use is "farm everything I don't own yet": the player gives their Account
ID, owned items are auto-synced from their public profile, and the **default target
is every masterable item minus what they own**. A `--wishlist` can narrow the target
to specific items, and `--owned` can supply ownership manually. The tool returns the
smallest set of mission nodes covering the missing items. A web frontend is planned,
so core logic stays UI-agnostic in the package and the CLI is a thin layer on top.

## Commands

```bash
pip install -e ".[dev]"          # install package + dev deps (pytest, responses)
python -m pytest -q              # run all tests
python -m pytest tests/test_optimize.py::test_greedy_picks_fewest_nodes  # single test
wfroutes route --helper path/to/warframe-api-helper.exe   # best: auto-pull full inventory (game open)
wfroutes route --account-id <id> --nonce <nonce>          # full inventory via live nonce
wfroutes route --account-id <id>                          # public profile only (no loose parts)
python -m warframe_routes.cli route --inventory examples/inventory.sample.json --account-id <id>

pip install -e ".[web]"          # install FastAPI + uvicorn for the web UI
cd frontend && npm install && npm run build && cd ..   # build the React SPA -> frontend/dist
wfroutes serve                   # serve API + built UI at http://127.0.0.1:8000
cd frontend && npm run dev       # frontend dev server (proxies /api to :8000)
cd frontend && npm test          # Vitest + Testing Library for App.jsx
```

Use `python -m warframe_routes.cli` rather than the `wfroutes` script when its
install location is not on PATH (common on Windows; see install warning).

## Architecture

The pipeline is a staged flow, one module per stage under `src/warframe_routes/`:

1. **`data.py`** — fetches drop tables from the WFCD API
   (`drops.warframestat.us/data/missionRewards.json`) and caches them at
   `~/.cache/warframe-optimize-routes/` (1-day TTL, `--refresh` bypasses).
   `parse_nodes()` flattens the API's `planet -> node -> rotation -> rewards`
   shape into flat `Node` objects. **Rotation and drop-chance detail are
   deliberately discarded** — a `Node` carries only the *set* of item names it
   can drop, because the fewest-missions objective only cares about coverage, not
   probability. Rewards come in two shapes (a flat list, or a rotation→list
   dict); `_collect_items` handles both.

2. **`inventory.py`** — loads owned/wishlist JSON files (plain lists of item-name
   strings) and computes `needed = target - owned`.

   **`catalog.py`** — supplies the *default* target: every masterable item in the
   game, from the warframestat items dataset (filter `masterable == true`). Used
   when no `--wishlist` is given, so the tool answers "what am I still missing?".

   **`sync.py`** — alternative owned-items source: fetches the public profile from
   `api.warframe.com/cdn/getProfileViewingData.php?playerId=<id>` (keyed by the
   24-hex **Account ID**, NOT username — the old `content.warframe.com/dynamic/...`
   host is dead), reads `Results[0].LoadOutInventory.XPInfo` (each `{ItemType:
   <uniqueName>, XP}`) for everything the player has *mastered*, then resolves those
   internal uniqueNames to display names via the cached items dataset (`items.py`).
   Account-ID format is validated *before* any network call. **`resolve_names` only
   maps masterable, non-`Node` items**: completed star-chart nodes also appear in
   `XPInfo` and can share a display name with a frame (the "Caliban" node vs the
   Caliban frame), so without that filter a mastered node would falsely mark the
   frame as owned. Note internal codenames diverge from display names (Caliban's
   uniqueName is `/Lotus/Powersuits/Sentient/Sentient`), so never infer ownership by
   substring-matching uniqueNames — always go through `resolve_names`.

3. **`items.py` + `acquisition.py`** — the acquisition chain. `items.py`
   fetches/caches the slim items dataset (`name,uniqueName,vaulted,type,masterable,
   components`, ~9 MB) and owns `normalize`, `base_relic_name` (strips the
   `(Exceptional|Flawless|Radiant)` relic refinement suffix), `relic_tier` (first
   token, e.g. `Axi C10 Relic` → `Axi`) and `parse_location` (`"<planet>/<node>
   (<mode>)"` → tuple). `acquisition.build_plan()` expands missing **equipment** into
   **parts** and splits them by **how you actually farm each**, because the two
   models differ fundamentally:
   - **Prime parts** (`drop.location` contains "Relic") → `prime_part_relics`:
     `part → {in-rotation relic display}`. **No node routing** — you can't farm a
     specific relic, you farm its *tier* (the CLI prints a tier guide). A relic is
     in-rotation iff it currently appears in `missionRewards`; parts with no live
     relic are vaulted → `not_farmable` (`vaulted_equipment()` flags fully-gone gear).
   - **Non-Prime parts** (`drop.location` parses to a node) → `direct_nodes` /
     `direct_parts`, a genuine fewest-missions **set-cover** fed to `optimize_route`.

   A component counts as a **part** iff `items.is_part_component(uniqueName)` —
   `/Recipes/` (filters out raw resources: Cryotic, Salvage, Neurodes, Orokin
   Cell, …) **or** `/InfestedMicroplanet/Resources/Mechs/` (Necramech vault
   parts — Voidrig/Bonewidow/Morgha/Cortege — which WFCD names outside
   `/Recipes/` even though they're one-per-item components exactly like a
   Chassis; no drop table lists Isolation Vault rewards, so without this
   marker they silently vanished from the plan instead of surfacing as
   "no known source", which `service.plan_route` now relabels into
   `special_source` — same mechanism as the Duviri-detection below).
   `items.part_display_name(equip, comp)` builds the fallback display name
   and skips re-prefixing when the component's own name already embeds the
   equipment name (a WFCD quirk specific to Necramech parts: `comp.name` is
   `"Voidrig Capsule"`, not `"Capsule"` — blindly prefixing would double it).
   Equipment that yields no farmable part (market/clan/syndicate/lich/Baro/
   quest) is reported in `no_mission_source`. **Only the non-Prime side uses
   `optimize.py`**; the Prime side is a per-part relic listing.

   `build_plan` also detects **prerequisite-weapon** components: ~19 items
   (Akbolto→Bolto, Dual Raza→Dual Kamas, Paracesis→Galatine, Zarr→Drakgoon,
   …) have a "component" that is really a reference to a whole other
   weapon's own `uniqueName` — you must already own that weapon to build
   this one, and WFCD doesn't model it as a drop or a Blueprint. These never
   affected part routing (they fail `is_part_component` and are skipped
   before reaching any bucket), but were previously invisible; now surfaced
   via `AcquisitionPlan.equipment_prerequisites` → `RouteResult.
   equipment_prerequisites` (equipment display name → required weapon name),
   rendered as a "requires: X" tag wherever that equipment appears in
   `no_part_source`/`no_mission_source`.

   **`private_inventory.py`** — the full inventory the public profile can't expose.
   `run_helper(path)` shells out to warframe-api-helper (game must be running) and
   reads the `inventory.json` it writes into the cache dir; `fetch_inventory(account_id,
   nonce)` downloads it live from authenticated `mobile.warframe.com/api/inventory.php`
   (nonce from the running game; no password); `load_inventory(path)` reads a saved
   file. `owned_parts()` maps
   each `MiscItems`/`Recipes` component `uniqueName` to the part's display name **via
   the same component `drop.type`** the chain uses, so a loose part lines up exactly
   with a needed part (subtracted in `cli.py`). Built equipment is resolved to owned
   gear by feeding all `ItemType`s through `sync.resolve_names`. `owned_relics()`
   counts held void projections by base relic name (refinements summed); the plan
   credits them — an owned relic costs only the fissure crack, no farming — and
   vaulted parts whose relic sits in the vault surface in `vaulted_crackable`.
   A **live** inventory
   (`--helper`/`--nonce`) is authoritative and supersedes the public profile (it
   includes built-but-unmastered gear `XPInfo` misses), so `cli.py` skips public sync
   then; a saved `--inventory` file still also pulls the profile (it may be partial).

4. **`optimize.py`** — objective-agnostic node selection (NP-hard set cover /
   facility-location, greedy). Two entry points, both returning a `Route` of
   `RouteStep`s + `uncovered`: `optimize_route` (fewest nodes, count-only) and
   `optimize_by_cost(nodes, needed, cost_fn)` (least **injected cost**, assigning
   each item to one node by smallest *marginal* cost — reuses stops, prefers
   higher-chance/faster nodes). **`service` uses `optimize_by_cost` with an
   expected-**time** cost for the non-Prime route**; `optimize_route` is the
   generic kept for tests/fallback. Prime side is tier-farmed, not node-routed.

   **`effort.py`** — turns drop **chances** into expected **runs** and **time**.
   Non-Prime: `1/p` per part, exact inclusion-exclusion coupon-collector for a
   node's set (mutually-exclusive "one drop per roll"); fat tables (>12 parts)
   fall back to an O(k) independent-rolls estimate. Prime: two-step
   `(1/d)(1/r + 1)` — farm the relic (node chance `r`) then crack it (in-relic
   chance `d`, refinement-dependent), modelled solo. `MODE_MINUTES`/`FISSURE_MINUTES`
   are rough per-mode time estimates (the one judgement part — tune freely). Pure
   functions; chances are **percentages**; `0`/missing ⇒ `inf` (unobtainable).
   `acquisition.build_plan` carries the chance data (`node_part_chance`,
   `part_relic_refine_chance`, `relic_source`) the model needs.
   `rotation_factor(rotation, mode)` scales that per-rotation time for how many
   rolls a deeper rotation actually costs: most endless modes follow the
   documented AABC cadence (A=1st roll, B=3rd, C=4th) via `ROTATION_FACTOR`,
   but **Disruption is a verified exception** (wiki.warframe.com/w/Disruption)
   — tier depends on round number *and* conduits defended per round, and a
   squad clearing all 4 conduits every round reaches B after round 1 and C
   after round 3, not "3x"/"4x" a single roll. Using the generic table for
   Disruption overestimated Neo/Axi relic farm time by ~30–70%, and
   Disruption is the tool's own `RELIC_TIER_GUIDE` recommendation for those
   tiers, so `DISRUPTION_ROTATION_FACTOR` is looked up separately whenever
   `mode == "Disruption"`. If another mode is ever found to deviate from
   AABC, add another mode-keyed table the same way rather than complicating
   the single dict.

5. **`service.py`** — UI-agnostic core shared by CLI and web. `plan_route()` takes
   resolved `owned`/`want`/`owned_parts` sets + datasets (+ a `refinement`) and
   returns a structured `RouteResult` (missions, prime parts+relics, tier guide,
   vaulted, no-source) **annotated with expected runs/time** via `effort.py`, plus
   `total_minutes`. Effort is a *displayed metric*, not the optimizer objective —
   routing is still fewest-missions. `inf` is sanitized to `None` (JSON-safe).
   Owns `RELIC_TIER_GUIDE`. **Both `cli.py` and `web.py` call this** — never
   reimplement plan assembly elsewhere.

6. **`cli.py`** — Click entry point. Resolves owned (helper/nonce/inventory/profile)
   + target (catalog/wishlist) + loose `owned_parts`, calls `service.plan_route`,
   prints it. Also hosts the `serve` command (launches `web.py` via uvicorn).

7. **`web.py` + `frontend/`** — local web UI. `web.py` is a FastAPI wrapper: `POST
   /api/route` does the same input resolution as the CLI and returns
   `RouteResult.to_dict()`; it serves the built React app (`frontend/dist`) at `/`
   when present. `frontend/` is a Vite + React SPA (dev server proxies `/api` to
   :8000). `catalog.all_targets(items_data)` derives the default target from the
   **already-loaded** items dataset — no second network call.

### Cross-cutting invariant: name normalization

Item names are matched via case-folded, whitespace-trimmed normalization.
**`items.normalize` is the single source of truth** (`(name or "").strip().
casefold()`); `inventory.py` and `optimize.py` import it as `_normalize`, and
`acquisition`/`service` use `items.normalize` directly. Change it in one place.
In `optimize.py`, "needed" names are already normalized; `Node.items` are
normalized on comparison (so feeding already-normalized part names is idempotent).

### Cross-cutting invariant: what counts as a farmable "part"

**`items.is_part_component`/`items.part_display_name` are the single source
of truth** for "is this component a farmable part" and "what do I call it
when the drop table gives no display string" — `acquisition.py` and
`private_inventory.py` both import and use them directly (never re-implement
the `/Recipes/` check locally). Any future equipment category whose WFCD
component naming doesn't follow the `/Recipes/` convention (like Necramech
vault parts) should extend `PART_PATH_MARKERS`, not add a parallel check.

## Conventions

- Source lives under `src/` (src-layout); imports are `from warframe_routes import ...`.
- Tests construct `Node`/profile objects directly or feed raw dicts to the parsers;
  they do **not** hit the network. Mock HTTP with the `responses` library (already a
  dev dep) — never make real requests. See `tests/test_sync.py` for the pattern.

## Known design gaps / next steps

Both the **Prime relic chain and the non-Prime direct chain are built**
(`acquisition.py`). Remaining gaps, in rough priority order:

1. **The public profile is doubly blind; use the private inventory.** `XPInfo`
   (`sync.py`) only exposes *mastered* gear, and the profile's loadout arrays only
   hold the *currently-equipped* items — so it misses both **loose parts** and
   **built-but-unmastered gear** (e.g. a crafted-but-unranked frame). The private
   inventory has all of it, via `--helper` (runs warframe-api-helper), `--account-id
   --nonce` (live `inventory.php`), or `--inventory file`. The **nonce reuses the
   running game's session** (no password, no kick). A built-in `login.php` (email/password) sync was deliberately *not*
   built: Warframe allows one session, so it would log the player out of their game,
   plus it handles the password and is grayer on ToS. A future no-touch option could
   read the live game's session token like warframe-api-helper does (OS-specific).

2. **Both chains are effort-optimized and joint.** Non-Prime minimizes expected
   **time** (`optimize_by_cost`), picking the best node when a part drops at
   several. Prime is **jointly** optimized over relics (`service._prime_relic_plan`
   reuses `optimize_by_cost`: a relic sharing several needed parts is cracked once
   for all of them), and 4× shared-radiant squad cracking is modelled via
   `effort.effective_squad_chance_pct` (`squad_radiant` flag through
   `plan_route`/the web UI). Time still uses rough per-mode estimates
   (`effort.MODE_MINUTES`) — the remaining judgement knob.

3. **Live worldstate is consulted; Nightwave and Sortie/Archon Hunt aren't.**
   `worldstate.py` filters event-only bounty drops against live
   `syndicateMissions` (15-min cache, graceful fallback when offline). Duviri
   Circuit gear is detected via `/Gameplay/Duviri/` component uniqueNames.
   Several other live sections are cross-referenced against needed items, all
   in `service.plan_route`: `fissures` (which relic tiers are actionable
   *right now*, plus double-dip detection when a route node is itself an open
   fissure — `Mission.live_fissure`/`PrimeRelic.tier_live`/`farm_node_live`),
   `voidTrader` (Baro Ki'Teer stock), `invasions` (matching rewards),
   `vaultTrader` (Varzia/Prime Resurgence — the *only* non-trade way to buy
   fully-vaulted equipment, matched against `vaulted_equipment`; store item
   names are inconsistent, e.g. `"Prime Corinth"` for `"Corinth Prime"`, so
   `worldstate.vault_trader_stock` indexes both word orders), and
   `dailyDeals` (Darvo's single rotating item). Nightwave cred-shop items are
   *not* labelled — `/pc/nightwave` exposes challenges/reputation only, never
   the rotating shop stock; there is no data source, live or static, short of
   hand-maintaining a JSON that goes stale every ~3-month season (rejected —
   not worth the upkeep for one section). Sortie/Archon Hunt were also
   evaluated and rejected: `/pc/sortie` and
   `/pc/archonHunt` both report `rewardPool: "Sortie Rewards"` (a label, not
   an item list), and even with real data these modes award Forma/Riven/
   Legendary Core/Archon Shards — not equipment parts, so they wouldn't fit
   this tool's "missing gear" model regardless. `flashSales` was checked too:
   all 24 live entries are cosmetic bundles/supporter packs, no equipment.

4. **`market.py`** — trade-vs-farm advice via `/pricecheck` (WFCD's proxy for
   warframe.market). Farming isn't always the right call: some parts take
   dozens of hours but cost a handful of platinum. `service.
   select_price_candidates()` (pure, no I/O) picks a *bounded* set worth a
   lookup — every fully-vaulted equipment name unconditionally, plus parts
   whose parent relic/mission time is ≥ `PRICE_CHECK_MIN_MINUTES` (120),
   capped at `PRICE_CHECK_MAX_ITEMS` (15) since there's no bulk price
   endpoint. `market.fetch_prices()` then does the actual (parallelized,
   30-min-cached) HTTP calls — called from `cli.py`/`web.py` **after**
   `plan_route` returns, not from inside it, preserving the invariant that
   `plan_route` itself makes no network calls (matters for testability: its
   tests feed plain dicts, no mocking). Full equipment queries try a
   `"<name> Set"` suffix first (the warframe.market full-blueprint-bundle
   convention — `"Titania Prime"` alone would match a stray single part at a
   misleadingly low price) falling back to the bare name for loose parts,
   which are already individually tradable under their own name. This was
   found via a full audit of WFCD's OpenAPI spec (99 endpoints) requested to
   check for anything else worth optimizing — `/drops` (a flatter, less
   useful re-serving of the same source data we already parse directly) and
   `/pc/arbitration` (broken upstream right now, and Vitus Essence isn't
   equipment anyway) were also checked and rejected.

   `service.build_buy_vs_farm()` turns the raw `market_prices` dict into the
   actual recommendation: each priced item paired with what farming it would
   cost (the parent relic's/mission's `minutes`), ranked worst-farm-first —
   fully-vaulted equipment always sorts to the top (no farm route exists at
   all). A part is flagged with `shared_with` when its relic/mission also
   covers other still-needed parts, since buying just that one part doesn't
   remove the run from the route if you need the others anyway — the UI
   surfaces this as a tooltip rather than overclaiming a guaranteed time save.
   Also pure/no I/O; called from `cli.py`/`web.py` right alongside
   `fetch_prices()`, same reasoning as `select_price_candidates`.

5. **`blueprint_costs.py`** — raw crafting-resource totals (Orokin Cell,
   Ferrite, Neurodes, …) for everything still missing, from a data source
   **completely separate** from the rest of this tool: the Warframe Wiki's
   `Module:Blueprints/data`, not WFCD/warframestat. Verified live against
   Rhino/Chroma/Ash Prime/Braton that WFCD's `/items` and `/warframes/{item}`
   never carry more than an incidental one-off resource, and confirmed via
   [WFCD/warframe-items#276](https://github.com/WFCD/warframe-items/issues/276)
   (closed "not planned") that this is a permanent upstream gap, not a
   field-selection fix. The wiki module *does* have full recipes, but only as
   raw Lua table source (`?action=raw`, no JSON API, no stability contract)
   — the most fragile integration in this codebase; `_parse_lua_table` is a
   small hand-rolled tokenizer/parser for this data-only Lua dialect (tables,
   strings, numbers, `true`/`false`/`nil`, `--` comments — no expressions to
   evaluate, so a full Lua interpreter dependency isn't needed). A parse or
   fetch failure degrades to an empty dict, never a crash or a guess.

   Two real parsing traps, found by diffing raw top-level key counts against
   what actually parsed: (1) the module has multiple top-level categories
   (`Blueprints` for weapons, `Suits` for Warframes/Necramechs, possibly more)
   that must be merged, not just read from one hardcoded key; (2) weapon
   sub-parts (Barrel/Receiver/Stock) usually carry an embedded `Cost` block
   (self-contained recipe) but Warframe sub-parts (Chassis/Neuroptics/
   Systems) don't — instead each is its *own* top-level entry named
   `"<Frame> <Part>"`, and Prime frames need word-overlap dedup on top of that
   (`"Ash Prime"` + `"Prime Chassis"` → `"Ash Prime Chassis"`, not the naive
   double-up `"Ash Prime Prime Chassis"` — see `_join_sibling_name`).
   `expand_resource_cost()` recurses through both shapes into one flat total.

   Coverage is **inherently partial** (~70% of the masterable catalog, e.g.
   Sentinels aren't in the wiki module at all) — `service.
   build_resource_needs()` silently omits anything unmatched rather than
   estimating, and the UI/CLI say so explicitly. `private_inventory.
   owned_resources()` (built from exactly the component entries `items.
   is_part_component` already excludes as "not a part") turns the gross
   total into an actual shortfall when a live inventory is available;
   without one, only the gross need is shown.

   The same wiki data carries a `Credits` cost per blueprint, ignored until
   `expand_full_cost()` (the resource-only `expand_resource_cost()` is now a
   thin wrapper around it) started accumulating it alongside resources through
   both sub-part shapes. `service.total_credits_needed()` sums it across every
   still-missing item the same way `build_resource_needs()` sums resources —
   surfaced as `RouteResult.credits_needed`.

The modular pipeline is structured so each can be added without disturbing the
others; `optimize.py` stays objective-agnostic.
