"""
FleetRepository — CRUD operations for the carts table.
"""

import logging
from typing import Optional

from supabase import AsyncClient

from ..models.cart import Cart, CartStatus, Coordinates

logger = logging.getLogger(__name__)


class FleetRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def load_all_carts(self, fleet_id: str) -> list[Cart]:
        """Load all carts belonging to a fleet from the DB."""
        response = (
            await self._client.table("carts")
            .select("*")
            .eq("fleet_id", fleet_id)
            .execute()
        )
        return [self._row_to_cart(row) for row in response.data]

    async def insert_cart(self, cart: Cart, fleet_id: str) -> None:
        """Persist a new cart to the DB."""
        await self._client.table("carts").insert(
            self._cart_to_row(cart, fleet_id)
        ).execute()
        logger.info("FleetRepository: inserted cart %s (%s)", cart.id, cart.name)

    async def update_cart(self, cart: Cart) -> None:
        """Persist status and location changes for an existing cart."""
        await (
            self._client.table("carts")
            .update({
                "status": cart.status.value,
                "current_lat": cart.current_location.lat if cart.current_location else None,
                "current_lng": cart.current_location.lng if cart.current_location else None,
                "assigned_schedule_id": cart.assigned_schedule_id,
            })
            .eq("id", cart.id)
            .execute()
        )

    async def delete_cart(self, cart_id: str) -> None:
        """Remove a cart from the DB."""
        await self._client.table("carts").delete().eq("id", cart_id).execute()
        logger.info("FleetRepository: deleted cart %s", cart_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cart_to_row(self, cart: Cart, fleet_id: str) -> dict:
        return {
            "id": cart.id,
            "fleet_id": fleet_id,
            "name": cart.name,
            "status": cart.status.value,
            "current_lat": cart.current_location.lat if cart.current_location else None,
            "current_lng": cart.current_location.lng if cart.current_location else None,
            "max_orders_per_hour": cart.max_orders_per_hour,
            "assigned_schedule_id": cart.assigned_schedule_id,
        }

    def _row_to_cart(self, row: dict) -> Cart:
        location: Optional[Coordinates] = None
        if row.get("current_lat") is not None and row.get("current_lng") is not None:
            location = Coordinates(lat=row["current_lat"], lng=row["current_lng"])
        return Cart(
            id=row["id"],
            name=row["name"],
            status=CartStatus(row["status"]),
            current_location=location,
            max_orders_per_hour=row.get("max_orders_per_hour", 50),
            assigned_schedule_id=row.get("assigned_schedule_id"),
        )
