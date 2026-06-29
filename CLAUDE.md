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

   A component counts as a **part** only if its `uniqueName` contains `/Recipes/`;
   this filters out raw resources (Cryotic, Salvage, Neurodes, Orokin Cell, …) that
   also have drop locations. Equipment that yields no farmable part (market/clan/
   syndicate/lich/Baro/quest) is reported in `no_mission_source`. **Only the
   non-Prime side uses `optimize.py`**; the Prime side is a per-part relic listing.

   **`private_inventory.py`** — the full inventory the public profile can't expose.
   `run_helper(path)` shells out to warframe-api-helper (game must be running) and
   reads the `inventory.json` it writes into the cache dir; `fetch_inventory(account_id,
   nonce)` downloads it live from authenticated `mobile.warframe.com/api/inventory.php`
   (nonce from the running game; no password); `load_inventory(path)` reads a saved
   file. `owned_parts()` maps
   each `MiscItems`/`Recipes` component `uniqueName` to the part's display name **via
   the same component `drop.type`** the chain uses, so a loose part lines up exactly
   with a needed part (subtracted in `cli.py`). Built equipment is resolved to owned
   gear by feeding all `ItemType`s through `sync.resolve_names`. A **live** inventory
   (`--helper`/`--nonce`) is authoritative and supersedes the public profile (it
   includes built-but-unmastered gear `XPInfo` misses), so `cli.py` skips public sync
   then; a saved `--inventory` file still also pulls the profile (it may be partial).

4. **`optimize.py`** — fewest-missions is **set cover (NP-hard)**, solved with the
   greedy heuristic. Returns a `Route` of `RouteStep`s plus `uncovered`. Used for the
   **non-Prime** `direct_nodes`/`direct_parts` only — the Prime side is tier-farmed,
   not node-routed.

5. **`service.py`** — UI-agnostic core shared by CLI and web. `plan_route()` takes
   resolved `owned`/`want`/`owned_parts` sets + datasets and returns a structured
   `RouteResult` (missions, prime parts+relics, tier guide, vaulted, no-source).
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

Item names are matched via case-folded, whitespace-trimmed normalization
(`name.strip().casefold()`). It is currently duplicated as `_normalize` in
`inventory.py`/`optimize.py` and `normalize` in `items.py` (re-exported through
`acquisition`). **If you change it, change every copy** or matching silently
breaks. In `optimize.py`, "needed" names are already normalized; `Node.items` are
normalized on comparison (so feeding already-normalized part names is idempotent).

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

3. **Coverage ignores RNG and cracking.** Set-cover treats a node as "covers part P"
   if it drops a relic containing P, ignoring drop chance, relic refinement, and the
   separate void-fissure cracking step. Fine for "which missions give access to the
   relics", but a time/expected-runs objective would need the discarded chance data.

The modular pipeline is structured so each can be added without disturbing the
others; `optimize.py` stays objective-agnostic.
