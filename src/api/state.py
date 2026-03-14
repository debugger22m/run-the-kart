"""
Shared application state (fleet, orchestrator) — lives for the lifetime of the server.
"""

import os

from ..models import Cart, Coordinates, Fleet
from ..models.cart import CartStatus
from ..agents import OrchestratorAgent
from .loop import AutonomousLoop

# Downtown Salt Lake City staging locations
_DEMO_CARTS = [
    ("Kart-Pioneer",   40.7580, -111.9012),  # Pioneer Park
    ("Kart-Gallivan",  40.7611, -111.8906),  # Gallivan Center
    ("Kart-Gateway",   40.7694, -111.9018),  # The Gateway
    ("Kart-Temple",    40.7708, -111.8958),  # Temple Square
    ("Kart-Delta",     40.7683, -111.9012),  # Delta Center area
]


class AppState:
    def __init__(self) -> None:
        fleet_name = os.getenv("DEFAULT_FLEET_NAME", "SLC-KartFleet")
        self.fleet = Fleet(name=fleet_name)

        for name, lat, lng in _DEMO_CARTS:
            self.fleet.add_cart(Cart(
                name=name,
                status=CartStatus.IDLE,
                current_location=Coordinates(lat=lat, lng=lng),
            ))

        self.orchestrator = OrchestratorAgent(self.fleet)
        self.loop = AutonomousLoop(self.orchestrator)
