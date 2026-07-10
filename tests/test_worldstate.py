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
