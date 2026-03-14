"""
Event discovery tools for the EventAgent.

Replace the mock implementations with real API calls (Eventbrite, Ticketmaster, etc.)
"""

import json
import random
from datetime import datetime, timedelta

from claude_agent_sdk import tool, create_sdk_mcp_server

# ---------------------------------------------------------------------------
# Mock data — replace with real API integrations
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

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "latitude": {"type": "number", "description": "Latitude of the search centre"},
        "longitude": {"type": "number", "description": "Longitude of the search centre"},
        "date_from": {"type": "string", "description": "ISO date string for start of window"},
        "date_to": {"type": "string", "description": "ISO date string for end of window"},
        "radius_km": {"type": "number", "description": "Search radius in kilometres", "default": 10},
    },
    "required": ["latitude", "longitude", "date_from", "date_to"],
}


@tool(
    "search_local_events",
    "Search for upcoming local events near a given location. Returns events with name, location, attendance, and time.",
    _SEARCH_SCHEMA,
)
async def search_local_events(args: dict) -> dict:
    # Mock implementation — replace with Eventbrite / Ticketmaster API call
    result = {"events": _MOCK_EVENTS, "total": len(_MOCK_EVENTS)}
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


@tool(
    "get_event_details",
    "Get detailed information about a specific event by its ID.",
    {"event_id": str},
)
async def get_event_details(args: dict) -> dict:
    event = next((e for e in _MOCK_EVENTS if e["id"] == args["event_id"]), None)
    if not event:
        result = {"error": f"Event {args['event_id']} not found"}
    else:
        result = event
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


@tool(
    "estimate_foot_traffic",
    "Estimate foot traffic and revenue potential at an event. Returns estimated customer count and revenue range.",
    {"event_id": str, "expected_attendance": int},
)
async def estimate_foot_traffic(args: dict) -> dict:
    # Mock implementation — replace with ML model or historical data lookup
    conversion_rate = random.uniform(0.05, 0.15)
    avg_order_value = random.uniform(8.0, 18.0)
    estimated_customers = int(args["expected_attendance"] * conversion_rate)
    result = {
        "event_id": args["event_id"],
        "estimated_customers": estimated_customers,
        "estimated_revenue_low": round(estimated_customers * avg_order_value * 0.8, 2),
        "estimated_revenue_high": round(estimated_customers * avg_order_value * 1.2, 2),
        "confidence": "medium",
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


# Bundle into an MCP server for use with the Agent SDK
EVENT_MCP_SERVER = create_sdk_mcp_server(
    name="event-tools",
    tools=[search_local_events, get_event_details, estimate_foot_traffic],
)
