"""parse_nodes()/_collect_items() flatten the WFCD missionRewards.json shape
(planet -> node -> rotation -> rewards) into Node objects — the foundation
every other module builds on, so its two reward shapes (flat list vs.
rotation dict) and malformed-data tolerance are worth testing directly."""

from warframe_routes import data


def test_parse_nodes_flat_reward_list():
    raw = {
        "missionRewards": {
            "Venus": {
                "Fossa": {
                    "gameMode": "Assassination",
                    "rewards": [
                        {"itemName": "Rhino Chassis Blueprint"},
                        {"itemName": "Rhino Neuroptics Blueprint"},
                    ],
                }
            }
        }
    }
    nodes = data.parse_nodes(raw)
    assert len(nodes) == 1
    node = nodes[0]
    assert node.planet == "Venus"
    assert node.name == "Fossa"
    assert node.game_mode == "Assassination"
    assert node.items == frozenset({"Rhino Chassis Blueprint", "Rhino Neuroptics Blueprint"})
    assert node.key == "Venus - Fossa"


def test_parse_nodes_rotation_dict_rewards():
    raw = {
        "missionRewards": {
            "Uranus": {
                "Ur": {
                    "gameMode": "Disruption",
                    "rewards": {
                        "A": [{"itemName": "Neo A1 Relic"}],
                        "B": [{"itemName": "Neo B2 Relic"}, {"itemName": "Neo B3 Relic"}],
                    },
                }
            }
        }
    }
    nodes = data.parse_nodes(raw)
    assert len(nodes) == 1
    assert nodes[0].items == frozenset({"Neo A1 Relic", "Neo B2 Relic", "Neo B3 Relic"})


def test_parse_nodes_missing_game_mode_defaults_to_unknown():
    raw = {"missionRewards": {"Mars": {"Olympus": {
        "rewards": [{"itemName": "Something"}],
    }}}}
    nodes = data.parse_nodes(raw)
    assert nodes[0].game_mode == "Unknown"


def test_parse_nodes_skips_nodes_with_no_items():
    raw = {"missionRewards": {"Mars": {
        "Empty": {"gameMode": "Capture", "rewards": []},
        "AlsoEmpty": {"gameMode": "Capture", "rewards": {}},
    }}}
    assert data.parse_nodes(raw) == []


def test_parse_nodes_tolerates_malformed_entries():
    raw = {
        "missionRewards": {
            "Mars": "not a dict",  # whole planet is malformed -> skipped
            "Venus": {
                "Fossa": "also not a dict",  # malformed node -> skipped
                "Real": {
                    "gameMode": "Exterminate",
                    "rewards": [
                        {"itemName": "Good Item"},
                        {"no": "itemName key"},
                        "not a dict reward",
                        None,
                    ],
                },
            },
        }
    }
    nodes = data.parse_nodes(raw)
    assert len(nodes) == 1
    assert nodes[0].items == frozenset({"Good Item"})


def test_parse_nodes_accepts_root_without_missionrewards_key():
    # Some callers may pass the rewards mapping directly rather than wrapped
    # in {"missionRewards": ...} -- parse_nodes falls back to the raw dict.
    raw = {"Venus": {"Fossa": {"gameMode": "Assassination",
                                "rewards": [{"itemName": "X"}]}}}
    nodes = data.parse_nodes(raw)
    assert len(nodes) == 1
    assert nodes[0].key == "Venus - Fossa"


def test_collect_items_strips_whitespace_and_skips_falsy_names():
    items = data._collect_items([
        {"itemName": "  Padded Name  "},
        {"itemName": ""},
        {"itemName": None},
    ])
    assert items == {"Padded Name"}


def test_collect_items_returns_empty_for_unrecognized_shape():
    assert data._collect_items("not a list or dict") == set()
    assert data._collect_items(None) == set()
