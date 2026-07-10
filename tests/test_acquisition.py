from warframe_routes.acquisition import build_plan

# One Prime with two relic-sourced parts and one resource component (no relics).
ITEMS = [
    {
        "name": "Volt Prime",
        "masterable": True,
        "vaulted": True,
        "components": [
            {
                "name": "Blueprint",
                "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeBlueprint",
                "drops": [
                    {"type": "Volt Prime Blueprint",
                     "location": "Axi N3 Relic (Radiant)"},
                    {"type": "Volt Prime Blueprint", "location": "Neo V1 Relic"},
                ],
            },
            {
                "name": "Chassis",
                "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
                "drops": [{"type": "Volt Prime Chassis",
                           "location": "Axi V8 Relic"}],
            },
            # resource -> /Items/ path, skipped even though it could have drops
            {"name": "Orokin Cell",
             "uniqueName": "/Lotus/Types/Items/MiscItems/OrokinCell", "drops": []},
        ],
    }
]

# Mantle drops Axi N3 (Blueprint); Apollodorus drops Neo V1 (Blueprint too).
# Axi V8 (Chassis) is dropped nowhere -> vaulted/not farmable.
MISSION_REWARDS = {
    "missionRewards": {
        "Earth": {"Mantle": {"gameMode": "Excavation",
                             "rewards": {"A": [{"itemName": "Axi N3 Relic"}]}}},
        "Mercury": {"Apollodorus": {"gameMode": "Survival",
                                    "rewards": [{"itemName": "Neo V1 Relic"}]}},
    }
}


def test_prime_part_lists_in_rotation_relics_with_display_name():
    plan = build_plan(ITEMS, MISSION_REWARDS, {"volt prime"})
    # "Axi N3 Relic (Radiant)" must match node reward "Axi N3 Relic", and the
    # part must point at the in-rotation relic display names (not nodes).
    assert plan.prime_part_relics["volt prime blueprint"] == {
        "Axi N3 Relic", "Neo V1 Relic"}


def test_part_with_no_in_rotation_relic_is_not_farmable():
    plan = build_plan(ITEMS, MISSION_REWARDS, {"volt prime"})
    assert "volt prime chassis" in plan.not_farmable          # Axi V8 drops nowhere
    assert "volt prime chassis" not in plan.prime_part_relics


def test_resource_component_is_ignored():
    plan = build_plan(ITEMS, MISSION_REWARDS, {"volt prime"})
    seen = set(plan.prime_part_relics) | plan.not_farmable | plan.direct_parts
    assert all("orokin cell" not in p for p in seen)


def test_primes_do_not_produce_mission_route_nodes():
    # Prime parts are tier-farmed, not node-routed: no direct nodes from relics.
    plan = build_plan(ITEMS, MISSION_REWARDS, {"volt prime"})
    assert plan.direct_nodes == [] and plan.direct_parts == set()


def test_fully_vaulted_equipment_reported():
    # Strip all node rewards -> nothing in rotation -> Volt Prime fully vaulted.
    empty = {"missionRewards": {"Earth": {"X": {"gameMode": "M", "rewards": {}}}}}
    plan = build_plan(ITEMS, empty, {"volt prime"})
    assert plan.vaulted_equipment() == {"Volt Prime"}
    assert plan.prime_part_relics == {}


# Non-Prime: parts drop straight from a boss node; resources are filtered out.
NONPRIME = [
    {
        "name": "Rhino",
        "masterable": True,
        "components": [
            {"name": "Chassis",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/RhinoChassis",
             "drops": [{"type": "Rhino Chassis Blueprint",
                        "location": "Venus/Fossa (Assassination)"}]},
            {"name": "Salvage",  # resource -> skipped
             "uniqueName": "/Lotus/Types/Items/MiscItems/Salvage",
             "drops": [{"type": "10X Salvage",
                        "location": "Venus/Fossa (Assassination)"}]},
            {"name": "Blueprint",  # market BP, no drops -> not farmed
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/RhinoBlueprint",
             "drops": []},
        ],
    }
]


