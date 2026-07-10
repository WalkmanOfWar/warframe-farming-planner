"""Expected-effort model: turn drop chances into expected runs and time.

The rest of the pipeline answers *which* missions cover the missing items; this
module answers *how much it costs*. Two farming models, two formulas:

**Non-Prime** parts drop straight from a node. A node hands out exactly one
reward per rotation roll, so the listed chances within a rotation are mutually
exclusive. Expected rolls to obtain a single part with probability ``p`` is
``1/p``. To collect *several* needed parts from the same node we use the exact
coupon-collector expectation for a weighted draw (inclusion-exclusion over the
non-empty subsets)::

    E[rolls] = Σ_{∅≠S⊆parts} (-1)^{|S|+1} / (Σ_{i∈S} p_i)

This is exact for the "one mutually-exclusive drop per roll" model and cheap
for the small part counts per mission (2^k terms, k ≤ ~4).

**Prime** parts are two-step: farm the *relic* (drops from some node with
chance ``r``), then crack it at a fissure where the part appears with chance
``d`` (``d`` depends on refinement: Intact < Exceptional < Flawless < Radiant).
Cracking is modelled solo (one relic per fissure run). Expected cracks to hit
the part is ``1/d``; each crack consumes a relic costing ``1/r`` farm runs, plus
the fissure run itself::

    relic_farm_runs = (1/d) * (1/r)
    crack_runs      = 1/d
    total_runs      = relic_farm_runs + crack_runs

All chances are accepted as **percentages** (as they appear in the WFCD data,
e.g. ``11`` or ``38.72``); ``0``/missing yields ``inf`` (unobtainable).

Time is ``runs * minutes_per_run``; the per-mode estimates below are rough
community averages, deliberately conservative, and the one part of this module
that is judgement rather than arithmetic. Tune :data:`MODE_MINUTES` freely.
"""

from __future__ import annotations

from itertools import combinations

# Rough minutes for one reward roll of a mission, by game mode (incl. loading).
# Endless modes are "per rotation roll", not per full run. Estimates, not gospel.
MODE_MINUTES: dict[str, float] = {
    "Capture": 1.5,
    "Exterminate": 3.0,
    "Assassination": 3.0,
    "Sabotage": 4.0,
    "Rescue": 3.5,
    "Spy": 5.0,
    "Mobile Defense": 4.0,
    "Defense": 5.0,        # ~5 waves per rotation
    "Survival": 5.0,       # ~5 minutes per rotation
    "Interception": 5.0,
    "Excavation": 4.0,
    "Disruption": 4.0,
    "Defection": 5.0,
    "Hijack": 4.0,
    "Skirmish": 6.0,
    "Assault": 5.0,
}
DEFAULT_MODE_MINUTES = 4.0
# A void-fissure crack run (typically a Capture fissure), incl. loading.
FISSURE_MINUTES = 2.5

# Most endless modes (Defense, Survival, Excavation, Interception, Mobile
# Defense, ...) hand out rewards on an A,A,B,C cadence, so a deeper rotation
# costs more real time per reward: A lands first, B on the 3rd drop, C on the
# 4th. Multiplier on the per-rotation mode time; a non-rotational drop is 1x.
ROTATION_FACTOR = {None: 1.0, "A": 1.0, "B": 3.0, "C": 4.0}

# Disruption is a documented exception: it does NOT follow AABC. Reward tier
# depends on round number *and* conduits successfully defended per round
# (wiki.warframe.com/w/Disruption); a squad defending all 4 conduits every
# round reaches Rotation B after round 1 and Rotation C after round 3 (not
# after "3x"/"4x" a single roll like the generic table above would imply).
# Using the generic factor here would overestimate Neo/Axi Disruption farm
# time by ~30-50%, and Disruption is the tool's own recommended route for
# those tiers (see service.RELIC_TIER_GUIDE).
DISRUPTION_ROTATION_FACTOR = {None: 1.0, "A": 1.0, "B": 1.0, "C": 3.0}


def rotation_factor(rotation: str | None, mode: str | None = None) -> float:
    table = DISRUPTION_ROTATION_FACTOR if mode == "Disruption" else ROTATION_FACTOR
    return table.get(rotation, 1.0)

