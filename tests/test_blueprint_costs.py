import responses

from warframe_routes import blueprint_costs as bc

# A small synthetic Lua fixture covering every real-data shape this module
# has to handle: comments, a weapon-style part with an *embedded* Cost
# (self-contained recursive recipe), a Warframe-style part with *no*
# embedded Cost (must be looked up as a sibling top-level entry), the Prime
# "Prime X" naming quirk that needs word-overlap dedup, and a bare boolean
# literal (real data has these on unrelated fields).
LUA_FIXTURE = """return {
	Blueprints = {
		Aeolak = {
			--BPCost = ,
			Credits = 15000,
			Consumed = true,
			Parts = {
				{ Count = 50, Name = "Thrax Plasm", Type = "Resource" },
				{
					Cost = {
						Parts = {
							{ Count = 5, Name = "Voidgel Orb", Type = "Resource" }
						}
					},
					Count = 1,
					Name = "Barrel",
					Type = "Item"
				}
			},
			Result = "Aeolak"
		}
	},
	Suits = {
		Dante = {
			Credits = 25000,
			Parts = {
				{ Count = 1, Name = "Chassis", Type = "Item" },
				{ Count = 3, Name = "Orokin Cell", Type = "Resource" }
			},
			Result = "Dante"
		},
		["Dante Chassis"] = {
			Credits = 15000,
			Parts = {
				{ Count = 8000, Name = "Alloy Plate", Type = "Resource" }
			},
			Result = "Dante Chassis"
		},
		["Ash Prime"] = {
			Credits = 25000,
			Parts = {
				{ Count = 1, Name = "Prime Chassis", Type = "PrimePart" },
				{ Count = 1, Name = "Orokin Cell", Type = "Resource" }
			},
			Result = "Ash Prime"
		},
		["Ash Prime Chassis"] = {
			Credits = 15000,
			Parts = {
				{ Count = 500, Name = "Circuits", Type = "Resource" }
			},
			Result = "Ash Prime Chassis"
		}
	}
}"""


def test_parses_nested_tables_comments_and_booleans():
    parsed = bc._parse_lua_table(LUA_FIXTURE)
    assert set(parsed.keys()) == {"Blueprints", "Suits"}
    assert parsed["Blueprints"]["Aeolak"]["Credits"] == 15000
    assert parsed["Blueprints"]["Aeolak"]["Consumed"] is True


def test_load_blueprints_merges_all_top_level_categories(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "_RAW_CACHE_FILE", tmp_path / "raw.lua")
    monkeypatch.setattr(bc, "_PARSED_CACHE_FILE", tmp_path / "parsed.json")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, bc.BLUEPRINTS_URL, body=LUA_FIXTURE)
        blueprints = bc.load_blueprints()
    # Weapons (Blueprints) and Warframes (Suits) both present, one flat dict.
    assert "Aeolak" in blueprints
    assert "Dante" in blueprints


def _fixture_blueprints():
    parsed = bc._parse_lua_table(LUA_FIXTURE)
    merged = {}
    for category in parsed.values():
        merged.update(category)
    return merged


def test_expand_resource_cost_follows_embedded_cost():
    blueprints = _fixture_blueprints()
    costs = bc.expand_resource_cost("Aeolak", blueprints)
    assert costs == {"Thrax Plasm": 50, "Voidgel Orb": 5}


def test_expand_resource_cost_follows_sibling_lookup_for_warframe_parts():
    blueprints = _fixture_blueprints()
    costs = bc.expand_resource_cost("Dante", blueprints)
    assert costs == {"Orokin Cell": 3, "Alloy Plate": 8000}


def test_expand_resource_cost_dedupes_prime_word_overlap():
    # "Ash Prime" + "Prime Chassis" must resolve to sibling key
    # "Ash Prime Chassis", not the naive double-up "Ash Prime Prime Chassis".
    blueprints = _fixture_blueprints()
    costs = bc.expand_resource_cost("Ash Prime", blueprints)
    assert costs == {"Orokin Cell": 1, "Circuits": 500}


