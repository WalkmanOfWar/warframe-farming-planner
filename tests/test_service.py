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
             "drops": [{"type": "Volt Prime Blueprint", "chance": 25.33,
                        "location": "Axi N3 Relic"}]},
            {"name": "Chassis",
             "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
             "imageName": "voltprimechassis.png",
             "drops": [{"type": "Volt Prime Chassis", "chance": 11.0,
                        "location": "Neo V1 Relic"}]},
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
             "drops": [{"type": "Rhino Chassis Blueprint", "chance": 38.72,
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
                             "rewards": {"A": [{"itemName": "Axi N3 Relic",
                                                "chance": 10.0}]}}},
        "Mercury": {"Apollodorus": {"gameMode": "Survival",
                                    "rewards": [{"itemName": "Neo V1 Relic",
                                                 "chance": 10.0}]}},
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


def test_prime_relic_plan_and_tiers():
    res = _plan()
    assert res.prime_part_count == 2          # Volt Prime BP + Chassis
    by_relic = {pr.relic: pr for pr in res.prime}
    assert by_relic["Axi N3 Relic"].parts == ["Volt Prime Blueprint"]
    assert by_relic["Axi N3 Relic"].tier == "Axi"
    assert by_relic["Neo V1 Relic"].parts == ["Volt Prime Chassis"]
    assert all(pr.minutes and pr.cracks for pr in res.prime)
    # Tier guide is emitted for exactly the tiers needed, sorted.
    assert [t.tier for t in res.tiers] == ["Axi", "Neo"]
    assert all(t.where for t in res.tiers)


def test_prime_shared_relic_cracked_once_for_multiple_parts():
    # A frame whose two parts both drop from ONE relic must appear as a single
    # relic entry covering both — not two separate per-part entries.
    shared = [{
        "name": "Duo Prime", "masterable": True, "vaulted": True,
        "components": [
            {"name": "Blueprint", "uniqueName": "/x/Recipes/DuoBP",
             "drops": [{"type": "Duo Prime Blueprint", "chance": 20.0,
                        "location": "Axi D1 Relic"}]},
            {"name": "Chassis", "uniqueName": "/x/Recipes/DuoChassis",
             "drops": [{"type": "Duo Prime Chassis", "chance": 20.0,
                        "location": "Axi D1 Relic"}]},
        ],
    }]
    mr = {"missionRewards": {"Lua": {"Apollo": {
        "gameMode": "Disruption",
        "rewards": {"C": [{"itemName": "Axi D1 Relic", "chance": 10.0}]}}}}}
    res = service.plan_route(owned=set(), want={"duo prime"}, owned_parts=set(),
                             items_data=shared, mission_rewards=mr)
    assert len(res.prime) == 1                 # one relic, not two
    assert res.prime[0].relic == "Axi D1 Relic"
    assert res.prime[0].parts == ["Duo Prime Blueprint", "Duo Prime Chassis"]


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
    # Volt Prime Blueprint owned -> its relic no longer cracked for it.
    assert all("Volt Prime Blueprint" not in pr.parts for pr in res.prime)
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


def test_select_price_candidates_includes_vaulted_unconditionally():
    res = service.RouteResult(missing_equipment=1, vaulted_equipment=["Volt Prime", "Ash Prime"])
    assert service.select_price_candidates(res) == ["Volt Prime", "Ash Prime"]


def test_select_price_candidates_includes_high_time_parts_ranked_first():
    res = service.RouteResult(missing_equipment=1, non_prime=[
        service.Mission(node="A", game_mode="Capture", parts=["Cheap Part"], minutes=5.0),
        service.Mission(node="B", game_mode="Capture", parts=["Slow Part"], minutes=500.0),
    ], prime=[
        service.PrimeRelic(relic="Axi X1 Relic", tier="Axi", parts=["Slower Prime Part"], minutes=1000.0),
    ])
    out = service.select_price_candidates(res, min_minutes=120.0)
    assert "Cheap Part" not in out           # below the time threshold
    assert out == ["Slower Prime Part", "Slow Part"]   # ranked by parent time, desc