def test_nonprime_part_routed_from_boss_node():
    plan = build_plan(NONPRIME, {"missionRewards": {}}, {"rhino"})
    assert "rhino chassis blueprint" in plan.direct_parts
    node = next(n for n in plan.direct_nodes if n.name == "Fossa")
    assert node.planet == "Venus" and node.game_mode == "Assassination"


def test_nonprime_resource_component_filtered_out():
    plan = build_plan(NONPRIME, {"missionRewards": {}}, {"rhino"})
    assert not any("salvage" in p for p in plan.direct_parts)
    assert plan.prime_part_relics == {}


NECRAMECH = [
    {
        "name": "Voidrig",
        "masterable": True,
        "components": [
            {"name": "Blueprint",
             "uniqueName": "/Lotus/Types/Recipes/DeimosRecipes/Mechs/NecromechBlueprint",
             "drops": []},
            # No drop table lists Isolation Vault rewards, and the component's
            # own name already embeds the equipment name (a WFCD quirk) -- both
            # must be handled without the part silently vanishing or the
            # display name coming out "Voidrig Voidrig Capsule".
            {"name": "Voidrig Capsule",
             "uniqueName": "/Lotus/Types/Gameplay/InfestedMicroplanet/Resources/"
                            "Mechs/NecromechPartSystemsItem",
             "drops": []},
        ],
    }
]


def test_necramech_vault_part_is_not_silently_dropped():
    plan = build_plan(NECRAMECH, {"missionRewards": {}}, {"voidrig"})
    assert "voidrig capsule" in plan.orphan_parts
    assert plan.orphan_parts["voidrig capsule"] == "Voidrig Capsule"  # no duplicated prefix


def test_necramech_blueprint_also_registered_as_orphan_part():
    plan = build_plan(NECRAMECH, {"missionRewards": {}}, {"voidrig"})
    assert "voidrig blueprint" in plan.orphan_parts


PREREQ_ITEMS = [
    {
        "name": "Bolto",
        "masterable": True,
        "uniqueName": "/Lotus/Weapons/Tenno/Pistol/CrossBow",
        "components": [
            {"name": "Blueprint",
             "uniqueName": "/Lotus/Types/Recipes/Weapons/BoltoBlueprint",
             "drops": [{"type": "Bolto Blueprint", "location": "Venus/Fossa (Assassination)"}]},
        ],
    },
    {
        "name": "Akbolto",
        "masterable": True,
        "uniqueName": "/Lotus/Weapons/Tenno/Akimbo/AkimboBolto",
        "components": [
            {"name": "Blueprint",
             "uniqueName": "/Lotus/Types/Recipes/Weapons/AkboltoBlueprint",
             "drops": []},
            # Not a drop-table part at all -- a reference to the whole Bolto
            # weapon's own uniqueName: you must already own one.
            {"name": "Bolto", "uniqueName": "/Lotus/Weapons/Tenno/Pistol/CrossBow",
             "drops": []},
        ],
    },
]


def test_prerequisite_weapon_is_detected():
    plan = build_plan(PREREQ_ITEMS, {"missionRewards": {}}, {"akbolto"})
    assert plan.equipment_prerequisites == {"Akbolto": "Bolto"}


def test_prerequisite_component_does_not_pollute_orphan_parts():
    plan = build_plan(PREREQ_ITEMS, {"missionRewards": {}}, {"akbolto"})
    # The "Bolto" reference itself must never show up as a farmable part --
    # only the real Blueprint component should land in orphan_parts.
    assert list(plan.orphan_parts.values()) == ["Akbolto Blueprint"]


def test_no_prerequisite_when_not_needed():
    plan = build_plan(PREREQ_ITEMS, {"missionRewards": {}}, {"bolto"})
    assert plan.equipment_prerequisites == {}
