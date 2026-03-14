"""
Maps and routing tools for the SchedulerAgent.

Replace mock implementations with Google Maps / Mapbox / OpenRouteService calls.
"""

import json
import math
import random

from claude_agent_sdk import tool, create_sdk_mcp_server

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
# Tool definitions
# ---------------------------------------------------------------------------

_ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "origin_lat": {"type": "number", "description": "Origin latitude"},
        "origin_lng": {"type": "number", "description": "Origin longitude"},
        "destination_lat": {"type": "number", "description": "Destination latitude"},
        "destination_lng": {"type": "number", "description": "Destination longitude"},
    },
    "required": ["origin_lat", "origin_lng", "destination_lat", "destination_lng"],
}

_NEAREST_CART_SCHEMA = {
    "type": "object",
    "properties": {
        "destination_lat": {"type": "number"},
        "destination_lng": {"type": "number"},
        "available_carts": {
            "type": "array",
            "description": "List of cart objects with cart_id, lat, and lng fields",
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
}

_PARKING_SCHEMA = {
    "type": "object",
    "properties": {
        "latitude": {"type": "number"},
        "longitude": {"type": "number"},
        "location_name": {"type": "string", "description": "Human-readable location name"},
    },
    "required": ["latitude", "longitude"],
}


@tool(
    "calculate_route",
    "Calculate the driving route and estimated travel time between two coordinates. Returns distance in km and duration in minutes.",
    _ROUTE_SCHEMA,
)
async def calculate_route(args: dict) -> dict:
    # Mock implementation — replace with Google Maps Directions API
    distance_km = _haversine_km(
        args["origin_lat"], args["origin_lng"],
        args["destination_lat"], args["destination_lng"],
    )
    base_minutes = (distance_km / 30) * 60
    result = {
        "distance_km": round(distance_km, 2),
        "duration_minutes": round(base_minutes * random.uniform(1.0, 1.4), 1),
        "origin": {"lat": args["origin_lat"], "lng": args["origin_lng"]},
        "destination": {"lat": args["destination_lat"], "lng": args["destination_lng"]},
        "traffic_condition": random.choice(["light", "moderate", "heavy"]),
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


@tool(
    "find_nearest_available_cart",
    "Given a destination and a list of available carts with their locations, find the cart that can arrive fastest.",
    _NEAREST_CART_SCHEMA,
)
async def find_nearest_available_cart(args: dict) -> dict:
    # Mock implementation — replace with a real routing matrix call
    carts = args.get("available_carts", [])
    if not carts:
        return {"content": [{"type": "text", "text": json.dumps({"error": "No available carts provided"})}]}

    best = min(
        carts,
        key=lambda c: _haversine_km(c["lat"], c["lng"], args["destination_lat"], args["destination_lng"]),
    )
    distance = _haversine_km(best["lat"], best["lng"], args["destination_lat"], args["destination_lng"])
    result = {
        "cart_id": best["cart_id"],
        "distance_km": round(distance, 2),
        "estimated_arrival_minutes": round((distance / 30) * 60, 1),
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


@tool(
    "check_parking_availability",
    "Check if there is adequate space for a food truck to park at the given coordinates. Returns availability and any restrictions.",
    _PARKING_SCHEMA,
)
async def check_parking_availability(args: dict) -> dict:
    # Mock implementation — replace with city permit API or Google Places
    available = random.choice([True, True, True, False])
    location = args.get("location_name") or f"({args['latitude']}, {args['longitude']})"
    result = {
        "available": available,
        "location": location,
        "max_truck_length_m": 7.5 if available else None,
        "permit_required": random.choice([True, False]),
        "restrictions": [] if available else ["No parking during peak hours"],
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


# Bundle into an MCP server for use with the Agent SDK
MAPS_MCP_SERVER = create_sdk_mcp_server(
    name="maps-tools",
    tools=[calculate_route, find_nearest_available_cart, check_parking_availability],
)