def test_select_price_candidates_respects_max_items_cap():
    res = service.RouteResult(missing_equipment=1,
                              vaulted_equipment=[f"Item {i}" for i in range(20)])
    assert len(service.select_price_candidates(res, max_items=5)) == 5


def test_select_price_candidates_dedupes_shared_parts():
    res = service.RouteResult(missing_equipment=1, prime=[
        service.PrimeRelic(relic="A", tier="Axi", parts=["Shared Part"], minutes=200.0),
        service.PrimeRelic(relic="B", tier="Axi", parts=["Shared Part"], minutes=300.0),
    ])
    assert service.select_price_candidates(res, min_minutes=120.0) == ["Shared Part"]


def test_necramech_vault_parts_get_relabeled_not_market_only():
    items_data = [{
        "name": "Voidrig",
        "masterable": True,
        "components": [
            {"name": "Blueprint",
             "uniqueName": "/Lotus/Types/Recipes/DeimosRecipes/Mechs/NecromechBlueprint",
             "drops": []},
            {"name": "Voidrig Capsule",
             "uniqueName": "/Lotus/Types/Gameplay/InfestedMicroplanet/Resources/"
                            "Mechs/NecromechPartSystemsItem",
             "drops": []},
        ],
    }]
    res = service.plan_route(owned=set(), want={"voidrig"}, owned_parts=set(),
                             items_data=items_data, mission_rewards={"missionRewards": {}})
    assert res.no_part_source == {}  # not left looking Market-only
    label = "Necramech gear — Isolation Vault (Cambion Drift, Deimos); check in-game"
    assert res.special_source[label] == ["Voidrig Blueprint", "Voidrig Capsule"]


def test_equipment_prerequisites_surfaced_in_result():
    items_data = [
        {"name": "Bolto", "masterable": True,
         "uniqueName": "/Lotus/Weapons/Tenno/Pistol/CrossBow",
         "components": [
             {"name": "Blueprint",
              "uniqueName": "/Lotus/Types/Recipes/Weapons/BoltoBlueprint",
              "drops": [{"type": "Bolto Blueprint", "location": "Venus/Fossa (Assassination)"}]},
         ]},
        {"name": "Akbolto", "masterable": True,
         "uniqueName": "/Lotus/Weapons/Tenno/Akimbo/AkimboBolto",
         "components": [
             {"name": "Blueprint",
              "uniqueName": "/Lotus/Types/Recipes/Weapons/AkboltoBlueprint", "drops": []},
             {"name": "Bolto", "uniqueName": "/Lotus/Weapons/Tenno/Pistol/CrossBow", "drops": []},
         ]},
    ]
    res = service.plan_route(owned=set(), want={"akbolto"}, owned_parts=set(),
                             items_data=items_data, mission_rewards={"missionRewards": {}})
    assert res.equipment_prerequisites == {"Akbolto": "Bolto"}
    assert res.no_part_source == {"Akbolto": ["Akbolto Blueprint"]}


def test_disruption_relic_uses_lower_rotation_factor_than_generic_mode():
    # Two identical relics, same chance, same rotation B, differing only by
    # game mode -- Disruption's farm-time estimate must come out lower than
    # a generic AABC-cadence mode (Survival), reflecting Disruption's actual
    # (documented) faster path to a given rotation tier.
    items_data = [{
        "name": "Volt Prime", "masterable": True,
        "components": [{
            "name": "Chassis",
            "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
            "drops": [{"type": "Volt Prime Chassis", "chance": 11.0,
                       "location": "Axi V8 Relic"}],
        }],
    }]
    mission_rewards_disruption = {"missionRewards": {"Uranus": {"Ur": {
        "gameMode": "Disruption",
        "rewards": {"B": [{"itemName": "Axi V8 Relic", "chance": 10.0}]},
    }}}}
    mission_rewards_survival = {"missionRewards": {"Uranus": {"Ur": {
        "gameMode": "Survival",
        "rewards": {"B": [{"itemName": "Axi V8 Relic", "chance": 10.0}]},
    }}}}
    res_disruption = service.plan_route(
        owned=set(), want={"volt prime"}, owned_parts=set(),
        items_data=items_data, mission_rewards=mission_rewards_disruption)
    res_survival = service.plan_route(
        owned=set(), want={"volt prime"}, owned_parts=set(),
        items_data=items_data, mission_rewards=mission_rewards_survival)
    assert res_disruption.prime[0].minutes < res_survival.prime[0].minutes


