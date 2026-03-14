from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..models import Cart, Coordinates
from ..models.cart import CartStatus
from .state import AppState

router = APIRouter()


def get_state(request: Request) -> AppState:
    return request.app.state.app


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class AddCartRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    max_orders_per_hour: int = 50


class OrchestrationRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: float = 10.0
    hours_ahead: int = 12


class CompleteScheduleRequest(BaseModel):
    schedule_id: str


# ---------------------------------------------------------------------------
# Fleet routes
# ---------------------------------------------------------------------------

@router.get("/fleet", summary="Get fleet overview")
async def get_fleet(request: Request):
    state = get_state(request)
    return state.fleet.summary()


@router.get("/fleet/carts", summary="List all carts")
async def list_carts(request: Request):
    state = get_state(request)
    return [c.model_dump_summary() for c in state.fleet.carts.values()]


@router.post("/fleet/carts", summary="Add a new cart to the fleet", status_code=201)
async def add_cart(request: Request, body: AddCartRequest):
    state = get_state(request)
    cart = Cart(
        name=body.name,
        current_location=Coordinates(lat=body.latitude, lng=body.longitude),
        max_orders_per_hour=body.max_orders_per_hour,
    )
    state.fleet.add_cart(cart)
    return {"message": "Cart added", "cart_id": cart.id, "cart": cart.model_dump_summary()}


@router.delete("/fleet/carts/{cart_id}", summary="Remove a cart from the fleet")
async def remove_cart(request: Request, cart_id: str):
    state = get_state(request)
    removed = state.fleet.remove_cart(cart_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Cart {cart_id} not found")
    return {"message": "Cart removed", "cart_id": cart_id}


@router.get("/fleet/carts/{cart_id}", summary="Get a single cart")
async def get_cart(request: Request, cart_id: str):
    state = get_state(request)
    cart = state.fleet.get_cart(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail=f"Cart {cart_id} not found")
    return cart.model_dump()


# ---------------------------------------------------------------------------
# Schedule routes
# ---------------------------------------------------------------------------

@router.get("/schedules", summary="List all active schedules")
async def list_schedules(request: Request):
    state = get_state(request)
    schedules = state.orchestrator.get_active_schedules()
    return [s.model_dump_summary() for s in schedules]


@router.post("/schedules/complete", summary="Mark a schedule as completed")
async def complete_schedule(request: Request, body: CompleteScheduleRequest):
    state = get_state(request)
    success = state.orchestrator.complete_schedule(body.schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Schedule {body.schedule_id} not found")
    return {"message": "Schedule completed", "schedule_id": body.schedule_id}


# ---------------------------------------------------------------------------
# Orchestration route
# ---------------------------------------------------------------------------

@router.post("/orchestrate", summary="Trigger a full orchestration cycle")
async def orchestrate(request: Request, body: OrchestrationRequest):
    """
    Runs EventAgent + SchedulerAgent in sequence:
      1. Discovers local events near the given coordinates.
      2. Assigns available carts to the best events.
      3. Returns the full result including schedules and fleet state.
    """
    state = get_state(request)
    result = await state.orchestrator.run_cycle(
        latitude=body.latitude,
        longitude=body.longitude,
        radius_km=body.radius_km,
        hours_ahead=body.hours_ahead,
    )
    return result.to_dict()
