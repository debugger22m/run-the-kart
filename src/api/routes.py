import random
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from ..models import Cart, Coordinates
from ..models.cart import CartStatus
from .state import AppState
from .loop import LoopConfig

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
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float = 10.0
    hours_ahead: int = 12

    model_config = {"extra": "ignore"}


class CompleteScheduleRequest(BaseModel):
    schedule_id: str


class AutonomousStartRequest(BaseModel):
    latitude: Optional[float] = None   # derived from fleet positions if omitted
    longitude: Optional[float] = None  # derived from fleet positions if omitted
    radius_km: float = 10.0
    hours_ahead: int = 12
    interval_seconds: int = 30


class CityRequest(BaseModel):
    name: str
    lat: float
    lng: float


# ---------------------------------------------------------------------------
# Fleet routes
# ---------------------------------------------------------------------------

@router.get("/fleet", summary="Get fleet overview including autonomous loop status")
async def get_fleet(request: Request):
    state = get_state(request)
    return {
        **state.fleet.summary(),
        "autonomous_loop": state.loop.status.to_dict(),
        "active_schedules": len(state.orchestrator.get_active_schedules()),
    }


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
# Orchestration route (manual one-shot)
# ---------------------------------------------------------------------------

@router.post("/orchestrate", summary="Trigger a single orchestration cycle manually")
async def orchestrate(
    request: Request,
    radius_km: float = 10.0,
    hours_ahead: int = 12,
):
    """
    Runs one full EventAgent → SchedulerAgent cycle.
    Search centre is automatically derived from the fleet's cart positions.
    """
    state = get_state(request)
    result = await state.orchestrator.run_cycle(
        radius_km=radius_km,
        hours_ahead=hours_ahead,
    )
    return result.to_dict()


# ---------------------------------------------------------------------------
# Autonomous loop routes
# ---------------------------------------------------------------------------

@router.post("/autonomous/start", summary="Start the autonomous orchestration loop")
async def start_autonomous(
    request: Request,
    radius_km: float = 10.0,
    hours_ahead: int = 12,
    interval_seconds: int = 30,
):
    """
    Starts the autonomous loop. Runs every `interval_seconds` seconds with no
    manual input — search centre is derived from fleet positions each cycle.
    """
    state = get_state(request)
    if state.loop.is_running():
        return {
            "message": "Autonomous loop is already running",
            "status": state.loop.status.to_dict(),
        }

    config = LoopConfig(
        radius_km=radius_km,
        hours_ahead=hours_ahead,
        interval_seconds=interval_seconds,
    )
    await state.loop.start(config)
    return {"message": "Autonomous loop started", "config": config.__dict__}


@router.post("/autonomous/stop", summary="Stop the autonomous orchestration loop")
async def stop_autonomous(request: Request):
    state = get_state(request)
    if not state.loop.is_running():
        raise HTTPException(status_code=409, detail="Autonomous loop is not running.")
    await state.loop.stop()
    return {"message": "Autonomous loop stopped", "cycles_completed": state.loop.status.cycle_count}


@router.get("/autonomous/status", summary="Get autonomous loop status and recent cycle history")
async def autonomous_status(request: Request):
    state = get_state(request)
    return state.loop.status.to_dict()


# ---------------------------------------------------------------------------
# City — change the operating city, reposition fleet, update loop centre
# ---------------------------------------------------------------------------

@router.post("/city", summary="Change operating city and reposition fleet")
async def set_city(request: Request, body: CityRequest):
    """
    Geocode a new city and update the autonomous loop's search centre.
    Scatters all idle carts around the new city centre so events are reachable.
    Also cancels any en-route schedules so carts start fresh in the new city.
    """
    state = get_state(request)

    # Cancel all active schedules and return carts to idle
    for schedule in state.orchestrator.get_active_schedules():
        state.orchestrator.complete_schedule(schedule.id)

    # Reposition every cart within ±3 km of the city centre
    for cart in state.fleet.carts.values():
        cart.current_location = Coordinates(
            lat=body.lat + random.uniform(-0.027, 0.027),
            lng=body.lng + random.uniform(-0.036, 0.036),
        )
        cart.go_idle()

    # Update the autonomous loop's fixed search centre
    if state.loop.status.config:
        state.loop.status.config.latitude  = body.lat
        state.loop.status.config.longitude = body.lng

    return {
        "message": f"City updated to {body.name}",
        "lat": body.lat,
        "lng": body.lng,
        "carts_repositioned": len(state.fleet.carts),
    }


# ---------------------------------------------------------------------------
# Dashboard — single endpoint for the live UI (avoids multiple round-trips)
# ---------------------------------------------------------------------------

@router.get("/dashboard", summary="All data needed by the live dashboard in one call")
async def dashboard(request: Request):
    state = get_state(request)
    fleet = state.fleet.summary()
    schedules = [s.model_dump_summary() for s in state.orchestrator.get_active_schedules()]
    loop = state.loop.status.to_dict()

    # Include idle cart positions so the map can show staging locations
    idle_carts = [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status.value,
            "lat": c.current_location.lat if c.current_location else None,
            "lng": c.current_location.lng if c.current_location else None,
        }
        for c in state.fleet.carts.values()
        if c.status.value == "idle"
    ]

    import os
    cfg = state.loop.status.config
    city = {
        "lat": cfg.latitude if cfg else None,
        "lng": cfg.longitude if cfg else None,
        "events_source": "ticketmaster" if os.getenv("TICKETMASTER_API_KEY") else "mock",
    }

    return {
        "fleet": fleet,
        "schedules": schedules,
        "loop": loop,
        "idle_carts": idle_carts,
        "city": city,
    }