def test_buy_vs_farm_ranks_vaulted_first_then_worst_farm():
    res = service.RouteResult(
        missing_equipment=3,
        vaulted_equipment=["Vaulted Prime"],
        prime=[service.PrimeRelic(relic="Axi X1 Relic", tier="Axi",
                                  parts=["Slow Prime Part"], minutes=500.0)],
        non_prime=[service.Mission(node="A", game_mode="Capture",
                                   parts=["Fast Part"], minutes=10.0)],
    )
    prices = {
        "Vaulted Prime": {"plat": 80, "tradable": True, "url": "u1"},
        "Slow Prime Part": {"plat": 15, "tradable": True, "url": "u2"},
        "Fast Part": {"plat": 5, "tradable": True, "url": "u3"},
    }
    out = service.build_buy_vs_farm(res, prices)
    assert [b.item for b in out] == ["Vaulted Prime", "Slow Prime Part", "Fast Part"]
    assert out[0].minutes is None and out[0].source is None
    assert out[1].minutes == 500.0 and out[1].source == "Axi X1 Relic"


def test_buy_vs_farm_flags_shared_relic_parts():
    res = service.RouteResult(
        missing_equipment=1,
        prime=[service.PrimeRelic(relic="Axi X1 Relic", tier="Axi",
                                  parts=["Part A", "Part B"], minutes=300.0)],
    )
    prices = {"Part A": {"plat": 10, "tradable": True, "url": None}}
    out = service.build_buy_vs_farm(res, prices)
    assert out[0].shared_with == 1  # one other needed part shares this crack


def test_buy_vs_farm_skips_unpriced_and_unknown_names():
    res = service.RouteResult(missing_equipment=1)
    assert service.build_buy_vs_farm(res, {"Untracked Item": {"plat": 5, "tradable": True, "url": None}}) == []


def test_active_fissures_prefer_fast_crack_modes_over_alphabetical_node():
    # Cracking is a rush-in job: Capture (~1.5 min) beats Defense (~5 min)
    # regardless of node name -- a slow mode should never outrank a live fast
    # one just because its node name sorts earlier alphabetically.
    items_data = [{
        "name": "Volt Prime", "masterable": True,
        "components": [{
            "name": "Chassis",
            "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
            "drops": [{"type": "Volt Prime Chassis", "chance": 11.0,
                       "location": "Axi V8 Relic"}],
        }],
    }]
    mission_rewards = {"missionRewards": {"Lua": {"Apollo": {
        "gameMode": "Disruption",
        "rewards": {"A": [{"itemName": "Axi V8 Relic", "chance": 10.0}]},
    }}}}
    fissures = [
        {"tier": "Axi", "node": "Aaa Node (Earth)", "missionType": "Defense",
         "isHard": False, "isStorm": False, "expiry": None},
        {"tier": "Axi", "node": "Zzz Node (Mars)", "missionType": "Capture",
         "isHard": False, "isStorm": False, "expiry": None},
    ]
    res = service.plan_route(owned=set(), want={"volt prime"}, owned_parts=set(),
                             items_data=items_data, mission_rewards=mission_rewards,
                             fissures=fissures)
    live = res.active_fissures["Axi"]
    assert live[0]["mission"] == "Capture"
    assert live[0]["node"] == "Zzz Node (Mars)"


