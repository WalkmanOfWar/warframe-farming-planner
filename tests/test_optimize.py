from warframe_routes.data import Node, parse_nodes
from warframe_routes.optimize import optimize_by_cost, optimize_route


def _node(name, items):
    return Node(planet="Earth", name=name, game_mode="Survival",
                items=frozenset(items))


def test_greedy_picks_fewest_nodes():
    nodes = [
        _node("A", {"x", "y"}),
        _node("B", {"y", "z"}),
        _node("C", {"x", "y", "z"}),  # single node covers everything
    ]
    route = optimize_route(nodes, {"x", "y", "z"})
    assert route.mission_count == 1
    assert route.steps[0].node.name == "C"
    assert not route.uncovered


def test_matching_is_case_insensitive():
    nodes = [_node("A", {"Volt Prime Barrel"})]
    route = optimize_route(nodes, {"volt prime barrel"})
    assert route.mission_count == 1


def test_reports_uncovered_items():
    nodes = [_node("A", {"x"})]
    route = optimize_route(nodes, {"x", "missing"})
    assert route.uncovered == frozenset({"missing"})


def test_optimize_by_cost_prefers_cheaper_node_over_fewer():
    # "y" drops at both A and B; B is cheaper. Count-only cover would take the
    # single node C; cost routing should instead use the cheap nodes.
    nodes = [_node("A", {"x"}), _node("B", {"x", "y"}), _node("Cheap", {"y"})]
    # cost: visiting "Cheap" for y is 1; via B it's 5.
    cost = {("A", "x"): 2.0, ("B", "x"): 2.0, ("B", "y"): 5.0, ("Cheap", "y"): 1.0}

    def cost_fn(node, parts):
        return sum(cost[(node.name, p)] for p in parts)

    route = optimize_by_cost(nodes, {"x", "y"}, cost_fn)
    assigned = {s.node.name: set(s.covers) for s in route.steps}
    assert assigned.get("Cheap") == {"y"}        # y routed to the cheap node
    assert "y" not in assigned.get("B", set())   # not bundled onto the pricier B
    assert not route.uncovered


def test_optimize_by_cost_reports_unobtainable_as_uncovered():
    nodes = [_node("A", {"x"})]

    def cost_fn(node, parts):
        return float("inf")                       # nothing is actually farmable

    route = optimize_by_cost(nodes, {"x", "missing"}, cost_fn)
    assert route.uncovered == frozenset({"x", "missing"})


def test_parse_nodes_handles_rotation_and_flat_rewards():
    raw = {
        "missionRewards": {
            "Earth": {
                "Cetus": {
                    "gameMode": "Bounty",
                    "rewards": {"A": [{"itemName": "Item One"}]},
                },
                "Mantle": {
                    "gameMode": "Excavation",
                    "rewards": [{"itemName": "Item Two"}],
                },
                "Empty": {"gameMode": "X", "rewards": {}},  # dropped
            }
        }
    }
    nodes = {n.name: n for n in parse_nodes(raw)}
    assert "Empty" not in nodes
    assert nodes["Cetus"].items == frozenset({"Item One"})
    assert nodes["Mantle"].items == frozenset({"Item Two"})
