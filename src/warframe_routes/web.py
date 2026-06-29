"""FastAPI backend: a thin HTTP layer over :mod:`warframe_routes.service`.

Run with ``wfroutes serve`` (or ``uvicorn warframe_routes.web:app``). Intended to
run **locally**, so it can use the same inputs as the CLI: a public Account ID, a
live inventory pull (Account ID + nonce), or an uploaded inventory.json. The built
React frontend (``frontend/dist``) is served at ``/`` when present.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import catalog, data, inventory, items, private_inventory, service, sync

app = FastAPI(title="Warframe Farming Planner")

# Allow the Vite dev server (localhost:5173) to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    account_id: str | None = None
    nonce: str | None = None
    wishlist: list[str] | None = None
    have_parts: list[str] | None = None
    inventory: dict | None = None  # uploaded inventory.json contents
    refresh: bool = False
    refinement: str = "Intact"     # relic refinement assumed for Prime effort


def _norm(names) -> set[str]:
    return {str(n).strip().casefold() for n in names}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/route")
def route(req: RouteRequest) -> dict:
    items_data = items.load_items(force_refresh=req.refresh)

    inv = req.inventory
    inv_is_full = False
    if inv is None and req.account_id and req.nonce:
        try:
            inv = private_inventory.fetch_inventory(req.account_id, req.nonce)
            inv_is_full = True
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    have: set[str] = set()
    owned_parts: set[str] = set()
    if inv is not None:
        types = private_inventory.collect_item_types(inv)
        have |= _norm(sync.resolve_names(types, items_data))
        owned_parts |= _norm(private_inventory.owned_parts(inv, items_data))
    if req.account_id and not inv_is_full:
        try:
            have |= _norm(sync.fetch_owned(req.account_id))
        except sync.InvalidAccountId as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if req.have_parts:
        owned_parts |= _norm(req.have_parts)

    if not have and not req.wishlist:
        raise HTTPException(
            status_code=400,
            detail="Provide an Account ID, an inventory, or a wishlist.",
        )

    want = (_norm(req.wishlist) if req.wishlist
            else _norm(catalog.all_targets(items_data)))

    result = service.plan_route(
        owned=have,
        want=want,
        owned_parts=owned_parts,
        items_data=items_data,
        mission_rewards=data.load_raw(force_refresh=req.refresh),
        refinement=req.refinement,
    )
    return result.to_dict()


def _mount_frontend() -> None:
    """Serve the built React app at / if it exists (production/local use)."""
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")


_mount_frontend()