def test_fissure_covers_tier_matches_exact_or_omnia_except_requiem():
    assert service._fissure_covers_tier("Axi", "Axi") is True
    assert service._fissure_covers_tier("Lith", "Axi") is False
    assert service._fissure_covers_tier("Omnia", "Axi") is True
    assert service._fissure_covers_tier("Omnia", "Lith") is True
    assert service._fissure_covers_tier("Omnia", "Requiem") is False


def test_omnia_fissure_counts_as_live_and_farmable_for_needed_tier():
    # An Omnia fissure lets you crack any non-Requiem relic tier -- a live
    # Omnia fissure at the relic's farm node (or anywhere, for tier_live)
    # must count as actionable even though its own tier string is "Omnia",
    # not "Axi".
    items_data = [{
        "name": "Volt Prime", "masterable": True,
        "components": [{
            "name": "Chassis",
            "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeChassis",
            "drops": [{"type": "Volt Prime Chassis", "chance": 11.0,
                       "location": "Axi V8 Relic"}],
        }],
    }]
    mission_rewards = {"missionRewards": {"Lua": {"Apollo": {
        "gameMode": "Disruption",
        "rewards": {"A": [{"itemName": "Axi V8 Relic", "chance": 10.0}]},
    }}}}
    fissures = [
        {"tier": "Omnia", "node": "Apollo (Lua)", "missionType": "Disruption",
         "isHard": False, "isStorm": False, "expiry": None},
    ]
    res = service.plan_route(owned=set(), want={"volt prime"}, owned_parts=set(),
                             items_data=items_data, mission_rewards=mission_rewards,
                             fissures=fissures)
    assert res.prime[0].tier_live is True
    assert res.prime[0].farm_node_live is True
    assert "Axi" in res.active_fissures
    assert res.active_fissures["Axi"][0]["tier"] == "Omnia"


def test_build_resource_needs_sums_across_equipment_gross():
    blueprints = {
        "Rhino": {"Parts": [{"Count": 2, "Name": "Neurodes", "Type": "Resource"}]},
        "Volt Prime": {"Parts": [{"Count": 2, "Name": "Neurodes", "Type": "Resource"},
                                 {"Count": 1, "Name": "Orokin Cell", "Type": "Resource"}]},
    }
    out = service.build_resource_needs(["Rhino", "Volt Prime"], blueprints)
    by_res = {r.resource: r for r in out}
    assert by_res["Neurodes"].need == 4
    assert by_res["Neurodes"].owned is None and by_res["Neurodes"].short_by is None
    assert by_res["Orokin Cell"].need == 1


def test_build_resource_needs_computes_shortfall_against_owned():
    blueprints = {"Rhino": {"Parts": [{"Count": 5, "Name": "Neurodes", "Type": "Resource"}]}}
    out = service.build_resource_needs(["Rhino"], blueprints, owned_resources={"Neurodes": 2})
    assert out[0].need == 5 and out[0].owned == 2 and out[0].short_by == 3


def test_build_resource_needs_shortfall_floors_at_zero_when_overstocked():
    blueprints = {"Rhino": {"Parts": [{"Count": 5, "Name": "Neurodes", "Type": "Resource"}]}}
    out = service.build_resource_needs(["Rhino"], blueprints, owned_resources={"Neurodes": 999})
    assert out[0].short_by == 0


def test_build_resource_needs_skips_unmatched_equipment():
    assert service.build_resource_needs(["Totally Unknown Item"], {}) == []


def test_total_credits_needed_sums_across_equipment():
    blueprints = {
        "Rhino": {"Credits": 25000, "Parts": []},
        "Volt Prime": {"Credits": 15000, "Parts": []},
    }
    assert service.total_credits_needed(["Rhino", "Volt Prime"], blueprints) == 40000


def test_total_credits_needed_skips_unmatched_equipment():
    assert service.total_credits_needed(["Totally Unknown Item"], {}) == 0


