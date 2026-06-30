"""Fetch and cache Warframe drop-table data from the public WFCD API.

The drop data lives at https://drops.warframestat.us/data/. We use
``missionRewards.json`` because it maps planet -> node -> rotation -> rewards,
which is exactly the shape we need to build node coverage.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

MISSION_REWARDS_URL = "https://drops.warframestat.us/data/missionRewards.json"
TRANSIENT_REWARDS_URL = "https://drops.warframestat.us/data/transientRewards.json"

# Where downloaded drop data is cached between runs.
CACHE_DIR = Path.home() / ".cache" / "warframe-optimize-routes"
CACHE_FILE = CACHE_DIR / "missionRewards.json"
TRANSIENT_CACHE_FILE = CACHE_DIR / "transientRewards.json"

# Re-download if the cache is older than this (seconds). One day by default.
CACHE_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class Node:
    """A single farmable mission node and the items it can drop.

    ``items`` is the set of canonical item names available across all
    rotations on this node. Rotation/chance detail is intentionally dropped
    here because the fewest-missions objective only cares about coverage.
    """

    planet: str
    name: str
    game_mode: str
    items: frozenset[str]

    @property
    def key(self) -> str:
        return f"{self.planet} - {self.name}"


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    age = time.time() - CACHE_FILE.stat().st_mtime
    return age < CACHE_TTL_SECONDS


def load_raw(force_refresh: bool = False) -> dict:
    """Return the raw missionRewards JSON, using the on-disk cache when fresh."""
    if not force_refresh and _cache_is_fresh():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    resp = requests.get(MISSION_REWARDS_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def parse_nodes(raw: dict) -> list[Node]:
    """Flatten the planet -> node -> rotation structure into a list of Nodes."""
    rewards_root = raw.get("missionRewards", raw)
    nodes: list[Node] = []

    for planet, planet_nodes in rewards_root.items():
        if not isinstance(planet_nodes, dict):
            continue
        for node_name, node_data in planet_nodes.items():
            if not isinstance(node_data, dict):
                continue
            items = _collect_items(node_data.get("rewards", {}))
            if not items:
                continue
            nodes.append(
                Node(
                    planet=planet,
                    name=node_name,
                    game_mode=node_data.get("gameMode", "Unknown"),
                    items=frozenset(items),
                )
            )
    return nodes


def _collect_items(rewards) -> set[str]:
    """Gather item names from a node's rewards block.

    ``rewards`` is either a flat list of reward dicts or a mapping of
    rotation name -> list of reward dicts.
    """
    items: set[str] = set()
    if isinstance(rewards, list):
        reward_lists = [rewards]
    elif isinstance(rewards, dict):
        reward_lists = list(rewards.values())
    else:
        return items

    for reward_list in reward_lists:
        if not isinstance(reward_list, list):
            continue
        for reward in reward_list:
            name = reward.get("itemName") if isinstance(reward, dict) else None
            if name:
                items.add(name.strip())
    return items


def load_nodes(force_refresh: bool = False) -> list[Node]:
    """Convenience: fetch (or read cache) and parse into Node objects."""
    return parse_nodes(load_raw(force_refresh=force_refresh))


def load_transient_raw(force_refresh: bool = False) -> list:
    """Return transientRewards.json (list of event/transient objectives), cached."""
    if not force_refresh and TRANSIENT_CACHE_FILE.exists():
        if (time.time() - TRANSIENT_CACHE_FILE.stat().st_mtime) < CACHE_TTL_SECONDS:
            return json.loads(TRANSIENT_CACHE_FILE.read_text(encoding="utf-8"))

    resp = requests.get(TRANSIENT_REWARDS_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TRANSIENT_CACHE_FILE.write_text(json.dumps(raw), encoding="utf-8")
    return raw
