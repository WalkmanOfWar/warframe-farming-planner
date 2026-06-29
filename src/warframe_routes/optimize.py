"""Fewest-mission route optimization (a set-cover problem).

Goal: pick the smallest set of mission nodes whose combined drops cover every
needed item. Minimum set cover is NP-hard, so we use the classic greedy
heuristic: repeatedly take the node that covers the most still-uncovered items.
The greedy algorithm is within a ln(n)+1 factor of optimal, which is more than
good enough for choosing farming routes.

Item names from the drop tables are matched against needed items using the
shared case-folded normalization from :mod:`warframe_routes.items`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import Node
# Single source of truth for name matching, shared across the package.
from .items import normalize as _normalize


@dataclass
class RouteStep:
    node: Node
    covers: frozenset[str]  # normalized needed-item names this node provides


@dataclass
class Route:
    steps: list[RouteStep]
    uncovered: frozenset[str]  # needed items no node could provide

    @property
    def mission_count(self) -> int:
        return len(self.steps)


def _node_coverage(node: Node, needed: set[str]) -> frozenset[str]:
    """Which needed items (normalized) this node can drop."""
    return frozenset(_normalize(item) for item in node.items) & needed


def optimize_route(nodes: list[Node], needed: set[str]) -> Route:
    """Greedily select the fewest nodes that cover ``needed``.

    Ties (equal new coverage) are broken by preferring the node with the
    smaller total drop table, which tends to mean faster/more focused farms.
    """
    remaining = set(needed)
    steps: list[RouteStep] = []

    # Precompute coverage once; recompute deltas against `remaining` each round.
    candidates = [(node, _node_coverage(node, remaining)) for node in nodes]
    candidates = [(n, c) for n, c in candidates if c]

    while remaining and candidates:
        best_node = None
        best_new: frozenset[str] = frozenset()
        for node, _ in candidates:
            new = _node_coverage(node, remaining)
            if len(new) > len(best_new) or (
                len(new) == len(best_new)
                and best_node is not None
                and len(node.items) < len(best_node.items)
            ):
                best_node, best_new = node, new

        if not best_new:
            break

        steps.append(RouteStep(node=best_node, covers=best_new))
        remaining -= best_new
        candidates = [(n, c) for n, c in candidates if _node_coverage(n, remaining)]

    return Route(steps=steps, uncovered=frozenset(remaining))


def optimize_by_cost(nodes: list[Node], needed: set[str], cost_fn) -> Route:
    """Assign every needed item to a node so total cost is (greedily) minimized.

    Stays objective-agnostic: the caller injects ``cost_fn(node, parts) -> float``
    giving the *total* expected cost of farming ``parts`` (a frozenset of
    normalized names) at ``node`` — e.g. expected minutes. We greedily assign one
    item at a time to whichever node yields the smallest **marginal** cost
    increase, which naturally reuses already-chosen nodes (the coupon-collector
    sharing makes adding to an existing stop cheap) and prefers higher-chance /
    faster nodes over merely-fewer ones.

    This is the standard greedy for uncapacitated facility-location-style
    problems; it isn't provably optimal (the exact problem is NP-hard) but is
    near-optimal in practice and far better than count-only set cover when an
    item drops at several nodes with different odds.
    """
    INF = float("inf")
    node_by_key: dict[str, Node] = {n.key: n for n in nodes}
    # A node only counts as a source for p if farming p there is actually
    # possible (finite cost) — a 0%-chance drop is unobtainable, not a free stop.
    coverers: dict[str, list[Node]] = {}
    for node in nodes:
        for p in _node_coverage(node, set(needed)):
            if cost_fn(node, frozenset({p})) != INF:
                coverers.setdefault(p, []).append(node)

    assignment: dict[str, set[str]] = {}
    cost_cache: dict[str, float] = {}        # node.key -> cost of its current set

    def add(node: Node, part: str) -> None:
        parts = assignment.setdefault(node.key, set())
        parts.add(part)
        cost_cache[node.key] = cost_fn(node, frozenset(parts))

    # Items with a single source have no choice — assign them directly. This also
    # removes the bulk of the work from the greedy loop below.
    uncovered: set[str] = set()
    multi: set[str] = set()
    for p in needed:
        nodes_p = coverers.get(p, ())
        if not nodes_p:
            uncovered.add(p)
        elif len(nodes_p) == 1:
            add(nodes_p[0], p)
        else:
            multi.add(p)

    # Greedily place the remaining multi-source items by least marginal cost.
    while multi:
        best = None  # (marginal, part, node)
        for p in multi:
            for node in coverers[p]:
                base = cost_cache.get(node.key, 0.0)
                cand = cost_fn(node, frozenset(assignment.get(node.key, set()) | {p}))
                marginal = cand - base
                if marginal < INF and (best is None or marginal < best[0]):
                    best = (marginal, p, node)
        if best is None:                      # only unobtainable assignments left
            uncovered |= multi
            break
        _, part, node = best
        add(node, part)
        multi.discard(part)

    steps = [
        RouteStep(node=node_by_key[k], covers=frozenset(parts))
        for k, parts in assignment.items() if parts
    ]
    return Route(steps=steps, uncovered=frozenset(uncovered))
