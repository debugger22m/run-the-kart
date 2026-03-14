"""
Event Agent

Responsible for discovering high-value local events near the fleet's operating area
and returning structured event data for the SchedulerAgent to act on.
"""

import json
import logging

from claude_agent_sdk import query, ClaudeAgentOptions

from ..tools.event_tools import EVENT_MCP_SERVER

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the Event Agent for an autonomous food truck fleet management system.

Your sole responsibility is to:
1. Search for upcoming local events in the given area and date window.
2. Retrieve detailed information about the most promising events.
3. Estimate the foot traffic and revenue potential for each event.
4. Return a ranked list of the top events (highest revenue potential first).

Always use the available tools to gather data before responding.
Return your final answer as a valid JSON array of event objects. Each object must include:
  - id, name, location_name, latitude, longitude, expected_attendance,
    start_time, end_time, category, estimated_customers, estimated_revenue_high

Do not include events that are already over or have very low attendance (< 200 people).
"""


class EventAgent:
    async def find_events(
        self,
        latitude: float,
        longitude: float,
        date_from: str,
        date_to: str,
        radius_km: float = 10.0,
    ) -> list[dict]:
        """Discover and rank events near a location using the Agent SDK."""
        prompt = (
            f"Find and rank the best upcoming events near coordinates "
            f"({latitude}, {longitude}) within {radius_km} km, "
            f"between {date_from} and {date_to}. "
            f"Estimate foot traffic and revenue for each event. "
            f"Return the top events as a JSON array."
        )

        result_text = ""
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=SYSTEM_PROMPT,
                model="claude-opus-4-6",
                permission_mode="bypassPermissions",
                mcp_servers={"event-tools": EVENT_MCP_SERVER},
                max_turns=10,
            ),
        ):
            if message.type == "result":
                result_text = message.result

        try:
            start = result_text.find("[")
            end = result_text.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(result_text[start:end])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("EventAgent response parse error: %s\nRaw: %s", exc, result_text)

        return []
