"""
Event Agent

Responsible for discovering high-value local events near the fleet's operating area
and returning structured event data for the SchedulerAgent to act on.
"""

import json
import logging
from typing import Any

from .base import BaseAgent
from ..tools.event_tools import EVENT_TOOLS, handle_event_tool_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Event Agent for an autonomous food truck fleet management system.

Your sole responsibility is to:
1. Call get_events_for_today to fetch all events happening today near the given location.
2. Call estimate_foot_traffic for each event to determine revenue potential.
3. Rank events by estimated_revenue_high (highest first).
4. Return a ranked list of the top events so the Scheduler can assign carts.

Always use get_events_for_today as your first tool call.
Return your final answer as a valid JSON array of event objects. Each object must include:
  - id, name, location_name, latitude, longitude, expected_attendance,
    start_time, end_time, category, estimated_customers, estimated_revenue_high

Do not include events with fewer than 200 expected attendees.
"""


class EventAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="EventAgent",
            system_prompt=SYSTEM_PROMPT,
            tools=EVENT_TOOLS,
        )

    async def handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        return handle_event_tool_call(tool_name, tool_input)

    async def find_events(
        self,
        latitude: float,
        longitude: float,
        date_from: str,
        date_to: str,
        radius_km: float = 10.0,
    ) -> list[dict]:
        """
        High-level method: discover and rank events near a location.

        Returns a list of event dicts sorted by revenue potential.
        """
        task = (
            f"Find and rank the best upcoming events near coordinates "
            f"({latitude}, {longitude}) within {radius_km} km, "
            f"between {date_from} and {date_to}. "
            f"Estimate foot traffic and revenue for each event. "
            f"Return the top events as a JSON array."
        )
        raw_response = await self.run(task)

        try:
            # Claude should return a JSON array; extract it from the response
            start = raw_response.find("[")
            end = raw_response.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(raw_response[start:end])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("EventAgent response parse error: %s\nRaw: %s", exc, raw_response)

        return []
