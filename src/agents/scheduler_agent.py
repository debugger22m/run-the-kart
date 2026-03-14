"""
Scheduler Agent

Takes a list of events and the current fleet state, then assigns the best available
cart to each high-value event, producing a list of Schedule objects.
"""

import json
import logging
from datetime import datetime

from claude_agent_sdk import query, ClaudeAgentOptions

from ..tools.maps_tools import MAPS_MCP_SERVER
from ..models import Fleet, Schedule, Coordinates
from ..models.schedule import Event, ScheduleStatus

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Scheduler Agent for an autonomous food truck fleet management system.

You will receive:
- A list of upcoming events (with coordinates, attendance, revenue estimates).
- A list of available food trucks (carts) with their current coordinates.

Your job is to:
1. Use the routing tools to find the nearest available cart for each event.
2. Check parking availability at each event location.
3. Assign carts to events, maximising total estimated revenue.
4. Avoid assigning the same cart to overlapping time windows.

Return your final answer as a valid JSON array of schedule assignment objects. Each must include:
  - cart_id, event_id, event_name, destination_lat, destination_lng,
    arrival_time (ISO), departure_time (ISO), estimated_revenue

Prioritise events by estimated revenue (highest first). If no carts are available, say so.
"""


class SchedulerAgent:
    async def create_schedules(self, fleet: Fleet, events: list[dict]) -> list[Schedule]:
        """Given a fleet and a list of events, produce Schedule objects via the Agent SDK."""
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

        prompt = (
            f"Assign food trucks to events to maximise revenue.\n\n"
            f"Available carts:\n{json.dumps(cart_summaries, indent=2)}\n\n"
            f"Events to cover:\n{json.dumps(events, indent=2)}\n\n"
            f"Use tools to calculate routes, find nearest carts, and check parking. "
            f"Return a JSON array of schedule assignments."
        )

        result_text = ""
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=SYSTEM_PROMPT,
                model="claude-opus-4-6",
                permission_mode="bypassPermissions",
                mcp_servers={"maps-tools": MAPS_MCP_SERVER},
                max_turns=15,
            ),
        ):
            if message.type == "result":
                result_text = message.result

        assignments: list[dict] = []
        try:
            start = result_text.find("[")
            end = result_text.rfind("]") + 1
            if start != -1 and end > start:
                assignments = json.loads(result_text[start:end])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("SchedulerAgent response parse error: %s\nRaw: %s", exc, result_text)
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
        """Convert a raw LLM assignment dict into a typed Schedule object."""
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

        arrival_str = assignment.get("arrival_time", event_data["start_time"])
        departure_str = assignment.get("departure_time", event_data["end_time"])

        return Schedule(
            cart_id=assignment["cart_id"],
            event=event,
            arrival_time=datetime.fromisoformat(arrival_str),
            departure_time=datetime.fromisoformat(departure_str),
            status=ScheduleStatus.CONFIRMED,
            estimated_revenue=assignment.get("estimated_revenue"),
        )
