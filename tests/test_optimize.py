from warframe_routes.data import Node, parse_nodes
from warframe_routes.optimize import optimize_route


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
