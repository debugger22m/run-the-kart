"""
DemandForecastingSkill — used by the EventAgent.

Gives the EventAgent tools to score each event's revenue opportunity
based on attendance, event type, time of day, and duration.
The agent uses these scores to rank events before passing them to the Scheduler.
"""

import json
import math
from typing import Any

from .base import Skill


class DemandForecastingSkill(Skill):
    @property
    def name(self) -> str:
        return "demand_forecasting"

    @property
    def description(self) -> str:
        return "Score and rank events by food truck revenue potential."

    @property
    def prompt_module(self) -> str:
        return """
## Demand Forecasting Skill
You have access to demand forecasting tools. Use them to:
- Call `forecast_demand` for every event you discover to get a revenue score.
- Call `score_event_opportunity` to combine demand with practical factors (duration, time of day).
- Only pass events with an opportunity_score >= 40 to the final ranked list.
- Always sort your final answer by opportunity_score descending so the Scheduler
  picks the highest-value events first.
"""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "forecast_demand",
                "description": (
                    "Forecast food truck customer demand for an event based on its type and attendance. "
                    "Returns estimated customers, average order value, and a raw demand score (0-100)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "event_category": {
                            "type": "string",
                            "description": "Event type: market, conference, music, food, sports, festival, etc.",
                        },
                        "expected_attendance": {"type": "integer"},
                        "duration_hours": {
                            "type": "number",
                            "description": "How long the event runs in hours",
                        },
                    },
                    "required": ["event_id", "event_category", "expected_attendance", "duration_hours"],
                },
            },
            {
                "name": "score_event_opportunity",
                "description": (
                    "Combine raw demand with time-of-day and event duration to produce a final "
                    "opportunity score (0-100). Higher is better for deployment."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "demand_score": {"type": "number", "description": "Raw demand score from forecast_demand"},
                        "start_hour": {
                            "type": "integer",
                            "description": "Hour of day the event starts (0-23, UTC)",
                        },
                        "duration_hours": {"type": "number"},
                        "estimated_revenue": {"type": "number", "description": "High-end revenue estimate in USD"},
                    },
                    "required": ["event_id", "demand_score", "start_hour", "duration_hours", "estimated_revenue"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        handlers = {
            "forecast_demand": self._forecast_demand,
            "score_event_opportunity": self._score_event_opportunity,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            return json.dumps(handler(**tool_input), default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Mock implementations — replace with ML model / historical data
    # ------------------------------------------------------------------

    # Conversion rates and average order values by event category
    _CATEGORY_PROFILE = {
        "music":      {"conversion": 0.12, "avg_order": 14.0},
        "conference": {"conversion": 0.09, "avg_order": 16.0},
        "market":     {"conversion": 0.14, "avg_order": 11.0},
        "food":       {"conversion": 0.08, "avg_order": 13.0},
        "festival":   {"conversion": 0.15, "avg_order": 12.0},
        "sports":     {"conversion": 0.10, "avg_order": 10.0},
    }
    _DEFAULT_PROFILE = {"conversion": 0.08, "avg_order": 11.0}

    def _forecast_demand(
        self, event_id: str, event_category: str, expected_attendance: int, duration_hours: float
    ) -> dict:
        profile = self._CATEGORY_PROFILE.get(event_category.lower(), self._DEFAULT_PROFILE)
        estimated_customers = int(expected_attendance * profile["conversion"])
        estimated_revenue = round(estimated_customers * profile["avg_order"], 2)

        # Demand score: scale 0-100 based on customers per hour
        customers_per_hour = estimated_customers / max(duration_hours, 1)
        demand_score = min(100, round(customers_per_hour * 2, 1))

        return {
            "event_id": event_id,
            "estimated_customers": estimated_customers,
            "avg_order_value": profile["avg_order"],
            "estimated_revenue": estimated_revenue,
            "demand_score": demand_score,
        }

    def _score_event_opportunity(
        self,
        event_id: str,
        demand_score: float,
        start_hour: int,
        duration_hours: float,
        estimated_revenue: float,
    ) -> dict:
        # Peak meal hours (11-14, 17-21) get a bonus
        if 11 <= start_hour <= 14 or 17 <= start_hour <= 21:
            time_bonus = 15
        elif 9 <= start_hour <= 16:
            time_bonus = 5
        else:
            time_bonus = -10  # late night / early morning penalty

        # Longer events give more serving time (capped at 6h bonus)
        duration_bonus = min(10, (duration_hours - 2) * 2) if duration_hours > 2 else 0

        # Revenue floor bonus — high revenue events get a small push
        revenue_bonus = min(10, math.log10(max(estimated_revenue, 1)) * 2)

        opportunity_score = round(
            min(100, max(0, demand_score + time_bonus + duration_bonus + revenue_bonus)), 1
        )

        return {
            "event_id": event_id,
            "opportunity_score": opportunity_score,
            "breakdown": {
                "demand_score": demand_score,
                "time_bonus": time_bonus,
                "duration_bonus": duration_bonus,
                "revenue_bonus": round(revenue_bonus, 1),
            },
        }
