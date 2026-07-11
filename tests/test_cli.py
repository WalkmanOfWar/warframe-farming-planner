"""CLI wiring tests: option resolution, error messages, and the
partial-inventory note — not the route-planning logic itself (see
test_service.py), just that cli.py glues the pieces together correctly and
never makes a real network call while doing it.
"""

from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from warframe_routes import catalog, cli, data, items, market, private_inventory, service, sync, worldstate
from warframe_routes.service import Mission, RouteResult


def _fake_result(missing=1, non_prime=None):
    return RouteResult(
        missing_equipment=missing,
        non_prime=non_prime or [],
        missing_equipment_names=["Rhino"],
    )


@pytest.fixture(autouse=True)
def _stub_data_sources(monkeypatch):
    """Every route() call touches these regardless of which owned-source path
    is under test; stub them so no test makes a real HTTP request. Individual
    tests further override sync.fetch_owned / private_inventory.* / service.plan_route."""
    monkeypatch.setattr(items, "load_items", lambda force_refresh=False: [])
    monkeypatch.setattr(data, "load_raw", lambda force_refresh=False: {})
    monkeypatch.setattr(data, "load_transient_raw", lambda force_refresh=False: [])
    monkeypatch.setattr(catalog, "all_targets", lambda items_data: ["Rhino"])
    monkeypatch.setattr(worldstate, "load_syndicate_missions", lambda force_refresh=False: None)
    monkeypatch.setattr(worldstate, "load_section", lambda name, force_refresh=False: None)
    monkeypatch.setattr(market, "fetch_prices", lambda candidates: {})
    monkeypatch.setattr("warframe_routes.blueprint_costs.load_blueprints", lambda force_refresh=False: {})


def _wishlist(tmp_path):
    path = tmp_path / "wishlist.json"
    path.write_text('["Rhino"]')
    return str(path)


def test_nonce_without_account_id_is_rejected():
    result = CliRunner().invoke(cli.cli, ["route", "--nonce", "abc"])
    assert result.exit_code != 0
    assert "--nonce requires --account-id" in result.output


def test_no_owned_source_and_no_wishlist_is_rejected():
    result = CliRunner().invoke(cli.cli, ["route"])
    assert result.exit_code != 0
    assert "Provide --account-id" in result.output


def test_wishlist_only_plan_prints_missions(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(
        missing=1, non_prime=[Mission(node="Venus - Fossa", game_mode="Assassination",
                                       parts=["Rhino Chassis Blueprint"])]))
    result = CliRunner().invoke(cli.cli, ["route", "--wishlist", _wishlist(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Non-Prime" in result.output
    assert "Rhino Chassis Blueprint" in result.output
    assert "Using public profile only" not in result.output


def test_nothing_to_farm_message(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(missing=0))
    result = CliRunner().invoke(cli.cli, ["route", "--wishlist", _wishlist(tmp_path)])
    assert result.exit_code == 0
    assert "Nothing to farm" in result.output


def test_account_id_only_shows_partial_inventory_note(monkeypatch, tmp_path):
    monkeypatch.setattr(sync, "fetch_owned", lambda account_id: set())
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(missing=1))
    result = CliRunner().invoke(
        cli.cli, ["route", "--account-id", "a" * 24, "--wishlist", _wishlist(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Using public profile only" in result.output


def test_account_id_with_inventory_file_does_not_show_partial_note(monkeypatch, tmp_path):
    # --inventory already has loose parts; pairing it with --account-id (to also
    # catch anything newer on the public profile) must not claim the data is partial.
    inv_path = tmp_path / "inventory.json"
    inv_path.write_text('{"MiscItems": [], "XPInfo": []}')
    monkeypatch.setattr(private_inventory, "load_inventory",
                         lambda path: {"MiscItems": [], "XPInfo": []})
    monkeypatch.setattr(sync, "fetch_owned", lambda account_id: set())
    monkeypatch.setattr(private_inventory, "collect_item_types", lambda inv: set())
    monkeypatch.setattr(sync, "resolve_names", lambda types, items_data: set())
    monkeypatch.setattr(private_inventory, "pending_owned", lambda inv, items_data: (set(), set()))
    monkeypatch.setattr(private_inventory, "owned_parts", lambda inv, items_data: set())
    monkeypatch.setattr(private_inventory, "owned_relics", lambda inv, items_data: {})
    monkeypatch.setattr(private_inventory, "owned_resources", lambda inv, items_data: {})
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(missing=1))
    result = CliRunner().invoke(cli.cli, [
        "route", "--account-id", "a" * 24, "--inventory", str(inv_path),
        "--wishlist", _wishlist(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    assert "Using public profile only" not in result.output


def test_invalid_account_id_reported_as_bad_parameter(monkeypatch, tmp_path):
    def _raise(account_id):
        raise sync.InvalidAccountId("bad id")
    monkeypatch.setattr(sync, "fetch_owned", _raise)
    result = CliRunner().invoke(
        cli.cli, ["route", "--account-id", "not-valid", "--wishlist", _wishlist(tmp_path)])
    assert result.exit_code != 0
    assert "bad id" in result.output


def test_helper_path_skips_public_profile_and_note(monkeypatch, tmp_path):
    monkeypatch.setattr(private_inventory, "run_helper", lambda path: {"MiscItems": [], "XPInfo": []})
    fetch_owned_mock = Mock(side_effect=AssertionError(
        "public profile should be skipped when --helper already gave a full inventory"))
    monkeypatch.setattr(sync, "fetch_owned", fetch_owned_mock)
    monkeypatch.setattr(private_inventory, "collect_item_types", lambda inv: set())
    monkeypatch.setattr(sync, "resolve_names", lambda types, items_data: set())
    monkeypatch.setattr(private_inventory, "pending_owned", lambda inv, items_data: (set(), set()))
    monkeypatch.setattr(private_inventory, "owned_parts", lambda inv, items_data: set())
    monkeypatch.setattr(private_inventory, "owned_relics", lambda inv, items_data: {})
    monkeypatch.setattr(private_inventory, "owned_resources", lambda inv, items_data: {})
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(missing=1))
    result = CliRunner().invoke(cli.cli, [
        "route", "--account-id", "a" * 24, "--helper", "helper.exe",
        "--wishlist", _wishlist(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    fetch_owned_mock.assert_not_called()
    assert "Using public profile only" not in result.output
