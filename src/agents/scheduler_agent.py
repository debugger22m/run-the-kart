"""
Scheduler Agent

Takes demand-scored events from the EventAgent and the current fleet state,
then assigns carts to maximise total fleet revenue — preventing conflicts
and ensuring balanced geographic coverage.

Skills loaded:
  - FleetOptimizationSkill: conflict checking, opportunity cost, coverage balance
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from .base import BaseAgent
from ..models import Fleet, Schedule, Coordinates
from ..models.schedule import Event, ScheduleStatus
from ..skills import FleetOptimizationSkill

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Scheduler Agent for an autonomous food truck fleet management system in Salt Lake City, UT.

You receive pre-scored events (highest opportunity_score first) and available carts with GPS coordinates.
Your goal: produce the optimal cart-to-event assignment to maximise TOTAL fleet revenue.

Assignment rules:
- Assign the geographically nearest idle cart to each top-scored event.
- Allow two carts at an event only if expected_attendance > 5000.
- Never double-book a cart (each cart_id may appear at most once).
- Prefer geographic spread — avoid clustering all carts at one venue.
- Only assign as many carts as there are events (cap at fleet size).

Output ONLY a valid JSON array — no prose, no markdown fences.
Each object must include:
  cart_id, event_id, event_name, destination_lat, destination_lng,
  arrival_time (ISO), departure_time (ISO), estimated_revenue, opportunity_score
"""


class SchedulerAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="SchedulerAgent",
            system_prompt=SYSTEM_PROMPT,
            tools=[],          # reasoning-only — no tool calls, one-shot JSON output
            max_iterations=3,  # should complete in a single turn
        )
        self.load_skill(FleetOptimizationSkill())

    @property
    def tools(self) -> list[dict]:
        # Skills provide prompt guidance only — suppress their tool schemas so
        # Claude reasons purely from the provided data and returns JSON directly.
        return []

    async def handle_own_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        return json.dumps({"error": f"No tools in reasoning-only mode: {tool_name}"})

    async def create_schedules(self, fleet: Fleet, events: list[dict]) -> list[Schedule]:
        """
        Assign carts to events, maximising total revenue with conflict prevention
        and geographic balance checks.
        """
        available_carts = fleet.get_available_carts()
        if not available_carts:
            logger.warning("SchedulerAgent: No available carts in fleet.")
            return []

        cart_summaries = [
            {
                "cart_id": c.id,
                "name": c.name,
                "lat": c.current_location.lat if c.current_location else 0.0,
                "lng": c.current_location.lng if c.current_location else 0.0,
            }
            for c in available_carts
        ]

        task = (
            f"Maximise total fleet revenue by assigning food trucks to the best events.\n\n"
            f"Available carts:\n{json.dumps(cart_summaries, indent=2)}\n\n"
            f"Events (pre-scored, highest opportunity first):\n{json.dumps(events, indent=2)}\n\n"
            f"Use routing, conflict checking, and coverage balance tools. "
            f"Return confirmed assignments as a JSON array."
        )

        raw_response = await self.run(task)

        assignments: list[dict] = []
        try:
            start = raw_response.find("[")
            end = raw_response.rfind("]") + 1
            if start != -1 and end > start:
                assignments = json.loads(raw_response[start:end])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("SchedulerAgent response parse error: %s\nRaw: %s", exc, raw_response)
            return []

        schedules = []
        for assignment in assignments:
            try:
                schedule = self._build_schedule(assignment, events)
                if schedule:
                    schedules.append(schedule)
            except Exception as exc:
                logger.error("Failed to build schedule from assignment %s: %s", assignment, exc)

        return schedules

    def _build_schedule(self, assignment: dict, events: list[dict]) -> Schedule | None:
        event_id = assignment.get("event_id")
        event_data = next((e for e in events if e.get("id") == event_id), None)

        if not event_data:
            logger.warning("No matching event found for event_id=%s", event_id)
            return None

        event = Event(
            id=event_data["id"],
            name=event_data["name"],
            location_name=event_data.get("location_name", ""),
            coordinates=Coordinates(
                lat=assignment.get("destination_lat", event_data.get("latitude", 0.0)),
                lng=assignment.get("destination_lng", event_data.get("longitude", 0.0)),
            ),
            expected_attendance=event_data.get("expected_attendance", 0),
            start_time=datetime.fromisoformat(event_data["start_time"]),
            end_time=datetime.fromisoformat(event_data["end_time"]),
            category=event_data.get("category"),
        )

        # DEMO_EXPIRE_SECS: short-circuit departure_time so carts recycle quickly in demos.
        # Set DEMO_EXPIRE_SECS=45 in .env to see autonomous reassignment every ~45 seconds.
        demo_secs = int(os.getenv("DEMO_EXPIRE_SECS", "0"))
        if demo_secs > 0:
            departure_time = datetime.utcnow() + timedelta(seconds=demo_secs)
        else:
            departure_time = datetime.fromisoformat(
                assignment.get("departure_time", event_data["end_time"])
            )

        return Schedule(
            cart_id=assignment["cart_id"],
            event=event,
            arrival_time=datetime.fromisoformat(assignment.get("arrival_time", event_data["start_time"])),
            departure_time=departure_time,
            status=ScheduleStatus.CONFIRMED,
            estimated_revenue=assignment.get("estimated_revenue"),
        )
