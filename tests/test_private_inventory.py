import pytest
import responses

from warframe_routes import private_inventory as pi

ITEMS = [
    {
        "name": "Volt Prime",
        "masterable": True,
        "components": [
            {"name": "Chassis",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
             "drops": [{"type": "Volt Prime Chassis", "location": "Axi V8 Relic"}]},
            {"name": "Orokin Cell",
             "uniqueName": "/Lotus/Types/Items/MiscItems/OrokinCell", "drops": []},
        ],
    }
]

INVENTORY = {
    "Suits": [{"ItemType": "/Lotus/Powersuits/Excalibur/Excalibur", "ItemCount": 1}],
    "MiscItems": [
        {"ItemType": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
         "ItemCount": 1},                                   # loose part -> owned
        {"ItemType": "/Lotus/Types/Items/MiscItems/OrokinCell",
         "ItemCount": 50},                                  # resource -> ignored
        {"ItemType": "/Lotus/Types/Items/MiscItems/Ferrite",
         "ItemCount": 0},                                   # zero count -> skipped
    ],
}


def test_collect_item_types_skips_zero_count():
    types = pi.collect_item_types(INVENTORY)
    assert "/Lotus/Powersuits/Excalibur/Excalibur" in types
    assert "/Lotus/Types/Items/MiscItems/Ferrite" not in types


def test_component_index_uses_drop_type_as_display():
    idx = pi.build_component_index(ITEMS)
    assert idx["/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis"] == \
        "Volt Prime Chassis"
    # resource component (no /Recipes/) is not indexed
    assert "/Lotus/Types/Items/MiscItems/OrokinCell" not in idx


def test_owned_parts_matches_acquisition_part_name():
    # The loose part name must equal the chain's part display ("Volt Prime Chassis").
    assert pi.owned_parts(INVENTORY, ITEMS) == {"Volt Prime Chassis"}


def test_fetch_inventory_rejects_bad_account_id():
    with pytest.raises(ValueError):
        pi.fetch_inventory("nope", "abc")


@responses.activate
def test_fetch_inventory_expired_nonce_raises():
    responses.add(responses.GET, pi.INVENTORY_URL, status=401)
    with pytest.raises(ValueError, match="expired"):
        pi.fetch_inventory("a" * 24, "stalenonce")


@responses.activate
def test_fetch_inventory_returns_json():
    responses.add(responses.GET, pi.INVENTORY_URL,
                  json={"MiscItems": [{"ItemType": "X", "ItemCount": 1}]})
    assert pi.fetch_inventory("a" * 24, "n") == {
        "MiscItems": [{"ItemType": "X", "ItemCount": 1}]}


RELIC_ITEMS = [
    {"name": "Axi A1 Intact",
     "uniqueName": "/Lotus/Types/Game/Projections/T4VoidProjectionEBronze"},
    {"name": "Axi A1 Radiant",
     "uniqueName": "/Lotus/Types/Game/Projections/T4VoidProjectionEPlatinum"},
    {"name": "Lith W3 Intact",
     "uniqueName": "/Lotus/Types/Game/Projections/T1VoidProjectionWBronze"},
]


def test_owned_relics_sums_refinements_under_base_name():
    inv = {"MiscItems": [
        {"ItemType": "/Lotus/Types/Game/Projections/T4VoidProjectionEBronze",
         "ItemCount": 3},
        {"ItemType": "/Lotus/Types/Game/Projections/T4VoidProjectionEPlatinum",
         "ItemCount": 2},
    ]}
    assert pi.owned_relics(inv, RELIC_ITEMS) == {"axi a1 relic": 5}


def test_owned_relics_ignores_zero_counts_and_unknown_types():
    inv = {"MiscItems": [
        {"ItemType": "/Lotus/Types/Game/Projections/T1VoidProjectionWBronze",
         "ItemCount": 0},
        {"ItemType": "/Lotus/Types/Items/MiscItems/OrokinCell", "ItemCount": 9},
    ]}
    assert pi.owned_relics(inv, RELIC_ITEMS) == {}


RESOURCE_ITEMS = [
    {
        "name": "Rhino",
        "components": [
            {"name": "Blueprint",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/RhinoBlueprint"},
            {"name": "Neurodes",
             "uniqueName": "/Lotus/Types/Items/MiscItems/Neurode"},
        ],
    },
]


def test_owned_resources_counts_by_display_name():
    inv = {"MiscItems": [
        {"ItemType": "/Lotus/Types/Items/MiscItems/Neurode", "ItemCount": 7},
    ]}
    assert pi.owned_resources(inv, RESOURCE_ITEMS) == {"Neurodes": 7}


def test_owned_resources_excludes_farmable_parts():
    # A /Recipes/ part must never show up as a "resource" -- it's what
    # items.is_part_component already treats as a farmable part.
    inv = {"MiscItems": [
        {"ItemType": "/Lotus/Types/Recipes/WarframeRecipes/RhinoBlueprint", "ItemCount": 1},
    ]}
    assert pi.owned_resources(inv, RESOURCE_ITEMS) == {}


def test_owned_resources_ignores_zero_counts():
    inv = {"MiscItems": [
        {"ItemType": "/Lotus/Types/Items/MiscItems/Neurode", "ItemCount": 0},
    ]}
    assert pi.owned_resources(inv, RESOURCE_ITEMS) == {}
