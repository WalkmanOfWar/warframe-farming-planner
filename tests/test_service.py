"""Tests for the plan-assembly service (the layer CLI and web both call).

These exercise `plan_route` end to end over a small synthetic items dataset,
covering every output bucket — Prime relics + tiers, non-Prime mission routing,
Market-only blueprints (`no_part_source`), non-standard sources grouped by
location (`special_source`), and the equipment/part icon map — plus the loose
`owned_parts` subtraction. No network: fixtures are plain dicts.
"""

from warframe_routes import service

CDN = "https://cdn.warframestat.us/img/"

# A dataset that hits every code path in plan_route:
#  - Volt Prime: two relic-sourced parts (Prime tier-farming side)
#  - Rhino:      one boss-node part (non-Prime set-cover) + a Market-only main BP
#  - Baruuk:     a part from a non-standard source (Sanctuary Onslaught)
#  - Sigma:      equipment with only resource components -> no farmable part
ITEMS = [
    {
        "name": "Volt Prime",
        "masterable": True,
        "imageName": "voltprime.png",
        "components": [
            {"name": "Blueprint",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeBlueprint",
             "imageName": "schematic.png",
             "drops": [{"type": "Volt Prime Blueprint", "location": "Axi N3 Relic"}]},
            {"name": "Chassis",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
             "imageName": "voltprimechassis.png",
             "drops": [{"type": "Volt Prime Chassis", "location": "Neo V1 Relic"}]},
        ],
    },
    {
        "name": "Rhino",
        "masterable": True,
        "imageName": "rhino.png",
        "components": [
            {"name": "Chassis",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/RhinoChassis",
             "imageName": "rhinochassis.png",
             "drops": [{"type": "Rhino Chassis Blueprint",
                        "location": "Venus/Fossa (Assassination)"}]},
            {"name": "Blueprint",  # Market-only: no drops anywhere
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/RhinoBlueprint",
             "imageName": "schematic.png",
             "drops": []},
        ],
    },
    {
        "name": "Baruuk",
        "masterable": True,
        "imageName": "baruuk.png",
        "components": [
            {"name": "Neuroptics",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/BaruukNeuro",
             "drops": [{"type": "Baruuk Neuroptics Blueprint",
                        "location": "Elite Sanctuary Onslaught, Rotation C"}]},
        ],
    },
    {
        "name": "Sigma",
        "masterable": True,
        "imageName": "sigma.png",
        "components": [
            {"name": "Salvage",  # resource, not /Recipes/ -> no farmable part
             "uniqueName": "/Lotus/Types/Items/MiscItems/Salvage",
             "drops": [{"type": "10X Salvage", "location": "Venus/Fossa (Assassination)"}]},
        ],
    },
]

# Both Volt Prime relics are in rotation so the Prime parts are farmable.
MISSION_REWARDS = {
    "missionRewards": {
        "Earth": {"Mantle": {"gameMode": "Excavation",
                             "rewards": {"A": [{"itemName": "Axi N3 Relic"}]}}},
        "Mercury": {"Apollodorus": {"gameMode": "Survival",
                                    "rewards": [{"itemName": "Neo V1 Relic"}]}},
    }
}

WANT = {"volt prime", "rhino", "baruuk", "sigma"}


def _plan(owned=None, want=WANT, owned_parts=None):
    return service.plan_route(
        owned=owned or set(),
        want=want,
        owned_parts=owned_parts or set(),
        items_data=ITEMS,
        mission_rewards=MISSION_REWARDS,
    )


def test_no_needed_equipment_returns_empty_result():
    res = service.plan_route(owned={"rhino"}, want={"rhino"}, owned_parts=set(),
                             items_data=ITEMS, mission_rewards=MISSION_REWARDS)
    assert res.missing_equipment == 0
    assert res.non_prime == [] and res.prime == [] and res.special_source == {}


def test_missing_equipment_count():
    assert _plan().missing_equipment == 4


