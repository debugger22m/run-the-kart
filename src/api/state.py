"""
Shared application state — lives for the lifetime of the server.

On startup, the fleet is loaded from the Supabase `carts` table.
If the DB returns zero carts (e.g. first run before seed migration),
the demo carts are inserted so the API is immediately usable.
"""

import logging
import os
from typing import TYPE_CHECKING

from ..models import Cart, Coordinates, Fleet
from ..models.cart import CartStatus
from ..agents import OrchestratorAgent
from .loop import AutonomousLoop

if TYPE_CHECKING:
    from supabase import AsyncClient

logger = logging.getLogger(__name__)

_DEFAULT_FLEET_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

# 10 carts spread across Downtown SLC staging zones (fallback if DB is empty)
_DEMO_CARTS = [
    ("Kart-Pioneer",    40.7580, -111.9012),  # Pioneer Park
    ("Kart-Gallivan",   40.7611, -111.8906),  # Gallivan Center
    ("Kart-Gateway",    40.7694, -111.9018),  # The Gateway
    ("Kart-Temple",     40.7708, -111.8958),  # Temple Square
    ("Kart-Delta",      40.7683, -111.9012),  # Delta Center
    ("Kart-Library",    40.7607, -111.8912),  # Salt Lake City Library
    ("Kart-CityCreek",  40.7683, -111.8945),  # City Creek Center
    ("Kart-Trolley",    40.7497, -111.8780),  # Trolley Square
    ("Kart-RiceEccles", 40.7596, -111.8486),  # Rice-Eccles Stadium
    ("Kart-SugarHouse", 40.7239, -111.8583),  # Sugar House Park
]


class AppState:
    def __init__(
        self,
        fleet: Fleet,
        orchestrator: OrchestratorAgent,
        loop: AutonomousLoop,
        fleet_repo,
        schedule_repo,
        event_cache_repo,
        orchestration_repo,
    ) -> None:
        self.fleet = fleet
        self.orchestrator = orchestrator
        self.loop = loop
        self.fleet_repo = fleet_repo
        self.schedule_repo = schedule_repo
        self.event_cache_repo = event_cache_repo
        self.orchestration_repo = orchestration_repo

    @classmethod
    async def create(cls, supabase: "AsyncClient") -> "AppState":
        """Async factory: initialise state by loading fleet data from Supabase."""
        from ..db import (
            FleetRepository,
            ScheduleRepository,
            EventCacheRepository,
            OrchestrationRepository,
        )

        fleet_name = os.getenv("DEFAULT_FLEET_NAME", "SLC-KartFleet")
        fleet_id = os.getenv("DEFAULT_FLEET_ID", _DEFAULT_FLEET_ID)

        fleet_repo = FleetRepository(supabase)
        schedule_repo = ScheduleRepository(supabase)
        event_cache_repo = EventCacheRepository(supabase)
        orchestration_repo = OrchestrationRepository(supabase, fleet_id)

        fleet = Fleet(id=fleet_id, name=fleet_name)
        carts = await fleet_repo.load_all_carts(fleet_id)

        if carts:
            for cart in carts:
                fleet.add_cart(cart)
            logger.info("AppState: loaded %d cart(s) from DB.", len(carts))
        else:
            # First run before seed migration — bootstrap demo carts
            logger.info("AppState: no carts found in DB, seeding %d demo cart(s).", len(_DEMO_CARTS))
            for name, lat, lng in _DEMO_CARTS:
                cart = Cart(
                    name=name,
                    status=CartStatus.IDLE,
                    current_location=Coordinates(lat=lat, lng=lng),
                )
                fleet.add_cart(cart)
                await fleet_repo.insert_cart(cart, fleet_id)

        orchestrator = OrchestratorAgent(
            fleet,
            schedule_repo=schedule_repo,
            orchestration_repo=orchestration_repo,
            event_cache_repo=event_cache_repo,
        )
        loop = AutonomousLoop(orchestrator)

        return cls(fleet, orchestrator, loop, fleet_repo, schedule_repo, event_cache_repo, orchestration_repo)