# Order matters: better refinement = higher part chance but costs void traces.
REFINEMENTS = ("Intact", "Exceptional", "Flawless", "Radiant")

# Above this many parts at one node, exact inclusion-exclusion (2^k terms) is
# too expensive, so mission_runs falls back to an O(k) independent-rolls estimate.
_EXACT_MAX_PARTS = 12


def mode_minutes(game_mode: str) -> float:
    return MODE_MINUTES.get(game_mode, DEFAULT_MODE_MINUTES)


def _p(chance_pct: float) -> float:
    """Percentage -> probability in (0, 1]; non-positive -> 0 (=> inf runs)."""
    return (chance_pct or 0.0) / 100.0


def part_runs(chance_pct: float) -> float:
    """Expected rolls to obtain a single part with the given drop chance (%)."""
    p = _p(chance_pct)
    return float("inf") if p <= 0 else 1.0 / p


def mission_runs(chances_pct: list[float]) -> float:
    """Expected rolls to collect *every* listed part from one node.

    For a realistic number of parts (≤ ``_EXACT_MAX_PARTS``) this is the exact
    weighted coupon-collector for the "one mutually-exclusive drop per roll"
    model, via inclusion-exclusion. For very fat drop tables it falls back to an
    O(k) independent-rolls estimate (a slight over-estimate, since it ignores
    that every roll is productive) — 2^k inclusion-exclusion is intractable when
    a single node lists dozens of needed parts. Any part with a non-positive
    chance makes the whole collection unobtainable (``inf``).
    """
    ps = [_p(c) for c in chances_pct]
    if not ps:
        return 0.0
    if any(p <= 0 for p in ps):
        return float("inf")
    if len(ps) > _EXACT_MAX_PARTS:
        return _mission_runs_independent(ps)
    total = 0.0
    n = len(ps)
    for k in range(1, n + 1):
        for combo in combinations(ps, k):
            sign = 1 if k % 2 == 1 else -1
            total += sign / sum(combo)
    return total


def _mission_runs_independent(ps: list[float]) -> float:
    """E[rolls] to collect all parts, treating each as an independent geometric.

    E[max T_i] = Σ_{t≥0} (1 - ∏_i (1 - (1-p_i)^t)). Summed until the per-step
    contribution is negligible; the tail decays at rate (1 - min p_i), so this is
    O(k / min p). Equals 1/p for a single part, like the exact model.
    """
    q = [1.0 - p for p in ps]
    total, t = 0.0, 0
    while True:
        prob_all = 1.0
        for qi in q:
            prob_all *= (1.0 - qi ** t)
        term = 1.0 - prob_all
        total += term
        if t > 0 and term < 1e-9:
            return total
        t += 1


def effective_squad_chance_pct(chance_pct: float, squad_size: int = 4) -> float:
    """Effective per-run drop probability when ``squad_size`` players each crack
    the same relic type and share results (pick any of the squad's drops).

    Probability of at least one hit in ``squad_size`` independent cracks:
    ``1 - (1 - p)^squad_size``, returned as a percentage.
    """
    p = _p(chance_pct)
    if p <= 0:
        return 0.0
    return (1.0 - (1.0 - p) ** squad_size) * 100.0


def prime_part_runs(in_relic_chance_pct: float, relic_node_chance_pct: float) -> dict:
    """Expected effort for one Prime part: relic farming + cracking (solo).

    Returns a dict with ``relic_farm_runs``, ``crack_runs`` and ``total_runs``.
    ``crack_runs`` is also the expected number of relics consumed.
    """
    d = _p(in_relic_chance_pct)
    r = _p(relic_node_chance_pct)
    if d <= 0 or r <= 0:
        inf = float("inf")
        return {"relic_farm_runs": inf, "crack_runs": inf, "total_runs": inf}
    crack_runs = 1.0 / d
    relic_farm_runs = crack_runs * (1.0 / r)
    return {
        "relic_farm_runs": relic_farm_runs,
        "crack_runs": crack_runs,
        "total_runs": relic_farm_runs + crack_runs,
    }
