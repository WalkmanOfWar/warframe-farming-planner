"""Command-line entry point: ``wfroutes``."""

from __future__ import annotations

import click

from . import (catalog, data, inventory, items, market, private_inventory,
               service, sync, worldstate)


def _hours(minutes: float) -> str:
    """Human-friendly duration: '45m', '2h 10m'."""
    m = int(round(minutes))
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _effort(runs: float | None, minutes: float | None) -> str:
    """Inline '  (~N runs, ~Xh Ym)' tag; empty when effort is unknown."""
    if runs is None or minutes is None:
        return ""
    return f"  (~{runs} runs, ~{_hours(minutes)})"


def _price(name: str, prices: dict) -> str:
    """Inline '  [buy ~Np]' tag when a warframe.market price is known."""
    p = prices.get(name)
    return f"  [buy ~{p['plat']}p]" if p else ""


@click.group()
def cli() -> None:
    """Suggest fewest-mission Warframe farming routes."""


@cli.command()
@click.option(
    "--account-id",
    help="Warframe Account ID (24-hex 'gid' cookie / EE.log id, NOT username) "
         "to auto-sync owned items from your public profile.",
)
@click.option(
    "--inventory",
    "inventory_file",
    type=click.Path(exists=True, dir_okay=False),
    help="inventory.json exported by AlecaFrame / warframe-api-helper. Gives both "
         "owned gear AND loose parts, so the route drops parts you already have.",
)
@click.option(
    "--nonce",
    help="Live session nonce (with --account-id) to download your full inventory "
         "directly — same data as --inventory, no file/password. Get accountId+nonce "
         "from warframe-api-helper while the game is running; it expires on game exit.",
)
@click.option(
    "--helper",
    type=click.Path(dir_okay=False),
    help="Path to warframe-api-helper(.exe). With Warframe running, runs it to pull "
         "your full inventory automatically (owned gear + loose parts). No password.",
)
@click.option(
    "--owned",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON list of items you already own (alternative/addition to --account-id).",
)
@click.option(
    "--wishlist",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional: narrow the target to this JSON list of items. "
         "Default target is everything masterable you don't already own.",
)
@click.option(
    "--have-parts",
    "have_parts",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON list of loose parts you already own (e.g. 'Caliban Prime "
         "Blueprint'). The public profile can't see un-built parts, so list them "
         "here to drop them from the route. Use names exactly as the route prints.",
)
@click.option(
    "--refinement",
    type=click.Choice(["Intact", "Exceptional", "Flawless", "Radiant"]),
    default="Intact",
    show_default=True,
    help="Relic refinement assumed when estimating Prime-part effort. Higher "
         "refinement raises rare-part chances but lowers common ones.",
)
@click.option(
    "--refresh",
    is_flag=True,
    help="Force re-download of drop data, ignoring the local cache.",
)
def route(account_id: str | None, inventory_file: str | None, nonce: str | None,
          helper: str | None, owned: str | None, wishlist: str | None,
          have_parts: str | None, refinement: str, refresh: bool) -> None:
    """Compute the route to farm everything you're still missing.

    With just --account-id, the target is every masterable item you don't own.
    """
    items_data = items.load_items(force_refresh=refresh)

    if nonce and not account_id:
        raise click.UsageError("--nonce requires --account-id.")
    inv = None
    inv_is_full = False
    if helper:
        try:
            inv = private_inventory.run_helper(helper)
            inv_is_full = True
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--helper")
    elif account_id and nonce:
        try:
            inv = private_inventory.fetch_inventory(account_id, nonce)
            inv_is_full = True  # live download is authoritative for this account
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--nonce")
    elif inventory_file:
        inv = private_inventory.load_inventory(inventory_file)

    have: set[str] = set()
    if owned:
        have |= inventory.load_item_list(owned)
    if inv is not None:
        types = private_inventory.collect_item_types(inv)
        have |= {n.strip().casefold() for n in sync.resolve_names(types, items_data)}
        # Items building in the foundry are committed — treat as owned.
        pending_equip, _pending_parts = private_inventory.pending_owned(inv, items_data)
        have |= pending_equip
    # A live (nonce) inventory already lists all owned gear, so skip the public
    # profile then; otherwise the profile still adds your mastered gear.
    if account_id and not inv_is_full:
        try:
            have |= {name.strip().casefold() for name in sync.fetch_owned(account_id)}
        except sync.InvalidAccountId as exc:
            raise click.BadParameter(str(exc), param_hint="--account-id")

    if not have and not wishlist:
        raise click.UsageError(
            "Provide --account-id / --inventory / --owned so I know what you "
            "already have, or --wishlist to target specific items."
        )

    if wishlist:
        want = inventory.load_item_list(wishlist)
    else:
        want = {name.strip().casefold() for name in catalog.all_targets(items_data)}

    owned_parts: set[str] = set()
    owned_relics: dict[str, int] = {}
    if inv is not None:
        owned_parts |= {n.strip().casefold()
                        for n in private_inventory.owned_parts(inv, items_data)}
        _, pending_parts = private_inventory.pending_owned(inv, items_data)
        owned_parts |= {n.strip().casefold() for n in pending_parts}
        owned_relics = private_inventory.owned_relics(inv, items_data)
    if have_parts:
        owned_parts |= inventory.load_item_list(have_parts)

    try:
        syndicate_missions = worldstate.load_syndicate_missions(force_refresh=refresh)
    except Exception:
        syndicate_missions = None  # worldstate unavailable — proceed without filtering

    def _ws(name):
        try:
            return worldstate.load_section(name, force_refresh=refresh)
        except Exception:
            return None  # live section unavailable — plan works without it

    result = service.plan_route(
        owned=have,
        want=want,
        owned_parts=owned_parts,
        items_data=items_data,
        mission_rewards=data.load_raw(force_refresh=refresh),
        refinement=refinement,
        transient_rewards=data.load_transient_raw(force_refresh=refresh),
        syndicate_missions=syndicate_missions,
        owned_relics=owned_relics,
        fissures=_ws("fissures"),
        void_trader=_ws("voidTrader"),
        invasions=_ws("invasions"),
        vault_trader=_ws("vaultTrader"),
        daily_deals=_ws("dailyDeals"),
    )

    try:
        candidates = service.select_price_candidates(result)
        result.market_prices = market.fetch_prices(candidates)
    except Exception:
        pass  # market prices are a bonus annotation, never required

    if not result.missing_equipment:
        click.echo("Nothing to farm — you already own everything in the target set.")
        return

    if result.non_prime:
        n = sum(len(m.parts) for m in result.non_prime)
        click.echo(f"Non-Prime — {n} part(s) from {len(result.non_prime)} mission(s):\n")
        for i, m in enumerate(result.non_prime, 1):
            # "Unknown" is a sentinel for a missing (mode) in the drop location;
            # don't print a meaningless tag (matches the web UI).
            mode = f"  [{m.game_mode}]" if m.game_mode and m.game_mode != "Unknown" else ""
            dip = (f"  ** LIVE {m.live_fissure} fissure — bring a relic! **"
                   if m.live_fissure else "")
            click.echo(f"{i}. {m.node}{mode}{_effort(m.runs, m.minutes)}{dip}")
            for part in m.parts:
                pr = m.part_runs.get(part)
                tail = f"  (~{pr} runs)" if pr is not None else ""
                click.echo(f"     - {part}{tail}{_price(part, result.market_prices)}")

    if result.prime:
        click.echo(f"\nPrime — crack {len(result.prime)} relic(s) for "
                   f"{result.prime_part_count} part(s), {refinement} "
                   "(farm the relic's TIER, then crack it at a void fissure):\n")
        for pr in result.prime:
            cracks = f"  (~{pr.cracks} cracks)" if pr.cracks is not None else ""
            owned = f"  [own {pr.owned}]" if pr.owned else ""
            hint = (f"  → crack as {pr.best_refinement} (~{_hours(pr.best_refinement_minutes)})"
                    if pr.best_refinement else "")
            live = ("  ** farm node is a LIVE fissure — farm & crack together! **"
                    if pr.farm_node_live else ("  [tier live now]" if pr.tier_live else ""))
            click.echo(f"  {pr.relic}{_effort(pr.runs, pr.minutes)}{cracks}{owned}{hint}{live}")
            for part in pr.parts:
                click.echo(f"     - {part}{_price(part, result.market_prices)}")
        click.echo("\n  Relic tiers to farm:")
        for t in result.tiers:
            click.echo(f"    {t.tier}: {t.where}")
            for f in result.active_fissures.get(t.tier, [])[:3]:
                tag = " [Steel Path]" if f["hard"] else (" [Void Storm]" if f["storm"] else "")
                click.echo(f"      LIVE: {f['node']} · {f['mission']}{tag}")

    if result.baro:
        click.echo(f"\nBaro Ki'Teer has {len(result.baro['items'])} item(s) you need "
                   f"(at {result.baro['location']}, until {result.baro['until']}):")
        for item in result.baro["items"]:
            click.echo(f"  - {item}")

    if result.vault_trader:
        click.echo(f"\nVarzia (Prime Resurgence) is selling "
                   f"{len(result.vault_trader['items'])} fully-vaulted item(s) you need "
                   f"(at {result.vault_trader['location']}, until "
                   f"{result.vault_trader['until']}) — the only non-trade way to get them:")
        for item in result.vault_trader["items"]:
            click.echo(f"  - {item}")

    if result.daily_deal:
        d = result.daily_deal
        click.echo(f"\nDarvo's daily deal has {d['item']} you need "
                   f"({d['discount']}% off, until {d['expiry']}).")

    if result.total_minutes:
        click.echo(f"\nEstimated total time: ~{_hours(result.total_minutes)} "
                   f"(rough; assumes {refinement} relics, solo cracking).")

    if result.vaulted_crackable:
        click.echo(f"\nVaulted parts you can still crack — you own the relic "
                   f"({len(result.vaulted_crackable)} part(s)):")
        for c in result.vaulted_crackable:
            click.echo(f"  - {c['part']}  ←  {c['relic']} "
                       f"(own {c['owned']}, {c['chance']}% per crack)")

    if result.vaulted_equipment:
        click.echo(f"\nVaulted / not currently farmable "
                   f"({result.vaulted_part_count} prime part(s), "
                   f"{len(result.vaulted_equipment)} fully-vaulted item(s)):")
        for item in result.vaulted_equipment:
            click.echo(f"  - {item}{_price(item, result.market_prices)}")

    if result.event_source:
        n = sum(len(p) for p in result.event_source.values())
        click.echo(f"\nAlso available from events / alerts ({n} item(s)):")
        for src, its in result.event_source.items():
            click.echo(f"  {src}:")
            for item in its:
                click.echo(f"     - {item}")

    if result.special_source:
        n = sum(len(p) for p in result.special_source.values())
        click.echo(f"\nOther sources — non-standard nodes "
                   f"(Sanctuary Onslaught, Plains, syndicates, ...) "
                   f"({n} part(s)):")
        for src, parts in result.special_source.items():
            click.echo(f"  {src}:")
            for part in parts:
                click.echo(f"     - {part}")

    if result.no_part_source:
        n = sum(len(p) for p in result.no_part_source.values())
        click.echo(f"\nNo drop source in database (Market / Duviri / Nightwave / …) "
                   f"({n} part(s)):")
        for equip, parts in result.no_part_source.items():
            click.echo(f"  {equip}:")
            for part in parts:
                click.echo(f"     - {part}")

    if result.no_mission_source:
        click.echo(f"\nNot from mission drops — get elsewhere (market, clan dojo, "
                   f"syndicate, Baro, lich/sister, standing, quest, event) "
                   f"({len(result.no_mission_source)} item(s)):")
        for item in result.no_mission_source:
            click.echo(f"  - {item}")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (dev).")
def serve(host: str, port: int, reload: bool) -> None:
    """Run the local web UI (FastAPI backend + built frontend)."""
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            'Web extras not installed. Run:  pip install -e ".[web]"')
    click.echo(f"Serving on http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run("warframe_routes.web:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()
