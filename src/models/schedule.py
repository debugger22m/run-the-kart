from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
import uuid

from .cart import Coordinates


class ScheduleStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Event(BaseModel):
    id: str
    name: str
    location_name: str
    coordinates: Coordinates
    expected_attendance: int
    start_time: datetime
    end_time: datetime
    category: Optional[str] = None


class Schedule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cart_id: str
    event: Event
    arrival_time: datetime
    departure_time: datetime
    status: ScheduleStatus = ScheduleStatus.PENDING
    estimated_revenue: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def confirm(self) -> None:
        self.status = ScheduleStatus.CONFIRMED

    def start(self) -> None:
        self.status = ScheduleStatus.IN_PROGRESS

    def complete(self) -> None:
        self.status = ScheduleStatus.COMPLETED

    def cancel(self, reason: Optional[str] = None) -> None:
        self.status = ScheduleStatus.CANCELLED
        if reason:
            self.notes = reason

    def model_dump_summary(self) -> dict:
        return {
            "schedule_id": self.id,
            "cart_id": self.cart_id,
            "event_name": self.event.name,
            "location": self.event.location_name,
            "coordinates": {"lat": self.event.coordinates.lat, "lng": self.event.coordinates.lng},
            "arrival_time": self.arrival_time.isoformat(),
            "departure_time": self.departure_time.isoformat(),
            "status": self.status.value,
            "estimated_revenue": self.estimated_revenue,
        }
