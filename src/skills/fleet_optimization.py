"""
FleetOptimizationSkill — used by the SchedulerAgent.

Gives the SchedulerAgent tools to:
- Prevent double-booking (a cart can't be at two places at once)
- Ensure full coverage (highest-value events get a cart first)
- Balance load across the fleet (don't pile all carts into one area)
- Calculate the true opportunity cost of each assignment
"""

import json
from datetime import datetime
from typing import Any

from .base import Skill


class FleetOptimizationSkill(Skill):
    @property
    def name(self) -> str:
        return "fleet_optimization"

    @property
    def description(self) -> str:
        return "Maximize total fleet revenue while preventing conflicts and balancing coverage."

    @property
    def prompt_module(self) -> str:
        return """
## Fleet Optimization Skill
You have access to fleet optimization tools. Use them to:
- Call `check_assignment_conflicts` before finalizing any cart-to-event assignment
  to ensure no cart is double-booked.
- Call `calculate_opportunity_cost` to compare assignments and always pick the
  combination that maximises TOTAL fleet revenue, not just individual event revenue.
- Call `check_coverage_balance` to ensure the fleet isn't clustered in one area —
  spread carts across events in different locations where possible.
- Never assign more than one cart to the same event unless the event attendance > 3000.
- Always resolve conflicts by choosing the assignment with the higher opportunity_score.
"""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "check_assignment_conflicts",
                "description": (
                    "Check whether a proposed cart assignment conflicts with existing assignments. "
                    "Returns whether the cart is free and any conflicting schedule details."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cart_id": {"type": "string"},
                        "proposed_start": {
                            "type": "string",
                            "description": "ISO datetime string for proposed arrival",
                        },
                        "proposed_end": {
                            "type": "string",
                            "description": "ISO datetime string for proposed departure",
                        },
                        "existing_assignments": {
                            "type": "array",
                            "description": "List of already-confirmed assignments for this cart",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cart_id": {"type": "string"},
                                    "arrival_time": {"type": "string"},
                                    "departure_time": {"type": "string"},
                                    "event_name": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["cart_id", "proposed_start", "proposed_end", "existing_assignments"],
                },
            },
            {
                "name": "calculate_opportunity_cost",
                "description": (
                    "Given two competing assignments for the same cart, calculate which one "
                    "yields higher net value after accounting for travel time lost."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cart_id": {"type": "string"},
                        "option_a": {
                            "type": "object",
                            "properties": {
                                "event_id": {"type": "string"},
                                "estimated_revenue": {"type": "number"},
                                "travel_minutes": {"type": "number"},
                                "opportunity_score": {"type": "number"},
                            },
                            "required": ["event_id", "estimated_revenue", "travel_minutes", "opportunity_score"],
                        },
                        "option_b": {
                            "type": "object",
                            "properties": {
                                "event_id": {"type": "string"},
                                "estimated_revenue": {"type": "number"},
                                "travel_minutes": {"type": "number"},
                                "opportunity_score": {"type": "number"},
                            },
                            "required": ["event_id", "estimated_revenue", "travel_minutes", "opportunity_score"],
                        },
                    },
                    "required": ["cart_id", "option_a", "option_b"],
                },
            },
            {
                "name": "check_coverage_balance",
                "description": (
                    "Given a proposed set of assignments, check whether the fleet is spread "
                    "across the operating area or clustered. Returns a balance score and recommendations."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "assignments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cart_id": {"type": "string"},
                                    "event_id": {"type": "string"},
                                    "latitude": {"type": "number"},
                                    "longitude": {"type": "number"},
                                    "estimated_revenue": {"type": "number"},
                                },
                                "required": ["cart_id", "event_id", "latitude", "longitude"],
                            },
                        },
                    },
                    "required": ["assignments"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        handlers = {
            "check_assignment_conflicts": self._check_conflicts,
            "calculate_opportunity_cost": self._opportunity_cost,
            "check_coverage_balance": self._coverage_balance,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            return json.dumps(handler(**tool_input), default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # Implementations
    # ------------------------------------------------------------------

    def _check_conflicts(
        self,
        cart_id: str,
        proposed_start: str,
        proposed_end: str,
        existing_assignments: list[dict],
    ) -> dict:
        p_start = datetime.fromisoformat(proposed_start)
        p_end = datetime.fromisoformat(proposed_end)

        conflicts = []
        for a in existing_assignments:
            if a.get("cart_id") != cart_id:
                continue
            a_start = datetime.fromisoformat(a["arrival_time"])
            a_end = datetime.fromisoformat(a["departure_time"])
            # Overlap check
            if p_start < a_end and p_end > a_start:
                conflicts.append({
                    "conflicting_event": a.get("event_name"),
                    "conflict_start": a["arrival_time"],
                    "conflict_end": a["departure_time"],
                })

        return {
            "cart_id": cart_id,
            "is_free": len(conflicts) == 0,
            "conflicts": conflicts,
        }

    def _opportunity_cost(self, cart_id: str, option_a: dict, option_b: dict) -> dict:
        # Travel penalty: each minute of travel = ~$0.50 opportunity cost
        travel_penalty_per_min = 0.50

        net_a = option_a["estimated_revenue"] - (option_a["travel_minutes"] * travel_penalty_per_min)
        net_b = option_b["estimated_revenue"] - (option_b["travel_minutes"] * travel_penalty_per_min)

        # Weight by opportunity score (0-100)
        weighted_a = net_a * (option_a["opportunity_score"] / 100)
        weighted_b = net_b * (option_b["opportunity_score"] / 100)

        winner = "option_a" if weighted_a >= weighted_b else "option_b"
        return {
            "cart_id": cart_id,
            "recommended": winner,
            "option_a": {"event_id": option_a["event_id"], "net_value": round(net_a, 2), "weighted_value": round(weighted_a, 2)},
            "option_b": {"event_id": option_b["event_id"], "net_value": round(net_b, 2), "weighted_value": round(weighted_b, 2)},
        }

    def _coverage_balance(self, assignments: list[dict]) -> dict:
        if len(assignments) < 2:
            return {"balance_score": 100, "recommendation": "Only one assignment — no balance check needed."}

        lats = [a["latitude"] for a in assignments]
        lngs = [a["longitude"] for a in assignments]

        lat_spread = max(lats) - min(lats)
        lng_spread = max(lngs) - min(lngs)

        # Spread in degrees: > 0.05 (~5km) is reasonable coverage
        spread_score = min(100, round((lat_spread + lng_spread) / 0.1 * 100))
        total_revenue = sum(a.get("estimated_revenue", 0) for a in assignments)

        recommendation = (
            "Good geographic spread across the fleet."
            if spread_score >= 50
            else "Carts are clustered — consider reassigning one cart to a more distant event."
        )

        return {
            "balance_score": spread_score,
            "lat_spread_deg": round(lat_spread, 4),
            "lng_spread_deg": round(lng_spread, 4),
            "total_estimated_revenue": round(total_revenue, 2),
            "recommendation": recommendation,
        }
