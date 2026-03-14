"""
Shared application state (fleet, orchestrator) — lives for the lifetime of the server.
"""

import os

from ..models import Cart, Coordinates, Fleet
from ..models.cart import CartStatus
from ..agents import OrchestratorAgent


class AppState:
    def __init__(self) -> None:
        fleet_name = os.getenv("DEFAULT_FLEET_NAME", "KartFleet")
        self.fleet = Fleet(name=fleet_name)

        # Seed the fleet with a couple of demo carts so the API is usable out-of-the-box.
        demo_carts = [
            Cart(
                name="Kart-Alpha",
                status=CartStatus.IDLE,
                current_location=Coordinates(lat=37.7749, lng=-122.4194),
            ),
            Cart(
                name="Kart-Beta",
                status=CartStatus.IDLE,
                current_location=Coordinates(lat=37.7845, lng=-122.4080),
            ),
        ]
        for cart in demo_carts:
            self.fleet.add_cart(cart)

        self.orchestrator = OrchestratorAgent(self.fleet)