def test_resource_needs_and_credits_single_pass_matches_the_two_wrappers():
    blueprints = {
        "Rhino": {
            "Credits": 25000,
            "Parts": [{"Count": 3, "Name": "Orokin Cell", "Type": "Resource"}],
        },
        "Volt Prime": {
            "Credits": 15000,
            "Parts": [{"Count": 500, "Name": "Circuits", "Type": "Resource"}],
        },
    }
    resource_needs, credits = service.resource_needs_and_credits(
        ["Rhino", "Volt Prime"], blueprints)
    assert credits == 40000
    by_res = {r.resource: r.need for r in resource_needs}
    assert by_res == {"Orokin Cell": 3, "Circuits": 500}
    # The two narrower wrappers must agree with the combined call.
    assert service.build_resource_needs(["Rhino", "Volt Prime"], blueprints) == resource_needs
    assert service.total_credits_needed(["Rhino", "Volt Prime"], blueprints) == credits


def test_plan_route_sets_partial_inventory_from_account_and_inventory_flags():
    base = dict(owned=set(), want=WANT, owned_parts=set(),
                items_data=ITEMS, mission_rewards=MISSION_REWARDS)
    assert service.plan_route(**base).partial_inventory is False
    assert service.plan_route(**base, account_id_given=True).partial_inventory is True
    assert service.plan_route(
        **base, account_id_given=True, has_full_inventory=True).partial_inventory is False
    # No account at all: a full inventory flag alone shouldn't matter.
    assert service.plan_route(**base, has_full_inventory=True).partial_inventory is False


def test_plan_route_leaves_priority_actions_for_the_caller():
    # priority_actions cross-checks buy_vs_farm (only known after the
    # caller's market.fetch_prices() call, a network call plan_route itself
    # never makes) -- plan_route only prepares invasion_parts for it.
    result = service.plan_route(owned=set(), want=WANT, owned_parts=set(),
                                items_data=ITEMS, mission_rewards=MISSION_REWARDS)
    assert result.priority_actions == []
    assert isinstance(result.invasion_parts, list)


def test_build_priority_actions_empty_result_has_no_actions():
    assert service.build_priority_actions(service.RouteResult(missing_equipment=0)) == []


def test_build_priority_actions_daily_deal_and_baro_are_now():
    result = service.RouteResult(
        missing_equipment=1,
        daily_deal={"item": "Rhino Prime", "discount": 50, "expiry": "soon"},
        baro={"location": "Larunda Relay", "until": "in 2 days", "items": ["Zenith"]},
    )
    actions = service.build_priority_actions(result)
    urgencies = {a.urgency for a in actions}
    assert urgencies == {"now"}
    assert any("Darvo" in a.title for a in actions)
    assert any("Baro" in a.title for a in actions)


def test_build_priority_actions_live_fissure_node_is_now():
    result = service.RouteResult(
        missing_equipment=1,
        non_prime=[service.Mission(node="Venus - Fossa", game_mode="Assassination",
                                    parts=["Rhino Chassis Blueprint"], live_fissure="Lith")],
    )
    actions = service.build_priority_actions(result)
    assert len(actions) == 1
    assert actions[0].urgency == "now"
    assert "Venus - Fossa" in actions[0].detail


def test_build_priority_actions_live_relic_farm_node_is_now():
    result = service.RouteResult(
        missing_equipment=1,
        prime=[service.PrimeRelic(relic="Axi N3 Relic", tier="Axi", parts=["Nova Prime Systems"],
                                   farm_node_live=True)],
    )
    actions = service.build_priority_actions(result)
    assert len(actions) == 1
    assert actions[0].urgency == "now"
    assert "Axi N3 Relic" in actions[0].detail


