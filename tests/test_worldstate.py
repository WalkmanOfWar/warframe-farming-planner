from warframe_routes import worldstate as ws


def test_fissure_node_tiers_matches_plan_node_format():
    live = [
        {"tier": "Lith", "node": "Hepit (Void)", "mission": "Capture",
         "hard": False, "storm": False, "expiry": None},
        {"tier": "Neo", "node": "Ukko (Void)", "mission": "Capture",
         "hard": False, "storm": True, "expiry": None},  # storm — skipped
    ]
    idx = ws.fissure_node_tiers(live)
    assert idx == {"void|hepit": "Lith"}


def test_active_fissures_drops_expired_and_keeps_flags():
    raw = [
        {"tier": "Axi", "node": "Kappa (Sedna)", "missionType": "Disruption",
         "isHard": True, "isStorm": False, "expiry": "2099-01-01T00:00:00.000Z"},
        {"tier": "Axi", "node": "Old (Node)", "missionType": "Capture",
         "isHard": False, "isStorm": False, "expiry": "2000-01-01T00:00:00.000Z"},
    ]
    out = ws.active_fissures(raw)
    assert len(out) == 1 and out[0]["hard"] and out[0]["tier"] == "Axi"


def test_invasion_rewards_skips_completed():
    fake = [
        {"node": "A (P)", "completed": True,
         "attacker": {"faction": "Corpus",
                      "reward": {"items": ["Karak Wraith Stock"]}}},
        {"node": "B (Q)", "completed": False,
         "defender": {"faction": "Grineer",
                      "reward": {"countedItems": [{"type": "Fieldron"}]}}},
    ]
    out = ws.invasion_rewards(fake)
    assert "karak wraith stock" not in out
    assert any("B (Q)" in d for d in out["fieldron"])


def test_vault_trader_stock_flips_word_order_and_strips_weapon_suffix():
    trader = {
        "location": "Maroo's Bazaar (Mars)", "expiry": "2099-01-01T00:00:00.000Z",
        "inventory": [
            {"item": "Prime Corinth",
             "uniqueName": "/Lotus/StoreItems/Weapons/Tenno/LongGuns/PrimeCorinth/PrimeCorinth"},
            {"item": "Astilla Prime Weapon",
             "uniqueName": "/Lotus/StoreItems/Weapons/Tenno/LongGuns/PrimeAstilla/AstillaPrimeWeapon"},
            {"item": "Titania Prime",
             "uniqueName": "/Lotus/StoreItems/Powersuits/Fairy/TitaniaPrime"},
        ],
    }
    stock = ws.vault_trader_stock(trader)
    assert stock["items"]["corinth prime"] == "Corinth Prime"
    assert stock["items"]["astilla prime"] == "Astilla Prime"
    assert stock["items"]["titania prime"] == "Titania Prime"


def test_vault_trader_stock_excludes_cosmetics_and_bundles():
    trader = {
        "location": "Maroo's Bazaar (Mars)", "expiry": "2099-01-01T00:00:00.000Z",
        "inventory": [
            {"item": "M P V Titania Prime Single Pack",
             "uniqueName": "/Lotus/Types/StoreItems/Packages/MegaPrimeVault/MPVTitaniaPrimeSinglePack"},
            {"item": "Titania Prime Syandana",
             "uniqueName": "/Lotus/StoreItems/Upgrades/Skins/Scarves/TitaniaPrimeSyandana"},
            {"item": "Titania Prime Bobble Head",
             "uniqueName": "/Lotus/StoreItems/Types/Items/ShipDecos/TitaniaPrimeBobbleHead"},
        ],
    }
    assert ws.vault_trader_stock(trader) is None  # nothing left after filtering


def test_vault_trader_stock_none_when_not_trading():
    assert ws.vault_trader_stock({"location": "x", "inventory": []}) is None
    assert ws.vault_trader_stock({"location": "x", "inventory": [{"item": "Y"}],
                                  "expiry": "2000-01-01T00:00:00.000Z"}) is None


def test_daily_deal_returns_first_unexpired():
    deals = [{"item": "Detonite Injector", "discount": 20,
              "expiry": "2099-01-01T00:00:00.000Z"}]
    assert ws.daily_deal(deals) == {
        "item": "Detonite Injector", "discount": 20, "expiry": "2099-01-01T00:00:00.000Z"}
    assert ws.daily_deal([]) is None
    assert ws.daily_deal([{"item": "X", "expiry": "2000-01-01T00:00:00.000Z"}]) is None
