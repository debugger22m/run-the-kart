"""
Event discovery tools for the EventAgent.

Primary source: Ticketmaster Discovery API (free, set TICKETMASTER_API_KEY in .env).
Fallback:       rotating mock events in Salt Lake City (no key required).
"""

import json
import logging
import math
import os
import random
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")

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
    """
    Return the active event wave for the current minute.
    Alternates between Wave A and Wave B every 60 seconds so carts are
    re-assigned to entirely different SLC locations after each expiry cycle.
    """
    now = datetime.utcnow()
    wave = int(now.timestamp() / 60) % 2  # flips every 60 seconds

    # Wave A — north/central Downtown SLC
    wave_a = [
        {
            "id": "evt_a01",
            "name": "Utah Jazz Home Game",
            "location_name": "Delta Center",
            "latitude": 40.7683, "longitude": -111.9012,
            "expected_attendance": 18500,
            "start_time": (now + timedelta(minutes=30)).isoformat(),
            "end_time": (now + timedelta(hours=4)).isoformat(),
            "category": "sports",
            "description": "Utah Jazz vs Lakers — sold-out game at Delta Center.",
        },
        {
            "id": "evt_a02",
            "name": "Temple Square Cultural Fest",
            "location_name": "Temple Square",
            "latitude": 40.7708, "longitude": -111.8958,
            "expected_attendance": 6000,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=6)).isoformat(),
            "category": "festival",
            "description": "Annual cultural festival at Temple Square.",
        },
        {
            "id": "evt_a03",
            "name": "Utah Tech Summit 2026",
            "location_name": "Salt Palace Convention Center",
            "latitude": 40.7608, "longitude": -111.8973,
            "expected_attendance": 5000,
            "start_time": (now + timedelta(minutes=15)).isoformat(),
            "end_time": (now + timedelta(hours=8)).isoformat(),
            "category": "conference",
            "description": "Annual statewide technology summit at the Salt Palace.",
        },
        {
            "id": "evt_a04",
            "name": "Jazz in the Park",
            "location_name": "Gallivan Center",
            "latitude": 40.7611, "longitude": -111.8906,
            "expected_attendance": 4000,
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=6)).isoformat(),
            "category": "music",
            "description": "Free outdoor jazz concert at Gallivan Plaza.",
        },
        {
            "id": "evt_a05",
            "name": "SLC Downtown Farmers Market",
            "location_name": "Pioneer Park",
            "latitude": 40.7580, "longitude": -111.9012,
            "expected_attendance": 3500,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=5)).isoformat(),
            "category": "market",
            "description": "Utah's largest weekly outdoor farmers market.",
        },
        {
            "id": "evt_a06",
            "name": "University of Utah Graduation",
            "location_name": "Rice-Eccles Stadium",
            "latitude": 40.7596, "longitude": -111.8486,
            "expected_attendance": 12000,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=4)).isoformat(),
            "category": "conference",
            "description": "Spring commencement ceremony at Rice-Eccles Stadium.",
        },
        {
            "id": "evt_a07",
            "name": "Gateway Night Market",
            "location_name": "The Gateway Mall",
            "latitude": 40.7694, "longitude": -111.9018,
            "expected_attendance": 2500,
            "start_time": (now + timedelta(hours=3)).isoformat(),
            "end_time": (now + timedelta(hours=8)).isoformat(),
            "category": "market",
            "description": "Evening market with local vendors and live entertainment.",
        },
        {
            "id": "evt_a08",
            "name": "City Creek Lunch Rush",
            "location_name": "City Creek Center",
            "latitude": 40.7683, "longitude": -111.8945,
            "expected_attendance": 2000,
            "start_time": (now + timedelta(minutes=10)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
            "category": "food",
            "description": "Peak lunch crowd at City Creek shopping center.",
        },
    ]

    # Wave B — south/east SLC districts
    wave_b = [
        {
            "id": "evt_b01",
            "name": "Trolley Square Artisan Fair",
            "location_name": "Trolley Square",
            "latitude": 40.7497, "longitude": -111.8780,
            "expected_attendance": 4500,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=6)).isoformat(),
            "category": "market",
            "description": "Weekend artisan fair at historic Trolley Square.",
        },
        {
            "id": "evt_b02",
            "name": "Sugar House Block Party",
            "location_name": "Sugar House Park",
            "latitude": 40.7239, "longitude": -111.8583,
            "expected_attendance": 5500,
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=7)).isoformat(),
            "category": "festival",
            "description": "Annual Sugar House neighborhood block party.",
        },
        {
            "id": "evt_b03",
            "name": "9th & 9th Street Festival",
            "location_name": "9th & 9th District",
            "latitude": 40.7448, "longitude": -111.8697,
            "expected_attendance": 3000,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=5)).isoformat(),
            "category": "festival",
            "description": "Bohemian street festival in the 9th & 9th neighborhood.",
        },
        {
            "id": "evt_b04",
            "name": "Liberty Park Concert Series",
            "location_name": "Liberty Park",
            "latitude": 40.7373, "longitude": -111.8756,
            "expected_attendance": 6000,
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=6)).isoformat(),
            "category": "music",
            "description": "Outdoor summer concert at Liberty Park amphitheater.",
        },
        {
            "id": "evt_b05",
            "name": "Westminster Alumni Reunion",
            "location_name": "Westminster University",
            "latitude": 40.7093, "longitude": -111.8632,
            "expected_attendance": 2800,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=5)).isoformat(),
            "category": "conference",
            "description": "Annual alumni homecoming weekend at Westminster campus.",
        },
        {
            "id": "evt_b06",
            "name": "Ball Park Neighborhood Cookoff",
            "location_name": "Ball Park District",
            "latitude": 40.7332, "longitude": -111.9019,
            "expected_attendance": 2200,
            "start_time": (now + timedelta(minutes=45)).isoformat(),
            "end_time": (now + timedelta(hours=4)).isoformat(),
            "category": "food",
            "description": "Community BBQ cook-off in the Ball Park neighborhood.",
        },
        {
            "id": "evt_b07",
            "name": "SLC Public Library Book Fest",
            "location_name": "Salt Lake City Library",
            "latitude": 40.7607, "longitude": -111.8912,
            "expected_attendance": 1500,
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=5)).isoformat(),
            "category": "festival",
            "description": "Annual literary festival at the iconic SLC Main Library.",
        },
        {
            "id": "evt_b08",
            "name": "Avenues Garden & Food Tour",
            "location_name": "The Avenues",
            "latitude": 40.7811, "longitude": -111.8833,
            "expected_attendance": 1800,
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "end_time": (now + timedelta(hours=5)).isoformat(),
            "category": "food",
            "description": "Self-guided garden and food tour through the historic Avenues.",
        },
    ]

    return wave_a if wave == 0 else wave_b


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_CATEGORY_PROFILE = {
    "music":      {"conversion": 0.12, "avg_order": 14.0},
    "conference": {"conversion": 0.09, "avg_order": 16.0},
    "market":     {"conversion": 0.14, "avg_order": 11.0},
    "food":       {"conversion": 0.08, "avg_order": 13.0},
    "festival":   {"conversion": 0.15, "avg_order": 12.0},
    "sports":     {"conversion": 0.10, "avg_order": 10.0},
}
_DEFAULT_PROFILE = {"conversion": 0.08, "avg_order": 11.0}


