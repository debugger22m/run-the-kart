from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class CartStatus(str, Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    SERVING = "serving"
    MAINTENANCE = "maintenance"


class Coordinates(BaseModel):
    lat: float
    lng: float

    def __str__(self) -> str:
        return f"({self.lat}, {self.lng})"


class Cart(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    status: CartStatus = CartStatus.IDLE
    current_location: Optional[Coordinates] = None
    max_orders_per_hour: int = 50
    assigned_schedule_id: Optional[str] = None

    def is_available(self) -> bool:
        return self.status == CartStatus.IDLE

    def assign(self, schedule_id: str, destination: Coordinates) -> None:
        self.status = CartStatus.EN_ROUTE
        self.assigned_schedule_id = schedule_id
        self.current_location = destination

    def start_serving(self) -> None:
        self.status = CartStatus.SERVING

    def go_idle(self) -> None:
        self.status = CartStatus.IDLE
        self.assigned_schedule_id = None

    def model_dump_summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "location": str(self.current_location) if self.current_location else None,
        }
