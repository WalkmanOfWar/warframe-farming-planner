"""Command-line entry point: ``wfroutes``."""

from __future__ import annotations

import click

from . import (acquisition, catalog, data, inventory, items, optimize,
               private_inventory, sync)

# Best community spots to farm each relic tier (you farm a tier, not a relic).
RELIC_TIER_GUIDE = {
    "Lith": "Hepit (Void) - Capture, fast",
    "Meso": "Ukko (Void) - Capture  /  Olympus (Mars) - Disruption, Rot C",
    "Neo": "Ukko (Void) - Capture  /  Ur (Uranus) - Disruption, Rot B/C",
    "Axi": "Apollo (Lua) - Disruption, Rot B/C",
    "Requiem": "Kuva Siphon / Kuva Flood missions",
}
_GENERIC_TIER_HINT = "farm this tier at any matching void fissure"


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
    "--refresh",
    is_flag=True,
    help="Force re-download of drop data, ignoring the local cache.",
)
def route(account_id: str | None, inventory_file: str | None, nonce: str | None,
          helper: str | None, owned: str | None, wishlist: str | None,
          have_parts: str | None, refresh: bool) -> None:
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
        want = {name.strip().casefold() for name in catalog.fetch_all_targets()}

    needed_equipment = inventory.compute_needed(want, have)

    if not needed_equipment:
        click.echo("Nothing to farm — you already own everything in the target set.")
        return

    plan = acquisition.build_plan(
        items_data,
        data.load_raw(force_refresh=refresh),
        needed_equipment,
    )

    owned_parts: set[str] = set()
    if inv is not None:
        owned_parts |= {n.strip().casefold()
                        for n in private_inventory.owned_parts(inv, items_data)}
    if have_parts:
        owned_parts |= inventory.load_item_list(have_parts)
    plan.direct_parts -= owned_parts
    plan.not_farmable -= owned_parts
    for p in owned_parts:
        plan.prime_part_relics.pop(p, None)

    disp = lambda p: plan.part_display.get(p, p)

    # --- Non-Prime: real fewest-missions route over boss/mission nodes ---
    if plan.direct_parts:
        result = optimize.optimize_route(plan.direct_nodes, plan.direct_parts)
        click.echo(f"Non-Prime — {len(plan.direct_parts)} part(s) from "
                   f"{result.mission_count} mission(s):\n")
        for i, step in enumerate(result.steps, 1):
            click.echo(f"{i}. {step.node.key}  [{step.node.game_mode}]")
            for item in sorted(disp(p) for p in step.covers):
                click.echo(f"     - {item}")

    # --- Prime: per-part relic, plus a tier farming guide (you farm tiers) ---
    if plan.prime_part_relics:
        click.echo(f"\nPrime — {len(plan.prime_part_relics)} part(s) "
                   "(farm the relic's TIER, then crack it at a void fissure):\n")
        for pnorm in sorted(plan.prime_part_relics, key=disp):
            relics = ", ".join(sorted(plan.prime_part_relics[pnorm]))
            click.echo(f"  {disp(pnorm)}  <-  {relics}")

        tiers = {items.relic_tier(r)
                 for relics in plan.prime_part_relics.values() for r in relics}
        click.echo("\n  Relic tiers to farm:")
        for tier in sorted(tiers):
            click.echo(f"    {tier}: {RELIC_TIER_GUIDE.get(tier, _GENERIC_TIER_HINT)}")

    if plan.not_farmable:
        vaulted = plan.vaulted_equipment()
        click.echo(f"\nVaulted / not currently farmable "
                   f"({len(plan.not_farmable)} prime part(s), "
                   f"{len(vaulted)} fully-vaulted item(s)):")
        for item in sorted(vaulted):
            click.echo(f"  - {item}")

    if plan.no_mission_source:
        click.echo(f"\nNot from mission drops — get elsewhere (market, clan dojo, "
                   f"syndicate, Baro, lich/sister, standing, quest, event) "
                   f"({len(plan.no_mission_source)} item(s)):")
        for item in sorted(plan.no_mission_source):
            click.echo(f"  - {item}")


if __name__ == "__main__":
    cli()
