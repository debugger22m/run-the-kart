"""
Event Agent

Discovers high-value local events near the fleet's operating area using web search
and returns demand-scored event data for the SchedulerAgent to act on.

Skills loaded:
  - DemandForecastingSkill: scores each event by revenue opportunity before ranking
"""

import json
import logging
from typing import Any

from .base import BaseAgent
from ..tools.event_tools import EVENT_TOOLS
from ..skills import DemandForecastingSkill

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a revenue-maximisation scout for an autonomous food truck fleet. Your single
goal is to identify the highest-revenue deployment opportunities for today and return
them as machine-readable JSON so the scheduling system can act immediately.

## Step 1 — Discover events via web search

Search for real events happening today near the target coordinates. Try 2-3 searches
covering different event types, for example:
- "[date] events today [city/neighbourhood]"
- "concerts festivals [date] [city]"
- "farmers markets sports games [date] [city]"

Extract every event you find: name, venue, start/end time, category, estimated attendance.

## Step 2 — Geocode venues

Assign latitude and longitude to each event. Use your knowledge of well-known venues.
Common SF reference points:
- Chase Center: 37.7680, -122.3877
- Oracle Park: 37.7786, -122.3893
- Golden Gate Park: 37.7694, -122.4862
- Moscone Center: 37.7845, -122.4008
- Ferry Building: 37.7956, -122.3933
- Civic Center / Market St: 37.7793, -122.4193
- Bill Graham Civic Auditorium: 37.7784, -122.4177
- The Fillmore: 37.7840, -122.4330
- Pier 39 / Fisherman's Wharf: 37.8087, -122.4098
- Union Square: 37.7879, -122.4074
- Yerba Buena Center: 37.7845, -122.4025
- Castro Theatre: 37.7620, -122.4350

No null coordinates are permitted. If you cannot determine coordinates, exclude the event.

## Step 3 — Estimate attendance

Attendance is rarely stated directly. Estimate using:
- Venue capacity (e.g., 20,000-seat arena at 80% = 16,000)
- Event type baselines: farmers market 500-2,000; street fair 2,000-10,000;
  major concert 5,000-50,000; conference 500-5,000; parade 10,000-100,000
- Historical data for recurring events
- Any ticket counts or registration numbers mentioned

Never leave attendance as null or 0. Always make your best informed estimate.
Discard events with expected_attendance < 200.

## Step 4 — Score each event

For every event:
1. Call `forecast_demand` (event_id, event_category, expected_attendance, duration_hours)
2. Call `score_event_opportunity` (event_id, demand_score, start_hour, duration_hours, estimated_revenue)
3. Discard events with opportunity_score < 40.

## Step 5 — Return results

Return ONLY a JSON array sorted by opportunity_score descending.
No markdown fences, no text before or after the array. Each element must have exactly:
{
  "id": "evt_001",
  "name": "Event Name",
  "location_name": "Venue Name",
  "latitude": 37.7786,
  "longitude": -122.3893,
  "expected_attendance": 8000,
  "start_time": "2026-03-14T12:00:00-07:00",
  "end_time": "2026-03-14T16:00:00-07:00",
  "category": "sports",
  "estimated_customers": 800,
  "estimated_revenue_high": 8000.0,
  "demand_score": 100.0,
  "opportunity_score": 100.0
}
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
        # web_search is server-side; no client-handled event tools remain
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    async def find_events(
        self,
        latitude: float,
        longitude: float,
        date_from: str,
        date_to: str,
        radius_km: float = 10.0,
    ) -> list[dict]:
        """
        Discover, score, and rank today's events near a location via web search.
        Returns events sorted by opportunity_score descending.
        """
        task = (
            f"Find and score today's best events for food truck deployment near "
            f"({latitude}, {longitude}) within {radius_km} km. "
            f"Today is {date_from}."
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
