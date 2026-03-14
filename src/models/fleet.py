from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid

from .cart import Cart, CartStatus


class Fleet(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    carts: Dict[str, Cart] = Field(default_factory=dict)

    def add_cart(self, cart: Cart) -> None:
        self.carts[cart.id] = cart

    def remove_cart(self, cart_id: str) -> Optional[Cart]:
        return self.carts.pop(cart_id, None)

    def get_cart(self, cart_id: str) -> Optional[Cart]:
        return self.carts.get(cart_id)

    def get_available_carts(self) -> List[Cart]:
        return [c for c in self.carts.values() if c.is_available()]

    def get_carts_by_status(self, status: CartStatus) -> List[Cart]:
        return [c for c in self.carts.values() if c.status == status]

    def total_carts(self) -> int:
        return len(self.carts)

    def summary(self) -> dict:
        status_counts: Dict[str, int] = {}
        for cart in self.carts.values():
            status_counts[cart.status.value] = status_counts.get(cart.status.value, 0) + 1

        return {
            "fleet_id": self.id,
            "fleet_name": self.name,
            "total_carts": self.total_carts(),
            "status_breakdown": status_counts,
            "carts": [c.model_dump_summary() for c in self.carts.values()],
        }