def _score_event(event: dict) -> dict:
    """Compute demand forecast and opportunity score inline — avoids extra LLM tool calls."""
    profile = _CATEGORY_PROFILE.get(event.get("category", ""), _DEFAULT_PROFILE)
    attendance = event["expected_attendance"]
    start = datetime.fromisoformat(event["start_time"])
    end = datetime.fromisoformat(event["end_time"])
    duration_hours = max((end - start).total_seconds() / 3600, 1)

    estimated_customers = int(attendance * profile["conversion"])
    avg_order = profile["avg_order"]
    estimated_revenue = round(estimated_customers * avg_order, 2)

    # Demand score: customers per hour, capped at 100
    demand_score = min(100, round((estimated_customers / duration_hours) * 2, 1))

    # Time-of-day bonus (UTC hours)
    h = start.hour
    time_bonus = 15 if (11 <= h <= 14 or 17 <= h <= 21) else (5 if 9 <= h <= 16 else -10)
    duration_bonus = min(10, (duration_hours - 2) * 2) if duration_hours > 2 else 0
    revenue_bonus = min(10, math.log10(max(estimated_revenue, 1)) * 2)
    opportunity_score = round(min(100, max(0, demand_score + time_bonus + duration_bonus + revenue_bonus)), 1)

    return {
        **event,
        "estimated_customers": estimated_customers,
        "estimated_revenue_high": estimated_revenue,
        "demand_score": demand_score,
        "opportunity_score": opportunity_score,
    }