def test_build_priority_actions_flags_live_fissure_that_is_cheaper_to_buy():
    # If the same part a live fissure would farm is also flagged in
    # buy_vs_farm (select_price_candidates already judged that farm route
    # slow/vaulted enough to be worth a market lookup), the "now" action
    # must say so rather than unconditionally pushing the player to farm.
    result = service.RouteResult(
        missing_equipment=1,
        non_prime=[service.Mission(node="Venus - Fossa", game_mode="Assassination",
                                    parts=["Rhino Chassis Blueprint"], live_fissure="Lith")],
        buy_vs_farm=[service.BuyVsFarm(item="Rhino Chassis Blueprint", plat=15,
                                       tradable=True, url=None, minutes=360, source="Venus - Fossa")],
    )
    actions = service.build_priority_actions(result)
    assert len(actions) == 1
    assert "cheaper to buy" in actions[0].detail


def test_build_priority_actions_live_relic_farm_flags_when_cheaper_to_buy():
    result = service.RouteResult(
        missing_equipment=1,
        prime=[service.PrimeRelic(relic="Axi N3 Relic", tier="Axi", parts=["Nova Prime Systems"],
                                   farm_node_live=True)],
        buy_vs_farm=[service.BuyVsFarm(item="Nova Prime Systems", plat=20,
                                       tradable=True, url=None, minutes=400, source="Axi N3 Relic")],
    )
    actions = service.build_priority_actions(result)
    assert len(actions) == 1
    assert "cheaper to buy" in actions[0].detail


def test_build_priority_actions_invasions_are_soon():
    # invasion_parts is passed explicitly by plan_route (from its own
    # invasion_hits), not re-derived by string-matching event_source keys.
    result = service.RouteResult(missing_equipment=1)
    actions = service.build_priority_actions(result, invasion_parts={"Ash Prime Systems"})
    assert len(actions) == 1
    assert actions[0].urgency == "soon"
    assert "invasion" in actions[0].title


def test_build_priority_actions_ignores_non_invasion_event_source_entries():
    # event_source can hold non-invasion transient/event entries (bounties,
    # Kahl's Garrison, ...) built the same way -- these must not be
    # mistaken for invasion hits just because invasion_parts wasn't passed.
    result = service.RouteResult(
        missing_equipment=1,
        event_source={"Kahl's Garrison (weekly)": ["Some Part"]},
    )
    assert service.build_priority_actions(result) == []


def test_build_priority_actions_radiant_relic_suggests_squad_unless_already_on():
    result = service.RouteResult(
        missing_equipment=1,
        prime=[service.PrimeRelic(relic="Axi N3 Relic", tier="Axi", parts=["Nova Prime Systems"],
                                   best_refinement="Radiant")],
        squad_radiant=False,
    )
    actions = service.build_priority_actions(result)
    assert len(actions) == 1 and actions[0].urgency == "squad"
    # best_refinement is computed at whatever squad_size the plan already used
    # (1, since squad_radiant is False here) -- Radiant already won solo, so
    # the message must not claim solo isn't worth it (that would contradict
    # the plan's own recommendation).
    assert "not worth" not in actions[0].detail
    assert "solo" not in actions[0].detail.lower()

    result.squad_radiant = True
    assert service.build_priority_actions(result) == []


def test_build_priority_actions_endless_mode_suggests_squad():
    result = service.RouteResult(
        missing_equipment=1,
        non_prime=[service.Mission(node="Uranus - Ur", game_mode="Disruption", parts=["X"])],
    )
    actions = service.build_priority_actions(result)
    assert len(actions) == 1
    assert actions[0].urgency == "squad"
    assert "Disruption" in actions[0].detail


def test_build_priority_actions_orders_now_before_soon_before_squad():
    result = service.RouteResult(
        missing_equipment=1,
        daily_deal={"item": "X", "discount": 10, "expiry": "today"},
        non_prime=[service.Mission(node="Uranus - Ur", game_mode="Disruption", parts=["X"])],
    )
    actions = service.build_priority_actions(result, invasion_parts={"X"})
    assert [a.urgency for a in actions] == ["now", "soon", "squad"]
