"""
Maps and routing tools for the SchedulerAgent.

Replace mock implementations with Google Maps / Mapbox / OpenRouteService calls.
"""

import json
import math
import random
from typing import Any

# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------

MAPS_TOOLS = [
    {
        "name": "calculate_route",
        "description": (
            "Calculate the driving route and estimated travel time between two coordinates. "
            "Returns distance in km and estimated travel duration in minutes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin_lat": {"type": "number", "description": "Origin latitude"},
                "origin_lng": {"type": "number", "description": "Origin longitude"},
                "destination_lat": {"type": "number", "description": "Destination latitude"},
                "destination_lng": {"type": "number", "description": "Destination longitude"},
            },
            "required": ["origin_lat", "origin_lng", "destination_lat", "destination_lng"],
        },
    },
    {
        "name": "find_nearest_available_cart",
        "description": (
            "Given a destination and a list of available cart IDs with their current locations, "
            "find the cart that can arrive fastest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination_lat": {"type": "number"},
                "destination_lng": {"type": "number"},
                "available_carts": {
                    "type": "array",
                    "description": "List of available cart info objects",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cart_id": {"type": "string"},
                            "lat": {"type": "number"},
                            "lng": {"type": "number"},
                        },
                        "required": ["cart_id", "lat", "lng"],
                    },
                },
            },
            "required": ["destination_lat", "destination_lng", "available_carts"],
        },
    },
    {
        "name": "check_parking_availability",
        "description": (
            "Check if there is adequate space for a food truck to park at the given coordinates. "
            "Returns availability status and any restrictions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "location_name": {"type": "string", "description": "Human-readable location name"},
            },
            "required": ["latitude", "longitude"],
        },
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Mock handlers
# ---------------------------------------------------------------------------

def _calculate_route(
    origin_lat: float, origin_lng: float, destination_lat: float, destination_lng: float
) -> dict:
    """Mock route calculation — replace with Google Maps Directions API."""
    distance_km = _haversine_km(origin_lat, origin_lng, destination_lat, destination_lng)
    # Assume average urban speed of 30 km/h with some traffic variance
    base_minutes = (distance_km / 30) * 60
    duration_minutes = round(base_minutes * random.uniform(1.0, 1.4), 1)
    return {
        "distance_km": round(distance_km, 2),
        "duration_minutes": duration_minutes,
        "origin": {"lat": origin_lat, "lng": origin_lng},
        "destination": {"lat": destination_lat, "lng": destination_lng},
        "traffic_condition": random.choice(["light", "moderate", "heavy"]),
    }


def _find_nearest_available_cart(
    destination_lat: float, destination_lng: float, available_carts: list[dict]
) -> dict:
    """Mock nearest-cart finder — replace with a real routing matrix call."""
    if not available_carts:
        return {"error": "No available carts provided"}

    best = min(
        available_carts,
        key=lambda c: _haversine_km(c["lat"], c["lng"], destination_lat, destination_lng),
    )
    distance = _haversine_km(best["lat"], best["lng"], destination_lat, destination_lng)
    return {
        "cart_id": best["cart_id"],
        "distance_km": round(distance, 2),
        "estimated_arrival_minutes": round((distance / 30) * 60, 1),
    }


def _check_parking_availability(
    latitude: float, longitude: float, location_name: str = ""
) -> dict:
    """Mock parking check — replace with city permit API or Google Places."""
    available = random.choice([True, True, True, False])
    return {
        "available": available,
        "location": location_name or f"({latitude}, {longitude})",
        "max_truck_length_m": 7.5 if available else None,
        "permit_required": random.choice([True, False]),
        "restrictions": [] if available else ["No parking during peak hours"],
    }


def handle_maps_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Route a Claude tool_use call to the correct handler and return a JSON string."""
    handlers = {
        "calculate_route": lambda i: _calculate_route(**i),
        "find_nearest_available_cart": lambda i: _find_nearest_available_cart(**i),
        "check_parking_availability": lambda i: _check_parking_availability(**i),
    }
    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = handler(tool_input)
        return json.dumps(result, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
