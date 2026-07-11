"""FastAPI /api/route wiring tests — mirrors test_cli.py but through the HTTP
layer: option resolution, error responses, and the partial_inventory flag.
Skips entirely if the `web` extra isn't installed (fastapi/uvicorn aren't a
core dependency — see pyproject.toml)."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from warframe_routes import catalog, data, items, market, private_inventory, service, sync, worldstate
from warframe_routes.service import Mission, RouteResult
from warframe_routes.web import app


def _fake_result(missing=1, non_prime=None):
    return RouteResult(
        missing_equipment=missing,
        non_prime=non_prime or [],
        missing_equipment_names=["Rhino"],
    )


@pytest.fixture(autouse=True)
def _stub_data_sources(monkeypatch):
    monkeypatch.setattr(items, "load_items", lambda force_refresh=False: [])
    monkeypatch.setattr(data, "load_raw", lambda force_refresh=False: {})
    monkeypatch.setattr(data, "load_transient_raw", lambda force_refresh=False: [])
    monkeypatch.setattr(catalog, "all_targets", lambda items_data: ["Rhino"])
    monkeypatch.setattr(worldstate, "load_syndicate_missions", lambda force_refresh=False: None)
    monkeypatch.setattr(worldstate, "load_section", lambda name, force_refresh=False: None)
    monkeypatch.setattr(market, "fetch_prices", lambda candidates: {})
    monkeypatch.setattr("warframe_routes.blueprint_costs.load_blueprints", lambda force_refresh=False: {})


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_no_owned_source_and_no_wishlist_is_rejected(client):
    resp = client.post("/api/route", json={})
    assert resp.status_code == 400
    assert "Provide an Account ID" in resp.json()["detail"]


def test_wishlist_only_returns_missions(monkeypatch, client):
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(
        missing=1, non_prime=[Mission(node="Venus - Fossa", game_mode="Assassination",
                                       parts=["Rhino Chassis Blueprint"])]))
    resp = client.post("/api/route", json={"wishlist": ["Rhino"]})
    assert resp.status_code == 200, resp.text
    data_out = resp.json()
    assert data_out["missing_equipment"] == 1
    assert data_out["non_prime"][0]["node"] == "Venus - Fossa"
    assert data_out["partial_inventory"] is False


def test_account_id_only_sets_partial_inventory_true(monkeypatch, client):
    monkeypatch.setattr(sync, "fetch_owned", lambda account_id: set())
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(missing=1))
    resp = client.post("/api/route", json={"account_id": "a" * 24, "wishlist": ["Rhino"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["partial_inventory"] is True


def test_invalid_account_id_returns_400(monkeypatch, client):
    def _raise(account_id):
        raise sync.InvalidAccountId("bad id")
    monkeypatch.setattr(sync, "fetch_owned", _raise)
    resp = client.post("/api/route", json={"account_id": "not-valid", "wishlist": ["Rhino"]})
    assert resp.status_code == 400
    assert "bad id" in resp.json()["detail"]


def test_account_id_with_nonce_skips_public_profile_and_note(monkeypatch, client):
    monkeypatch.setattr(private_inventory, "fetch_inventory",
                         lambda account_id, nonce: {"MiscItems": [], "XPInfo": []})
    def _fail(account_id):
        raise AssertionError("public profile should be skipped when nonce already gave a full inventory")
    monkeypatch.setattr(sync, "fetch_owned", _fail)
    monkeypatch.setattr(private_inventory, "collect_item_types", lambda inv: set())
    monkeypatch.setattr(sync, "resolve_names", lambda types, items_data: set())
    monkeypatch.setattr(private_inventory, "pending_owned", lambda inv, items_data: (set(), set()))
    monkeypatch.setattr(private_inventory, "owned_parts", lambda inv, items_data: set())
    monkeypatch.setattr(private_inventory, "owned_relics", lambda inv, items_data: {})
    monkeypatch.setattr(private_inventory, "owned_resources", lambda inv, items_data: {})
    monkeypatch.setattr(service, "plan_route", lambda **kw: _fake_result(missing=1))
    resp = client.post("/api/route", json={
        "account_id": "a" * 24, "nonce": "live-nonce", "wishlist": ["Rhino"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["partial_inventory"] is False


def test_invalid_nonce_returns_400(monkeypatch, client):
    def _raise(account_id, nonce):
        raise ValueError("nonce expired")
    monkeypatch.setattr(private_inventory, "fetch_inventory", _raise)
    resp = client.post("/api/route", json={
        "account_id": "a" * 24, "nonce": "stale", "wishlist": ["Rhino"],
    })
    assert resp.status_code == 400
    assert "nonce expired" in resp.json()["detail"]
