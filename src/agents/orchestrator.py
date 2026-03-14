"""
Orchestrator Agent

Fully autonomous coordinator. Each cycle:
  1. Auto-expires schedules whose events have ended → carts return to idle.
  2. Derives search centre from fleet positions.
  3. Runs EventAgent to discover and score today's SLC events.
  4. Runs SchedulerAgent to assign idle carts to the best events.
  5. Applies assignments to fleet state.

No human input is required between cycles.
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
    expired_schedules: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "fleet_summary": self.fleet_summary,
            "discovered_events": self.discovered_events,
            "schedules": [s.model_dump_summary() for s in self.schedules],
            "expired_schedules": self.expired_schedules,
            "errors": self.errors,
        }


class OrchestratorAgent:
    """
    Autonomous coordinator for the food truck fleet.
    Designed to run continuously via AutonomousLoop — no manual triggers needed.
    """

    def __init__(self, fleet: Fleet) -> None:
        self.fleet = fleet
        self._event_agent = EventAgent()
        self._scheduler_agent = SchedulerAgent()
        self._active_schedules: dict[str, Schedule] = {}
        self._city_override: tuple[float, float] | None = None
        self._city_name: str = "Salt Lake City, UT"

    def set_city(self, name: str, lat: float, lng: float) -> None:
        """Pin the search centre to an explicit city — overrides fleet centroid."""
        self._city_override = (lat, lng)
        self._city_name = name
        logger.info("Orchestrator: city set to %s (%.4f, %.4f)", name, lat, lng)

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
        One full autonomous cycle — safe to call repeatedly with no side effects.
        """
        errors: list[str] = []

        # Step 1: Free carts whose events have ended
        expired = self._expire_completed_schedules()
        if expired:
            logger.info("Orchestrator: auto-expired %d schedule(s) — carts returned to idle.", expired)

        # Step 2: City override > caller-provided > fleet centroid
        if self._city_override:
            latitude, longitude = self._city_override
            logger.info("Orchestrator: using city override %s — (%.4f, %.4f)", self._city_name, latitude, longitude)
        elif latitude is None or longitude is None:
            latitude, longitude = self._fleet_centroid()
            logger.info("Orchestrator: search centre from fleet centroid — (%.4f, %.4f)", latitude, longitude)

        logger.info(
            "Orchestrator: cycle start — centre=(%.4f, %.4f) radius=%dkm idle_carts=%d",
            latitude, longitude, radius_km, len(self.fleet.get_available_carts()),
        )

        date_from = datetime.utcnow().strftime("%Y-%m-%d")
        date_to = (datetime.utcnow() + timedelta(hours=hours_ahead)).strftime("%Y-%m-%d")

        # Step 3: Discover events
        try:
            discovered_events = await self._event_agent.find_events(
                latitude, longitude, date_from, date_to, radius_km
            )
            logger.info("Orchestrator: %d event(s) discovered.", len(discovered_events))
        except Exception as exc:
            logger.error("Orchestrator: EventAgent failed — %s", exc)
            errors.append(f"EventAgent error: {exc}")
            discovered_events = []

        # Step 4: Assign idle carts to events
        new_schedules: list[Schedule] = []
        available = self.fleet.get_available_carts()

        if not available:
            logger.info("Orchestrator: all carts busy — skipping scheduling this cycle.")
        elif not discovered_events:
            logger.info("Orchestrator: no events found — skipping scheduling this cycle.")
        else:
            try:
                new_schedules = await self._scheduler_agent.create_schedules(
                    self.fleet, discovered_events
                )
                logger.info("Orchestrator: %d new schedule(s) created.", len(new_schedules))
            except Exception as exc:
                logger.error("Orchestrator: SchedulerAgent failed — %s", exc)
                errors.append(f"SchedulerAgent error: {exc}")

        # Step 5: Apply new schedules to fleet
        for schedule in new_schedules:
            self._apply_schedule(schedule)

        return OrchestrationResult(
            fleet_summary=self.fleet.summary(),
            discovered_events=discovered_events,
            schedules=new_schedules,
            expired_schedules=expired,
            errors=errors,
        )

    def get_active_schedules(self) -> list[Schedule]:
        return list(self._active_schedules.values())

    def complete_schedule(self, schedule_id: str) -> bool:
        """Manually mark a schedule as completed and return the cart to idle."""
        schedule = self._active_schedules.get(schedule_id)
        if not schedule:
            return False
        schedule.complete()
        cart = self.fleet.get_cart(schedule.cart_id)
        if cart:
            cart.go_idle()
        del self._active_schedules[schedule_id]
        logger.info("Orchestrator: schedule %s manually completed.", schedule_id)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _expire_completed_schedules(self) -> int:
        """
        Scan active schedules and auto-complete any whose departure_time has passed.
        Returns the number of schedules expired.
        """
        now = datetime.utcnow()
        expired_ids = [
            sid for sid, s in self._active_schedules.items()
            if s.departure_time <= now
        ]
        for sid in expired_ids:
            schedule = self._active_schedules.pop(sid)
            schedule.complete()
            cart = self.fleet.get_cart(schedule.cart_id)
            if cart:
                cart.go_idle()
                logger.info(
                    "Orchestrator: '%s' finished at '%s' — back to idle.",
                    cart.name,
                    schedule.event.name,
                )
        return len(expired_ids)

    def _fleet_centroid(self) -> tuple[float, float]:
        """Average lat/lng of all carts with a known location."""
        located = [c for c in self.fleet.carts.values() if c.current_location]
        if not located:
            return 40.7608, -111.8910  # Downtown SLC fallback
        lat = sum(c.current_location.lat for c in located) / len(located)
        lng = sum(c.current_location.lng for c in located) / len(located)
        return lat, lng

    def _apply_schedule(self, schedule: Schedule) -> None:
        cart = self.fleet.get_cart(schedule.cart_id)
        if not cart:
            logger.warning("Orchestrator: cart %s not found in fleet.", schedule.cart_id)
            return
        cart.assign(schedule.id, schedule.event.coordinates)
        self._active_schedules[schedule.id] = schedule
        logger.info(
            "Orchestrator: '%s' → '%s' (departs %s).",
            cart.name,
            schedule.event.name,
            schedule.departure_time.strftime("%H:%M UTC"),
        )
