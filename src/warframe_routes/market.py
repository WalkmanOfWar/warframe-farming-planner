"""Live warframe.market trade prices, proxied through the WFCD price-check API.

Farming isn't always the best use of time: some parts take dozens of hours to
farm but cost a handful of platinum to buy from another player. This module
answers "is it worth buying instead?" for a *curated* set of expensive or
otherwise-unfarmable items — never for everything in a plan, to keep the
number of outbound requests (and route-planning latency) bounded. Candidate
selection lives in :func:`warframe_routes.service.select_price_candidates`;
this module only knows how to price a given list of names.

There is no bulk endpoint, so one request per item is required. Requests are
parallelized (``ThreadPoolExecutor``) and cached locally for 30 minutes —
trade prices move faster than mission/worldstate data, so the TTL is shorter
than :mod:`data`'s. A failed or unmatched lookup is silently skipped: a
missing price is not an error, the farming route stands on its own without it.

Full equipment (a complete frame/weapon) is sold on warframe.market as a
``"<Name> Set"`` blueprint bundle, priced differently from any single loose
part — e.g. ``"Corinth Prime"`` alone best-matches a single stray component
at ~19p, while ``"Corinth Prime Set"`` correctly prices the full build at
~83p. So the equipment-level candidates this module receives should already
be bare equipment names; :func:`_fetch_one` tries the ``" Set"`` suffix
first and falls back to the bare name only for individual loose parts
(which already carry their own suffix, e.g. ``"Corinth Prime Barrel"``).
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .data import CACHE_DIR
from .items import normalize

PRICECHECK_URL = "https://api.warframestat.us/pricecheck/find/{}"
_CACHE_FILE = CACHE_DIR / "market_prices.json"
_TTL = 30 * 60  # seconds
_TIMEOUT = 8
_MAX_WORKERS = 6


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass  # a failed cache write shouldn't break price lookups


def _fetch_one(query: str) -> dict | None:
    """Try ``"<query> Set"`` (the full-blueprint-bundle convention) then the
    bare name; returns the first match with an average price, or None."""
    for candidate in (f"{query} Set", query):
        try:
            resp = requests.get(PRICECHECK_URL.format(candidate), timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue
        if isinstance(data, list) and data:
            entry = data[0]
            avg = (entry.get("prices") or {}).get("average")
            if avg is not None:
                return {
                    "name": entry.get("name", candidate),
                    "plat": avg,
                    "tradable": bool(entry.get("tradable", True)),
                    "url": entry.get("url"),
                }
    return None


def fetch_prices(names: list[str]) -> dict[str, dict]:
    """Fetch warframe.market average prices for the given item names.

    Returns ``display_name -> {name, plat, tradable, url}`` for every match;
    names with no match (or a failed lookup) are simply absent from the
    result — never an error. Caller must already have applied a bound on
    ``len(names)``; this function makes exactly one request per uncached name.
    """
    names = list(dict.fromkeys(n for n in names if n))  # dedupe, preserve order
    if not names:
        return {}

    cache = _load_cache()
    now = time.time()
    out: dict[str, dict] = {}
    to_fetch: list[str] = []
    for n in names:
        entry = cache.get(normalize(n))
        if entry and now - entry.get("_fetched", 0) < _TTL:
            if entry.get("price"):
                out[n] = entry["price"]
            continue
        to_fetch.append(n)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, n): n for n in to_fetch}
            for fut in as_completed(futures):
                n = futures[fut]
                try:
                    price = fut.result()
                except Exception:
                    price = None
                cache[normalize(n)] = {"price": price, "_fetched": now}
                if price:
                    out[n] = price
        _save_cache(cache)

    return out