def test_expand_resource_cost_unknown_name_returns_empty():
    assert bc.expand_resource_cost("Nonexistent Item", _fixture_blueprints()) == {}


def test_find_blueprint_key_case_insensitive():
    blueprints = _fixture_blueprints()
    assert bc.find_blueprint_key("dante", blueprints) == "Dante"
    assert bc.find_blueprint_key("  Ash Prime  ".strip(), blueprints) == "Ash Prime"
    assert bc.find_blueprint_key("Totally Unknown", blueprints) is None


def test_find_blueprint_key_with_prebuilt_index_matches_linear_scan():
    blueprints = _fixture_blueprints()
    index = bc.build_key_index(blueprints)
    assert index == {
        "aeolak": "Aeolak", "dante": "Dante", "dante chassis": "Dante Chassis",
        "ash prime": "Ash Prime", "ash prime chassis": "Ash Prime Chassis",
    }
    assert bc.find_blueprint_key("dante", blueprints, index) == "Dante"
    assert bc.find_blueprint_key("Ash Prime", blueprints, index) == "Ash Prime"
    assert bc.find_blueprint_key("Totally Unknown", blueprints, index) is None


def test_join_sibling_name_dedupes_overlapping_word():
    assert bc._join_sibling_name("Ash Prime", "Prime Chassis") == "Ash Prime Chassis"
    assert bc._join_sibling_name("Dante", "Chassis") == "Dante Chassis"


def test_load_blueprints_returns_empty_on_fetch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "_RAW_CACHE_FILE", tmp_path / "raw.lua")
    monkeypatch.setattr(bc, "_PARSED_CACHE_FILE", tmp_path / "parsed.json")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, bc.BLUEPRINTS_URL, status=503)
        assert bc.load_blueprints() == {}


def test_load_blueprints_returns_empty_on_unparseable_response(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "_RAW_CACHE_FILE", tmp_path / "raw.lua")
    monkeypatch.setattr(bc, "_PARSED_CACHE_FILE", tmp_path / "parsed.json")
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, bc.BLUEPRINTS_URL, body="not lua at all {{{")
        assert bc.load_blueprints() == {}


def test_expand_full_cost_sums_credits_across_sibling_lookup():
    blueprints = _fixture_blueprints()
    resources, credits = bc.expand_full_cost("Dante", blueprints)
    # Dante's own 25000 + Dante Chassis's own 15000 (sibling-looked-up sub-build).
    assert resources == {"Orokin Cell": 3, "Alloy Plate": 8000}
    assert credits == 40000


def test_expand_full_cost_sums_credits_across_embedded_cost():
    blueprints = _fixture_blueprints()
    # Aeolak's fixture Cost block has no explicit Credits key -> contributes 0,
    # only the top-level Aeolak Credits (15000) should be counted.
    _resources, credits = bc.expand_full_cost("Aeolak", blueprints)
    assert credits == 15000


def test_expand_full_cost_falls_back_to_pname_even_when_sibling_has_credits():
    # A sibling-named stub entry can carry a nonzero Credits with no real
    # Parts recipe (e.g. Aklato/Lato/Lex/Sicarus in the live wiki data), while
    # the actual resource recipe lives under the plain part name instead.
    # The resources-empty fallback must still trigger in that case, not be
    # suppressed just because the sibling had a credits value.
    blueprints = {
        "Nightfall": {
            "Credits": 10000,
            "Parts": [{"Count": 1, "Name": "Neuroptics", "Type": "Item"}],
        },
        "Nightfall Neuroptics": {"Credits": 5000, "Parts": []},
        "Neuroptics": {
            "Credits": 0,
            "Parts": [{"Count": 100, "Name": "Rubedo", "Type": "Resource"}],
        },
    }
    resources, credits = bc.expand_full_cost("Nightfall", blueprints)
    assert resources == {"Rubedo": 100}
    assert credits == 10000


def test_expand_resource_cost_unchanged_by_credits_refactor():
    # The pre-existing public function must still return just the dict.
    blueprints = _fixture_blueprints()
    assert bc.expand_resource_cost("Dante", blueprints) == {
        "Orokin Cell": 3, "Alloy Plate": 8000}
