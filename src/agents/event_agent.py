"""
Event Agent

Discovers high-value local events near the fleet's operating area and returns
structured, demand-scored event data for the SchedulerAgent to act on.

Skills loaded:
  - DemandForecastingSkill: scores each event by revenue opportunity before ranking
"""

import json
import logging
from typing import Any

from .base import BaseAgent
from ..tools.event_tools import EVENT_TOOLS, handle_event_tool_call
from ..skills import DemandForecastingSkill

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Event Agent for an autonomous food truck fleet management system.

Your job is to find today's best events for food truck deployment and score them
so the Scheduler Agent can make the highest-revenue assignments possible.

Step-by-step process:
1. Call get_events_for_today to fetch all events happening today near the given location.
2. For each event, call forecast_demand (using the event category, attendance, and duration).
3. For each event, call score_event_opportunity using the demand score, start hour, and revenue.
4. Only keep events with opportunity_score >= 40.
5. Return the final list sorted by opportunity_score descending.

Return your final answer as a valid JSON array. Each object must include:
  - id, name, location_name, latitude, longitude, expected_attendance,
    start_time, end_time, category, estimated_customers, estimated_revenue_high,
    demand_score, opportunity_score

Do not include events with fewer than 200 expected attendees.
"""


class EventAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="EventAgent",
            system_prompt=SYSTEM_PROMPT,
            tools=EVENT_TOOLS,
        )
        self.load_skill(DemandForecastingSkill())

    async def handle_own_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
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
        Discover, score, and rank today's events near a location.
        Returns events sorted by opportunity_score descending.
        """
        task = (
            f"Find and score today's best events for food truck deployment near "
            f"({latitude}, {longitude}) within {radius_km} km. "
            f"Use demand forecasting to score each event and return only high-opportunity events "
            f"as a JSON array sorted by opportunity_score descending."
        )
        raw_response = await self.run(task)

        try:
            start = raw_response.find("[")
            end = raw_response.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(raw_response[start:end])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("EventAgent response parse error: %s\nRaw: %s", exc, raw_response)

        return []
