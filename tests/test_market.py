import responses

from warframe_routes import market


def _price_json(name, avg):
    return [{"name": name, "tradable": True, "url": f"https://warframe.market/items/{name}",
             "prices": {"average": avg}}]


@responses.activate
def test_fetch_prices_tries_set_suffix_first(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "_CACHE_FILE", tmp_path / "market_prices.json")
    responses.add(responses.GET, market.PRICECHECK_URL.format("Corinth Prime Set"),
                  json=_price_json("Corinth Prime Set", 83))

    prices = market.fetch_prices(["Corinth Prime"])

    assert prices["Corinth Prime"] == {
        "name": "Corinth Prime Set", "plat": 83, "tradable": True,
        "url": "https://warframe.market/items/Corinth Prime Set",
    }


@responses.activate
def test_fetch_prices_falls_back_to_bare_name(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "_CACHE_FILE", tmp_path / "market_prices.json")
    responses.add(responses.GET, market.PRICECHECK_URL.format("Astilla Prime Barrel Set"),
                  json=[])  # no "Set" bundle for a loose part
    responses.add(responses.GET, market.PRICECHECK_URL.format("Astilla Prime Barrel"),
                  json=_price_json("Astilla Prime Barrel", 6))

    prices = market.fetch_prices(["Astilla Prime Barrel"])

    assert prices["Astilla Prime Barrel"]["plat"] == 6


@responses.activate
def test_fetch_prices_skips_unmatched_and_failed_lookups(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "_CACHE_FILE", tmp_path / "market_prices.json")
    responses.add(responses.GET, market.PRICECHECK_URL.format("Nothing Set"), json=[])
    responses.add(responses.GET, market.PRICECHECK_URL.format("Nothing"), status=500)

    prices = market.fetch_prices(["Nothing"])

    assert prices == {}


@responses.activate
def test_fetch_prices_caches_between_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "_CACHE_FILE", tmp_path / "market_prices.json")
    responses.add(responses.GET, market.PRICECHECK_URL.format("Titania Prime Set"),
                  json=_price_json("Titania Prime Set", 77))

    first = market.fetch_prices(["Titania Prime"])
    # No responses registered for a second round — a network call here would
    # raise ConnectionError from the `responses` mock, proving the cache hit.
    second = market.fetch_prices(["Titania Prime"])

    assert first == second == {
        "Titania Prime": {"name": "Titania Prime Set", "plat": 77,
                          "tradable": True,
                          "url": "https://warframe.market/items/Titania Prime Set"}
    }


def test_fetch_prices_empty_input_short_circuits(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "_CACHE_FILE", tmp_path / "market_prices.json")
    assert market.fetch_prices([]) == {}
