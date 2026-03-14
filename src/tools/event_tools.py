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
        "name": "get_events_for_today",
        "description": (
            "Get all events happening today near a given location. "
            "Returns events sorted by start time with attendance and category information. "
            "Use this as the primary tool to discover where to deploy food trucks today."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude of the operating area"},
                "longitude": {"type": "number", "description": "Longitude of the operating area"},
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in kilometres (default 10)",
                    "default": 10,
                },
                "min_attendance": {
                    "type": "integer",
                    "description": "Minimum expected attendance to include an event (default 200)",
                    "default": 200,
                },
            },
            "required": ["latitude", "longitude"],
        },
    },
    {
        "name": "search_local_events",
        "description": (
            "Search for upcoming local events near a given location across a custom date range. "
            "Use get_events_for_today instead if you only need today's events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Latitude of the search centre"},
                "longitude": {"type": "number", "description": "Longitude of the search centre"},
                "radius_km": {"type": "number", "description": "Search radius in kilometres", "default": 10},
                "date_from": {"type": "string", "description": "ISO date string (e.g. 2026-03-14)"},
                "date_to": {"type": "string", "description": "ISO date string (e.g. 2026-03-15)"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional event category filter",
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
            "Estimate the foot traffic and revenue potential at an event given its attendance. "
            "Returns estimated customer count and revenue range for a food truck."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "expected_attendance": {"type": "integer"},
            },
            "required": ["event_id", "expected_attendance"],
        },
    },
]

# ---------------------------------------------------------------------------
# Mock data — timestamps are always relative to now so they stay valid
# ---------------------------------------------------------------------------

def _build_mock_events() -> list[dict]:
    """Generate mock events anchored to the current time."""
    now = datetime.utcnow()
    return [
        {
            "id": "evt_001",
            "name": "Downtown Farmers Market",
            "location_name": "Central Plaza",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "expected_attendance": 1200,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=5)).isoformat(),
            "category": "market",
            "description": "Weekly outdoor farmers market with 80+ vendors.",
        },
        {
            "id": "evt_002",
            "name": "Tech Conference 2026",
            "location_name": "Convention Centre",
            "latitude": 37.7845,
            "longitude": -122.4080,
            "expected_attendance": 3500,
            "start_time": (now + timedelta(minutes=30)).isoformat(),
            "end_time": (now + timedelta(hours=8)).isoformat(),
            "category": "conference",
            "description": "Annual technology summit with 3500 attendees.",
        },
        {
            "id": "evt_003",
            "name": "Golden Gate Park Concert",
            "location_name": "Golden Gate Park Bandshell",
            "latitude": 37.7694,
            "longitude": -122.4862,
            "expected_attendance": 5000,
            "start_time": (now + timedelta(hours=3)).isoformat(),
            "end_time": (now + timedelta(hours=7)).isoformat(),
            "category": "music",
            "description": "Free outdoor concert series in the park.",
        },
        {
            "id": "evt_004",
            "name": "Mission Street Food Festival",
            "location_name": "Mission District",
            "latitude": 37.7599,
            "longitude": -122.4148,
            "expected_attendance": 800,
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=6)).isoformat(),
            "category": "food",
            "description": "Neighbourhood street food festival.",
        },
        {
            "id": "evt_005",
            "name": "SoMa Night Market",
            "location_name": "SoMa District",
            "latitude": 37.7786,
            "longitude": -122.4058,
            "expected_attendance": 2200,
            "start_time": (now + timedelta(hours=4)).isoformat(),
            "end_time": (now + timedelta(hours=9)).isoformat(),
            "category": "market",
            "description": "Evening market with art, food, and live music.",
        },
    ]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _get_events_for_today(
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    min_attendance: int = 200,
) -> dict:
    """Return today's events above the minimum attendance threshold."""
    events = _build_mock_events()
    filtered = [e for e in events if e["expected_attendance"] >= min_attendance]
    filtered.sort(key=lambda e: e["start_time"])
    return {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "centre": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "events": filtered,
        "total": len(filtered),
    }


def _search_local_events(
    latitude: float,
    longitude: float,
    date_from: str,
    date_to: str,
    radius_km: float = 10.0,
    categories: list[str] | None = None,
) -> dict:
    events = _build_mock_events()
    if categories:
        events = [e for e in events if e.get("category") in categories]
    return {"events": events, "total": len(events)}


def _get_event_details(event_id: str) -> dict:
    event = next((e for e in _build_mock_events() if e["id"] == event_id), None)
    if not event:
        return {"error": f"Event {event_id} not found"}
    return event


def _estimate_foot_traffic(event_id: str, expected_attendance: int) -> dict:
    conversion_rate = random.uniform(0.05, 0.15)
    avg_order_value = random.uniform(8.0, 18.0)
    estimated_customers = int(expected_attendance * conversion_rate)
    estimated_revenue_low = round(estimated_customers * avg_order_value * 0.8, 2)
    estimated_revenue_high = round(estimated_customers * avg_order_value * 1.2, 2)
    return {
        "event_id": event_id,
        "estimated_customers": estimated_customers,
        "estimated_revenue_low": estimated_revenue_low,
        "estimated_revenue_high": estimated_revenue_high,
        "confidence": "medium",
    }


def handle_event_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    handlers = {
        "get_events_for_today": lambda i: _get_events_for_today(**i),
        "search_local_events": lambda i: _search_local_events(**i),
        "get_event_details": lambda i: _get_event_details(**i),
        "estimate_foot_traffic": lambda i: _estimate_foot_traffic(**i),
    }
    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        return json.dumps(handler(tool_input), default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
