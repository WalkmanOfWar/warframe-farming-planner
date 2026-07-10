from warframe_routes.items import is_part_component, part_display_name


def test_is_part_component_accepts_recipes_path():
    assert is_part_component("/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis")


def test_is_part_component_accepts_necramech_vault_parts():
    assert is_part_component(
        "/Lotus/Types/Gameplay/InfestedMicroplanet/Resources/Mechs/NecromechPartChassisItem")


def test_is_part_component_rejects_generic_resources():
    assert not is_part_component("/Lotus/Types/Items/MiscItems/OrokinCell")
    assert not is_part_component("")
    assert not is_part_component(None)


def test_part_display_name_prefixes_equipment_name():
    assert part_display_name("Volt Prime", "Chassis") == "Volt Prime Chassis"


def test_part_display_name_skips_duplicate_prefix():
    # Necramech vault-part components already embed the equipment name.
    assert part_display_name("Voidrig", "Voidrig Capsule") == "Voidrig Capsule"


def test_part_display_name_prefix_check_is_case_insensitive():
    assert part_display_name("voidrig", "Voidrig Capsule") == "Voidrig Capsule"
