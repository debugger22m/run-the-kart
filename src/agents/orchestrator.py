"""
Orchestrator Agent

The top-level agent that coordinates the EventAgent and SchedulerAgent.
It decides when to trigger event discovery, when to schedule, and maintains
overall fleet state.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .event_agent import EventAgent
from .scheduler_agent import SchedulerAgent
from ..models import Fleet, Schedule

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    fleet_summary: dict
    discovered_events: list[dict]
    schedules: list[Schedule]
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "fleet_summary": self.fleet_summary,
            "discovered_events": self.discovered_events,
            "schedules": [s.model_dump_summary() for s in self.schedules],
            "errors": self.errors,
        }


class OrchestratorAgent:
    """
    Coordinates the EventAgent and SchedulerAgent to autonomously manage
    the food truck fleet's deployment.
    """

    def __init__(self, fleet: Fleet) -> None:
        self.fleet = fleet
        self._event_agent = EventAgent()
        self._scheduler_agent = SchedulerAgent()
        self._active_schedules: dict[str, Schedule] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_cycle(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float = 10.0,
        hours_ahead: int = 12,
    ) -> OrchestrationResult:
        """
        Execute one full orchestration cycle:
          1. Derive search centre from fleet positions (or use provided lat/lng).
          2. Discover today's events in the area.
          3. Schedule available carts to the best events.
          4. Update fleet state.
        """
        errors: list[str] = []

        # Derive search centre from the fleet's cart positions if not explicitly provided
        if latitude is None or longitude is None:
            latitude, longitude = self._fleet_centroid()
            logger.info("Orchestrator: search centre derived from fleet — (%.4f, %.4f)", latitude, longitude)

        logger.info(
            "Orchestrator: starting cycle — centre=(%.4f, %.4f), radius=%dkm, window=%dh",
            latitude,
            longitude,
            radius_km,
            hours_ahead,
        )

        date_from = datetime.utcnow().strftime("%Y-%m-%d")
        date_to = (datetime.utcnow() + timedelta(hours=hours_ahead)).strftime("%Y-%m-%d")

        # --- Step 1: Discover events (runs concurrently with fleet status check) ---
        events_task = asyncio.create_task(
            self._event_agent.find_events(latitude, longitude, date_from, date_to, radius_km)
        )

        try:
            discovered_events = await events_task
            logger.info("Orchestrator: discovered %d event(s).", len(discovered_events))
        except Exception as exc:
            logger.error("Orchestrator: EventAgent failed — %s", exc)
            errors.append(f"EventAgent error: {exc}")
            discovered_events = []

        schedules: list[Schedule] = []

        # --- Step 2: Schedule carts to events ---
        if discovered_events and self.fleet.get_available_carts():
            try:
                schedules = await self._scheduler_agent.create_schedules(
                    self.fleet, discovered_events
                )
                logger.info("Orchestrator: created %d schedule(s).", len(schedules))
            except Exception as exc:
                logger.error("Orchestrator: SchedulerAgent failed — %s", exc)
                errors.append(f"SchedulerAgent error: {exc}")
        elif not self.fleet.get_available_carts():
            logger.info("Orchestrator: no available carts — skipping scheduling.")
        else:
            logger.info("Orchestrator: no events found — skipping scheduling.")

        # --- Step 3: Apply schedules to fleet ---
        for schedule in schedules:
            self._apply_schedule(schedule)

        return OrchestrationResult(
            fleet_summary=self.fleet.summary(),
            discovered_events=discovered_events,
            schedules=schedules,
            errors=errors,
        )

    def get_active_schedules(self) -> list[Schedule]:
        return list(self._active_schedules.values())

    def complete_schedule(self, schedule_id: str) -> bool:
        """Mark a schedule as completed and return the cart to idle."""
        schedule = self._active_schedules.get(schedule_id)
        if not schedule:
            return False
        schedule.complete()
        cart = self.fleet.get_cart(schedule.cart_id)
        if cart:
            cart.go_idle()
        del self._active_schedules[schedule_id]
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fleet_centroid(self) -> tuple[float, float]:
        """Return the average lat/lng of all carts that have a known location."""
        located = [c for c in self.fleet.carts.values() if c.current_location]
        if not located:
            # Default to downtown Salt Lake City if no cart locations are known
            return 40.7608, -111.8910
        lat = sum(c.current_location.lat for c in located) / len(located)
        lng = sum(c.current_location.lng for c in located) / len(located)
        return lat, lng

    def _apply_schedule(self, schedule: Schedule) -> None:
        """Push a schedule onto a cart and register it as active."""
        cart = self.fleet.get_cart(schedule.cart_id)
        if not cart:
            logger.warning("Orchestrator: cart %s not found in fleet.", schedule.cart_id)
            return
        cart.assign(schedule.id, schedule.event.coordinates)
        self._active_schedules[schedule.id] = schedule
        logger.info(
            "Orchestrator: cart '%s' assigned to event '%s' at %s.",
            cart.name,
            schedule.event.name,
            schedule.event.coordinates,
        )
