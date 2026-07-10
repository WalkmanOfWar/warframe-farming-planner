"""Foundry resource costs, sourced from the Warframe Wiki's blueprint data
module — a *completely separate* data source from everything else in this
pipeline (WFCD/warframestat, warframe.market). WFCD's own item dataset does
not track this: `/items`, `/warframes/{item}` and the full unfiltered item
record all omit build-resource quantities (confirmed live against Rhino,
Chroma, Ash Prime, Braton — none list more than an incidental one-off
resource), and WFCD's maintainers closed the upstream feature request for it
as "not planned" (github.com/WFCD/warframe-items/issues/276).

The wiki's ``Module:Blueprints/data`` *does* have it, but only as raw Lua
table source (``?action=raw``), not a JSON API — no formal stability
contract, unlike every other integration in this codebase. This module is
consequently the most fragile piece of the pipeline: if the wiki editors
restructure the module, parsing degrades to "no resource data" (caught and
surfaced as such), never a crash and never silently wrong numbers.

The Lua dialect here is data-only (no expressions, functions, or
metatables) — just nested tables, strings, numbers, and ``--`` line
comments — so a small hand-rolled tokenizer/parser is more auditable than a
general Lua interpreter dependency, and keeps this project's zero-heavy-deps
footprint.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from .data import CACHE_DIR
from .items import normalize

BLUEPRINTS_URL = (
    "https://wiki.warframe.com/index.php?title=Module:Blueprints/data&action=raw"
)
_RAW_CACHE_FILE = CACHE_DIR / "blueprints_raw.lua"
_PARSED_CACHE_FILE = CACHE_DIR / "blueprints_parsed.json"
_TTL = 24 * 60 * 60  # seconds — crafting recipes change only with game content updates

# A component whose Parts entry has one of these Types recurses into its own
# nested Cost.Parts (a sub-build, e.g. a weapon's Barrel/Receiver/Stock) —
# anything else (Type == "Resource") is a raw material, the leaf case.
_NESTED_PART_TYPES = {"Item", "PrimePart"}


# ── Minimal Lua-table tokenizer/parser (data-only dialect) ──────────────

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>--[^\n]*)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[{}\[\]=,])
""", re.VERBOSE)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"Unexpected character {text[pos]!r} at offset {pos}")
        pos = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment"):
            continue
        tokens.append((kind, m.group()))
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.i = 0

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _next(self) -> tuple[str, str]:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of input")
        self.i += 1
        return tok

    def _expect(self, text: str) -> None:
        kind, val = self._next()
        if val != text:
            raise ValueError(f"Expected {text!r}, got {val!r} at token {self.i}")

    def parse_value(self):
        kind, val = self._peek()
        if kind == "string":
            self._next()
            return val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if kind == "number":
            self._next()
            return float(val) if "." in val else int(val)
        if kind == "ident" and val in ("true", "false", "nil"):
            self._next()
            return {"true": True, "false": False, "nil": None}[val]
        if val == "{":
            return self.parse_table()
        raise ValueError(f"Unexpected token {val!r} while parsing a value")

    def parse_table(self):
        self._expect("{")
        obj: dict = {}
        arr: list = []
        while True:
            kind, val = self._peek()
            if val == "}":
                self._next()
                break
            if val == "[":
                self._next()
                key = self.parse_value()
                self._expect("]")
                self._expect("=")
                obj[key] = self.parse_value()
            elif kind == "ident":
                self._next()
                self._expect("=")
                obj[val] = self.parse_value()
            else:
                arr.append(self.parse_value())
            kind, val = self._peek() or (None, None)
            if val == ",":
                self._next()
            elif val != "}":
                raise ValueError(f"Expected ',' or '}}', got {val!r} at token {self.i}")
        return obj if obj else arr


def _parse_lua_table(text: str) -> dict:
    """Parse the module's ``return { ... }`` body into nested dicts/lists."""
    text = text.strip()
    if text.startswith("return"):
        text = text[len("return"):].strip()
    tokens = _tokenize(text)
    return _Parser(tokens).parse_table()


# ── Fetch, cache, and expose the parsed blueprint table ─────────────────

def _cache_is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < _TTL


