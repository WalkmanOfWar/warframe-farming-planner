import pytest
import responses

from warframe_routes import sync


def test_invalid_account_id_is_rejected_before_network():
    with pytest.raises(sync.InvalidAccountId):
        sync.fetch_profile("not-an-id")
    with pytest.raises(sync.InvalidAccountId):
        sync.fetch_profile("MyUsername")


def test_owned_unique_names_reads_xpinfo():
    profile = {
        "Results": [
            {
                "DisplayName": "Tenno",
                "LoadOutInventory": {
                    "XPInfo": [
                        {"ItemType": "/Lotus/Powersuits/Volt/VoltPrime", "XP": 1},
                        {"ItemType": "/Lotus/Weapons/Soma", "XP": 2},
                        {"bad": "entry"},
                    ]
                },
            }
        ]
    }
    assert sync.owned_unique_names(profile) == {
        "/Lotus/Powersuits/Volt/VoltPrime",
        "/Lotus/Weapons/Soma",
    }


def test_owned_unique_names_empty_profile():
    assert sync.owned_unique_names({"Results": []}) == set()


def test_resolve_names_maps_unique_to_display():
    items_data = [
        {"uniqueName": "/Lotus/Powersuits/Volt/VoltPrime", "name": "Volt Prime",
         "masterable": True, "type": "Warframe"},
        {"uniqueName": "/Lotus/Weapons/Soma", "name": "Soma",
         "masterable": True, "type": "Rifle"},
    ]
    got = sync.resolve_names(
        {"/Lotus/Powersuits/Volt/VoltPrime", "/Lotus/Unknown/Thing"},
        items_data=items_data,
    )
    assert got == {"Volt Prime"}


def test_resolve_names_ignores_nodes_sharing_a_display_name():
    # A mastered star-chart node must not register as owning the same-named frame.
    items_data = [
        {"uniqueName": "SolNode60", "name": "Caliban",
         "masterable": False, "type": "Node"},
        {"uniqueName": "/Lotus/Powersuits/Sentient/Sentient", "name": "Caliban",
         "masterable": True, "type": "Warframe"},
    ]
    got = sync.resolve_names({"SolNode60"}, items_data=items_data)
    assert got == set()  # mastering the node does not mean owning the frame


@responses.activate
def test_fetch_profile_404_raises_invalid():
    responses.add(responses.GET, sync.PROFILE_URL, status=404)
    with pytest.raises(sync.InvalidAccountId):
        sync.fetch_profile("a" * 24)
