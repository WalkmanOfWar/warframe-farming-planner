"""Fewest-mission route optimization (a set-cover problem).

Goal: pick the smallest set of mission nodes whose combined drops cover every
needed item. Minimum set cover is NP-hard, so we use the classic greedy
heuristic: repeatedly take the node that covers the most still-uncovered items.
The greedy algorithm is within a ln(n)+1 factor of optimal, which is more than
good enough for choosing farming routes.

Item names from the drop tables are matched against needed items using the same
case-folded normalization as :mod:`warframe_routes.inventory`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import Node


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


def _normalize(name: str) -> str:
    return name.strip().casefold()


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