def load_blueprints(force_refresh: bool = False) -> dict[str, dict]:
    """Return ``{item_name: {Credits, Parts, Result, ...}}``, cached 24h.

    Returns an empty dict (never raises) on any fetch or parse failure — a
    missing/broken resource-cost source degrades to "no data", the same as
    any other optional annotation in this tool, not a crash.
    """
    if not force_refresh and _cache_is_fresh(_PARSED_CACHE_FILE):
        try:
            return json.loads(_PARSED_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    try:
        if not force_refresh and _cache_is_fresh(_RAW_CACHE_FILE):
            raw = _RAW_CACHE_FILE.read_text(encoding="utf-8")
        else:
            resp = requests.get(BLUEPRINTS_URL, timeout=30)
            resp.raise_for_status()
            raw = resp.text
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _RAW_CACHE_FILE.write_text(raw, encoding="utf-8")

        parsed = _parse_lua_table(raw)
        if not isinstance(parsed, dict):
            return {}
        # The module has multiple top-level categories keyed by product type
        # (at least "Blueprints" for weapons and "Suits" for Warframes/
        # Necramechs/etc, possibly more as the wiki evolves) -- merge them
        # into one flat lookup rather than hardcoding which categories exist.
        blueprints: dict[str, dict] = {}
        for category in parsed.values():
            if isinstance(category, dict):
                blueprints.update(category)
        if not blueprints:
            return {}
        _PARSED_CACHE_FILE.write_text(json.dumps(blueprints), encoding="utf-8")
        return blueprints
    except Exception:
        return {}


def expand_resource_cost(
    name: str, blueprints: dict[str, dict], _seen: frozenset[str] = frozenset()
) -> dict[str, int]:
    """Flatten one blueprint's full resource cost, recursing into any nested
    sub-component build (``Type in {"Item", "PrimePart"}``) so the result is
    the total raw materials needed from zero, not just the final-assembly step.

    Weapons and Warframes structure sub-parts differently in this data:
    a weapon's Barrel/Receiver/Stock usually carries its own embedded
    ``Cost`` block (self-contained recipe); a Warframe's Chassis/Neuroptics/
    Systems does not — instead each is its *own* top-level entry named
    ``"<Frame> <Part>"`` (e.g. "Dante" + "Chassis" -> "Dante Chassis"), so a
    part with no embedded Cost is looked up as a sibling by that convention.

    Returns ``{}`` for a name absent from ``blueprints`` (no known cost) —
    silence, not a guess. ``_seen`` guards against a malformed cyclic
    reference in the source data; normal data never triggers it.
    """
    entry = blueprints.get(name)
    if not entry or name in _seen:
        return {}
    return _expand_parts(entry.get("Parts") or [], blueprints, _seen | {name}, name)


def _join_sibling_name(parent_name: str, pname: str) -> str:
    """Build the sibling top-level key for an un-embedded sub-part.

    Usually a plain join ("Dante" + "Chassis" -> "Dante Chassis"), but Prime
    frames name their parts with a *leading* "Prime " ("Ash Prime" + "Prime
    Chassis" would naively double up to "Ash Prime Prime Chassis" instead of
    the real key "Ash Prime Chassis") -- drop the word repeated across the
    parent/part boundary before joining.
    """
    p_words, c_words = parent_name.split(), pname.split()
    if p_words and c_words and p_words[-1].casefold() == c_words[0].casefold():
        return " ".join(p_words + c_words[1:])
    return f"{parent_name} {pname}"


def _expand_parts(
    parts: list, blueprints: dict[str, dict], seen: frozenset[str], parent_name: str
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        count = part.get("Count") or 0
        pname = part.get("Name", "")
        if part.get("Type") in _NESTED_PART_TYPES:
            cost = part.get("Cost")
            if cost:
                sub_totals = _expand_parts(cost.get("Parts") or [], blueprints, seen, pname)
            else:
                sibling = _join_sibling_name(parent_name, pname)
                sub_totals = expand_resource_cost(sibling, blueprints, seen)
                if not sub_totals:
                    sub_totals = expand_resource_cost(pname, blueprints, seen)
            for sub_name, sub_count in sub_totals.items():
                totals[sub_name] = totals.get(sub_name, 0) + sub_count * count
        elif pname:
            totals[pname] = totals.get(pname, 0) + count
    return totals


def find_blueprint_key(display_name: str, blueprints: dict[str, dict]) -> str | None:
    """Match a catalog display name to this module's (differently-cased,
    sometimes differently-spaced) key, via normalized exact match."""
    if display_name in blueprints:
        return display_name
    target = normalize(display_name)
    for key in blueprints:
        if normalize(key) == target:
            return key
    return None
