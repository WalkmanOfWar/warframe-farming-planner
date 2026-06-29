# warframe-optimize-routes

A CLI that suggests **fewest-mission farming routes** in Warframe. Point it at your
account and it figures out **everything you don't own yet** and returns the smallest
set of mission nodes that covers it. Drop-table and item data come from the public
[warframestat / WFCD](https://docs.warframestat.us) APIs.

A web frontend is planned; the optimization logic lives in a reusable package so
the same core can back both the CLI and a future site.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Best: Warframe running -> auto-pull full inventory via warframe-api-helper
wfroutes route --helper path/to/warframe-api-helper.exe

# Same data from accountId + a live nonce (no helper run each time)
wfroutes route --account-id <your-account-id> --nonce <session-nonce>

# Or a saved inventory.json export
wfroutes route --inventory inventory.json

# Public profile only (owned gear, but NOT loose parts / unmastered gear)
wfroutes route --account-id <your-account-id>
```

- `--helper`: with Warframe **running**, runs
  [warframe-api-helper](https://github.com/Sainan/warframe-api-helper) for you and
  reads the full inventory it pulls — owned gear (even built-but-unmastered) **and
  loose parts**. No file, no password. Recommended.
- `--account-id` + `--nonce`: same full download without re-running the helper each
  time (grab `accountId`+`nonce` once; the nonce dies when you close the game).
- `--inventory`: a saved `inventory.json` (AlecaFrame / helper export).
- `--account-id` (alone): only what you've *mastered* from your public profile.
  The public API **can't see loose parts or built-but-unmastered gear** (only
  mastered items + your equipped loadout), so it over-lists unfinished sets.
- `--wishlist` (optional): narrow the target to these items. **Omit it and the
  target is every masterable item you don't already own.**
- `--owned` / `--have-parts` (optional): manual JSON lists of owned items / loose
  parts, if you can't use `--inventory`.
- `--refresh`: force re-download of drop data instead of using the local cache.

### Why a helper is needed

The public profile can't see un-built parts or unmastered gear. The full inventory
is only on an authenticated endpoint whose token (`nonce`) lives in your *running
game's* session. [warframe-api-helper](https://github.com/Sainan/warframe-api-helper/releases/latest)
reads that token from the live game (no password) and pulls the inventory — that's
what `--helper` runs for you.

> A fully hands-off fetch (no helper) would need either your password — which would
> log you out of the game, since Warframe allows one session — or re-implementing
> the helper's game-memory read ourselves. Hence the helper step.

Output is split by how you actually farm each thing:

- **Non-Prime** parts drop from a specific boss/mission, so these are routed as a
  **fewest-missions** plan over those nodes.
- **Prime** parts come from **relics**, and you can't farm a specific relic — you
  farm its **tier** (Lith/Meso/Neo/Axi) and crack it at a void fissure. So each
  Prime part is listed with the in-rotation relic(s) that drop it, plus a short
  per-tier farming guide (e.g. *Lith → Hepit, Meso/Neo → Ukko, Axi → Apollo*).
  Parts whose relics aren't currently dropping (**vaulted**) are listed separately.

Raw resources (Cryotic, Salvage, …) are ignored, and gear with no mission source
(market, clan, syndicate, lich/sister, Baro, quest) is listed separately.

### Finding your Account ID

This is **not** your username. It's a 24-character hex id:

- **Browser:** log into [warframe.com](https://www.warframe.com), open DevTools
  (F12) → Application → Cookies → copy the `gid` value, **or**
- **Game logs:** open `%localappdata%\Warframe\EE.log`, search for "Logged in" —
  the id is in parentheses.

## How it works

1. **Owned** comes from your public profile (`sync.py`, by Account ID) — the items
   you've mastered.
2. **Target** is every masterable item (`catalog.py`), or your `--wishlist`.
3. **Acquisition chain** (`acquisition.py`) expands missing gear → parts → sources:
   Prime parts via currently-dropping relics, non-Prime parts via boss/mission nodes.
4. **Optimize** (`optimize.py`) solves the fewest-missions **set cover** (NP-hard)
   with a greedy heuristic over the parts.

Data comes from the public warframestat / WFCD APIs and is cached for a day under
`~/.cache/warframe-optimize-routes/` (`--refresh` to force re-download).

## Web UI

A local React UI (same engine as the CLI) is in `frontend/`. Build it once, then
serve it from the Python backend:

```bash
pip install -e ".[web]"
cd frontend && npm install && npm run build && cd ..
wfroutes serve                      # -> http://127.0.0.1:8000
```

Open the URL, enter your Account ID (and optionally a nonce / inventory.json /
wishlist), and hit **Plan route**.

For frontend development with hot-reload, run the backend and the Vite dev server
side by side (the dev server proxies `/api` to port 8000):

```bash
wfroutes serve                      # terminal 1 (API on :8000)
cd frontend && npm run dev          # terminal 2 (UI on :5173)
```

## Credits & data sources

This tool is just a planner on top of data and tools built by others. Huge thanks to:

- **[Digital Extremes](https://www.digitalextremes.com/)** — creators of
  [Warframe](https://www.warframe.com/) and the underlying game data. This project
  is an unofficial fan tool and is **not affiliated with or endorsed by Digital
  Extremes**.
- **[Warframe Community Developers (WFCD)](https://github.com/WFCD)** — for the
  open data and APIs this relies on:
  - [warframestat.us](https://docs.warframestat.us/) — the items API
    (`api.warframestat.us`) used for items, components and vaulted status.
  - [drops.warframestat.us](https://drops.warframestat.us/) — the parsed mission
    drop tables (relics & boss drops).
  - [WFCD/warframe-items](https://github.com/WFCD/warframe-items) and
    [WFCD/profile-parser](https://github.com/WFCD/profile-parser) — which documented
    the public profile structure (`LoadOutInventory.XPInfo`).
- **[Sainan](https://github.com/Sainan)** — for
  [warframe-api-helper](https://github.com/Sainan/warframe-api-helper), the
  read-only tool that pulls your full inventory from the running game (used by
  `--helper`), and the OpenWF import docs that documented the inventory endpoint.
- **[AlecaFrame](https://alecaframe.com/)** — an alternative source of the
  `inventory.json` export.

All trademarks and game content belong to Digital Extremes. No game assets are
redistributed here — data is fetched live from the public APIs above.

## License

[MIT](LICENSE).
