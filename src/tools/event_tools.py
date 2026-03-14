"""
Event discovery tools for the EventAgent.

Each tool is defined as an Anthropic-compatible tool schema plus a handler function.
Replace the mock implementations with real API calls (Eventbrite, Ticketmaster, etc.)
"""

import json
import random
from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------

EVENT_TOOLS = [
    {
        "name": "search_local_events",
        "description": (
            "Search for upcoming local events near a given location. "
            "Returns a list of events with name, location, expected attendance, and time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude of the search centre"},
                "longitude": {"type": "number", "description": "Longitude of the search centre"},
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometres",
                    "default": 10,
                },
                "date_from": {
                    "type": "string",
                    "description": "ISO date string for start of search window (e.g. 2026-03-14)",
                },
                "date_to": {
                    "type": "string",
                    "description": "ISO date string for end of search window (e.g. 2026-03-15)",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of event categories to filter by",
                },
            },
            "required": ["latitude", "longitude", "date_from", "date_to"],
        },
    },
    {
        "name": "get_event_details",
        "description": "Get detailed information about a specific event by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The unique event identifier"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "estimate_foot_traffic",
        "description": (
            "Estimate the foot traffic and revenue potential at an event. "
            "Returns an estimated number of customers and revenue range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event identifier"},
                "expected_attendance": {
                    "type": "integer",
                    "description": "Expected number of attendees at the event",
                },
            },
            "required": ["event_id", "expected_attendance"],
        },
    },
]

# ---------------------------------------------------------------------------
# Mock handlers — replace with real API integrations
# ---------------------------------------------------------------------------

_MOCK_EVENTS = [
    {
        "id": "evt_001",
        "name": "Downtown Farmers Market",
        "location_name": "Central Plaza",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "expected_attendance": 1200,
        "start_time": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        "end_time": (datetime.utcnow() + timedelta(hours=6)).isoformat(),
        "category": "market",
    },
    {
        "id": "evt_002",
        "name": "Tech Conference 2026",
        "location_name": "Convention Centre",
        "latitude": 37.7845,
        "longitude": -122.4080,
        "expected_attendance": 3500,
        "start_time": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        "end_time": (datetime.utcnow() + timedelta(hours=9)).isoformat(),
        "category": "conference",
    },
    {
        "id": "evt_003",
        "name": "Golden Gate Park Concert",
        "location_name": "Golden Gate Park Bandshell",
        "latitude": 37.7694,
        "longitude": -122.4862,
        "expected_attendance": 5000,
        "start_time": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
        "end_time": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
        "category": "music",
    },
    {
        "id": "evt_004",
        "name": "Sunday Street Food Festival",
        "location_name": "Mission District",
        "latitude": 37.7599,
        "longitude": -122.4148,
        "expected_attendance": 800,
        "start_time": (datetime.utcnow() + timedelta(hours=3)).isoformat(),
        "end_time": (datetime.utcnow() + timedelta(hours=7)).isoformat(),
        "category": "food",
    },
]


def _search_local_events(
    latitude: float,
    longitude: float,
    date_from: str,
    date_to: str,
    radius_km: float = 10.0,
    categories: list[str] | None = None,
) -> dict:
    """Mock implementation — replace with Eventbrite / Ticketmaster API call."""
    events = _MOCK_EVENTS
    if categories:
        events = [e for e in events if e.get("category") in categories]
    return {"events": events, "total": len(events)}


def _get_event_details(event_id: str) -> dict:
    """Mock implementation — replace with real event detail lookup."""
    event = next((e for e in _MOCK_EVENTS if e["id"] == event_id), None)
    if not event:
        return {"error": f"Event {event_id} not found"}
    return event


def _estimate_foot_traffic(event_id: str, expected_attendance: int) -> dict:
    """Mock implementation — replace with ML model or historical data lookup."""
    conversion_rate = random.uniform(0.05, 0.15)
    avg_order_value = random.uniform(8.0, 18.0)
    estimated_customers = int(expected_attendance * conversion_rate)
    estimated_revenue_low = estimated_customers * avg_order_value * 0.8
    estimated_revenue_high = estimated_customers * avg_order_value * 1.2

    return {
        "event_id": event_id,
        "estimated_customers": estimated_customers,
        "estimated_revenue_low": round(estimated_revenue_low, 2),
        "estimated_revenue_high": round(estimated_revenue_high, 2),
        "confidence": "medium",
    }


def handle_event_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Route a Claude tool_use call to the correct handler and return a JSON string."""
    handlers = {
        "search_local_events": lambda i: _search_local_events(**i),
        "get_event_details": lambda i: _get_event_details(**i),
        "estimate_foot_traffic": lambda i: _estimate_foot_traffic(**i),
    }
    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = handler(tool_input)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