def _get_events_for_today(
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    min_attendance: int = 200,
) -> dict:
    """
    Return today's SLC events pre-scored by demand and opportunity.
    Scores are pre-computed so the EventAgent can return results in a single tool call.
    """
    events = _build_mock_events()
    scored = [_score_event(e) for e in events if e["expected_attendance"] >= min_attendance]
    scored.sort(key=lambda e: e["opportunity_score"], reverse=True)
    return {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "location": "Salt Lake City, UT",
        "centre": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "events": scored,
        "total": len(scored),
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


# ---------------------------------------------------------------------------
# Ticketmaster Discovery API (live events)
# ---------------------------------------------------------------------------

_TM_CATEGORY_MAP = {
    "music":           "music",
    "sports":          "sports",
    "arts & theatre":  "festival",
    "family":          "festival",
    "film":            "festival",
    "miscellaneous":   "conference",
    "undefined":       "conference",
}

_TM_ATTENDANCE = {
    "sports":     18000,
    "music":       8000,
    "festival":    5000,
    "conference":  3000,
    "market":      2500,
    "food":        2000,
}


async def _fetch_ticketmaster_events(
    latitude: float,
    longitude: float,
    radius_km: float = 50.0,
) -> list[dict] | None:
    """
    Fetch real events from Ticketmaster Discovery API.
    Returns None when the key is missing or the request fails (triggers mock fallback).
    """
    if not TICKETMASTER_API_KEY:
        return None

    radius_miles = max(1, int(radius_km * 0.621371))
    now = datetime.utcnow()
    params = {
        "apikey":        TICKETMASTER_API_KEY,
        "latlong":       f"{latitude},{longitude}",
        "radius":        radius_miles,
        "unit":          "miles",
        "size":          20,
        "sort":          "date,asc",
        "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime":   (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://app.ticketmaster.com/discovery/v2/events.json",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Ticketmaster API error: %s — falling back to mock events", exc)
        return None

    raw_events = data.get("_embedded", {}).get("events", [])
    events: list[dict] = []

    for e in raw_events:
        venues = e.get("_embedded", {}).get("venues", [{}])
        venue  = venues[0] if venues else {}
        loc    = venue.get("location", {})

        lat_str = loc.get("latitude")
        lng_str = loc.get("longitude")
        if not lat_str or not lng_str:
            continue

        start_info = e.get("dates", {}).get("start", {})
        start_iso  = start_info.get("dateTime") or start_info.get("localDate")
        if not start_iso:
            continue

        try:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue

        end_dt = start_dt + timedelta(hours=3)

        # Map Ticketmaster segment to our category
        classifications = e.get("classifications", [{}])
        segment = classifications[0].get("segment", {}).get("name", "").lower() if classifications else ""
        category = _TM_CATEGORY_MAP.get(segment, "conference")

        attendance = _TM_ATTENDANCE.get(category, 2500)

        events.append({
            "id":                  f"tm_{e.get('id', '')}",
            "name":                e.get("name", "Unknown Event"),
            "location_name":       venue.get("name", "Unknown Venue"),
            "latitude":            float(lat_str),
            "longitude":           float(lng_str),
            "expected_attendance": attendance,
            "start_time":          start_dt.isoformat(),
            "end_time":            end_dt.isoformat(),
            "category":            category,
            "description":         f"{e.get('name')} at {venue.get('name', 'Unknown Venue')}",
            "source":              "ticketmaster",
        })

    logger.info("Ticketmaster: fetched %d event(s) near (%.4f, %.4f)", len(events), latitude, longitude)
    return events


# ---------------------------------------------------------------------------
# Updated async get_events_for_today (tries Ticketmaster, falls back to mock)
# ---------------------------------------------------------------------------

async def _get_events_for_today_async(
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
    min_attendance: int = 200,
) -> dict:
    if TICKETMASTER_API_KEY:
        # Live mode — use Ticketmaster for the given coordinates.
        # Do NOT fall back to SLC mock events if the city changed.
        live_events = await _fetch_ticketmaster_events(latitude, longitude, radius_km)
        events = live_events or []
        source = "ticketmaster"
    else:
        # No key — use rotating SLC mock events for demo
        events = _build_mock_events()
        source = "mock"

    scored = [_score_event(e) for e in events if e["expected_attendance"] >= min_attendance]
    scored.sort(key=lambda e: e["opportunity_score"], reverse=True)

    return {
        "date":      datetime.utcnow().strftime("%Y-%m-%d"),
        "location":  f"({latitude:.4f}, {longitude:.4f})",
        "centre":    {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "source":    source,
        "events":    scored,
        "total":     len(scored),
    }


async def handle_event_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    try:
        if tool_name == "get_events_for_today":
            result = await _get_events_for_today_async(**tool_input)
            return json.dumps(result, default=str)
        elif tool_name == "search_local_events":
            return json.dumps(_search_local_events(**tool_input), default=str)
        elif tool_name == "get_event_details":
            return json.dumps(_get_event_details(**tool_input), default=str)
        elif tool_name == "estimate_foot_traffic":
            return json.dumps(_estimate_foot_traffic(**tool_input), default=str)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