def test_prime_parts_and_tiers():
    res = _plan()
    parts = {p.part: p for p in res.prime}
    assert parts["Volt Prime Blueprint"].relics == ["Axi N3 Relic"]
    assert parts["Volt Prime Blueprint"].tiers == ["Axi"]
    assert parts["Volt Prime Chassis"].tiers == ["Neo"]
    # Tier guide is emitted for exactly the tiers needed, sorted.
    assert [t.tier for t in res.tiers] == ["Axi", "Neo"]
    assert all(t.where for t in res.tiers)


def test_nonprime_routed_to_boss_node():
    res = _plan()
    nodes = {m.node: m for m in res.non_prime}
    assert "Venus - Fossa" in nodes
    assert nodes["Venus - Fossa"].parts == ["Rhino Chassis Blueprint"]
    assert nodes["Venus - Fossa"].game_mode == "Assassination"


def test_market_only_blueprint_in_no_part_source():
    res = _plan()
    # Grouped by owning equipment: Rhino -> [Rhino Blueprint].
    assert res.no_part_source == {"Rhino": ["Rhino Blueprint"]}
    # ...and it must NOT leak into the mission route.
    routed = {p for m in res.non_prime for p in m.parts}
    assert "Rhino Blueprint" not in routed


def test_no_part_source_groups_multiple_parts_under_equipment():
    # A Market weapon whose every part is bought (no drops): all parts must
    # collapse under one equipment key, sorted — not a flat per-part list.
    weapon = [{
        "name": "Agkuza", "masterable": True,
        "components": [
            {"name": n, "uniqueName": f"/Lotus/Types/Recipes/Weapons/Agkuza{n}",
             "drops": []}
            for n in ("Blueprint", "Blade", "Guard", "Handle")
        ],
    }]
    res = service.plan_route(
        owned=set(), want={"agkuza"}, owned_parts=set(),
        items_data=weapon, mission_rewards={"missionRewards": {}})
    assert res.no_part_source == {
        "Agkuza": ["Agkuza Blade", "Agkuza Blueprint",
                   "Agkuza Guard", "Agkuza Handle"],
    }


def test_special_source_grouped_by_location():
    res = _plan()
    assert res.special_source == {
        "Elite Sanctuary Onslaught, Rotation C": ["Baruuk Neuroptics Blueprint"],
    }


def test_equipment_with_no_farmable_part_in_no_mission_source():
    res = _plan()
    assert "Sigma" in res.no_mission_source


def test_owned_parts_subtracted_across_buckets():
    res = _plan(owned_parts={
        "volt prime blueprint",          # remove a Prime part
        "rhino chassis blueprint",       # remove the only non-Prime part
        "baruuk neuroptics blueprint",   # remove the special-source part
        "rhino blueprint",               # remove the Market BP
    })
    assert all(p.part != "Volt Prime Blueprint" for p in res.prime)
    assert res.non_prime == []                       # only part was owned
    assert res.special_source == {}
    assert res.no_part_source == {}                  # Rhino BP was owned


def test_image_map_blueprint_prefers_portrait_over_schematic():
    # "Volt Prime Blueprint" component imageName is the generic schematic; the
    # map must resolve to the warframe portrait via the progressive-prefix rule.
    res = _plan()
    assert res.images["Volt Prime Blueprint"] == CDN + "voltprime.png"


def test_image_map_component_direct_hit():
    res = _plan()
    # "Volt Prime Chassis" matches the chassis component's own imageName.
    assert res.images["Volt Prime Chassis"] == CDN + "voltprimechassis.png"


def test_image_map_equipment_fallback_for_special_source_part():
    # Baruuk Neuroptics has no imageName of its own and "baruuk neuroptics" isn't
    # a registered component image -> falls back to the Baruuk equipment portrait.
    res = _plan()
    assert res.images["Baruuk Neuroptics Blueprint"] == CDN + "baruuk.png"


def test_image_map_covers_no_mission_source_equipment():
    res = _plan()
    assert res.images["Sigma"] == CDN + "sigma.png"


def test_to_dict_is_json_shaped():
    d = _plan().to_dict()
    assert isinstance(d, dict)
    assert isinstance(d["special_source"], dict)
    assert isinstance(d["prime"], list) and isinstance(d["prime"][0], dict)
