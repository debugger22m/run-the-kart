"""
ScheduleRepository — CRUD operations for the schedules table.

Events are upserted into the events table when a schedule is created,
so that the event cache is populated as a side-effect of scheduling.
"""

import logging
import uuid

from supabase import AsyncClient

from ..models.schedule import Schedule

logger = logging.getLogger(__name__)


class ScheduleRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create_schedule(self, schedule: Schedule) -> str:
        """
        Upsert the schedule's event into the events table then insert the schedule.
        Returns the event's DB id (UUID).
        """
        event_db_id = await self._upsert_event(schedule)

        await self._client.table("schedules").insert({
            "id": schedule.id,
            "cart_id": schedule.cart_id,
            "event_id": event_db_id,
            "arrival_time": schedule.arrival_time.isoformat(),
            "departure_time": schedule.departure_time.isoformat(),
            "status": schedule.status.value,
            "estimated_revenue": schedule.estimated_revenue,
            "notes": schedule.notes,
        }).execute()

        logger.info(
            "ScheduleRepository: created schedule %s (cart=%s, event=%s)",
            schedule.id, schedule.cart_id, schedule.event.name,
        )
        return event_db_id

    async def update_status(self, schedule_id: str, status: str) -> None:
        """Update the status of a schedule by id."""
        await (
            self._client.table("schedules")
            .update({"status": status})
            .eq("id", schedule_id)
            .execute()
        )

    async def get_active(self) -> list[dict]:
        """Return all confirmed or in-progress schedules with event data joined."""
        response = await (
            self._client.table("schedules")
            .select("*, events(*)")
            .in_("status", ["confirmed", "in_progress"])
            .execute()
        )
        return response.data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _upsert_event(self, schedule: Schedule) -> str:
        """
        Upsert the event from a schedule into the events table.
        Uses external_id (the original string id from the agent) for dedup.
        Returns the UUID primary key of the event row.
        """
        event = schedule.event
        external_id = event.id  # original agent-assigned id (e.g. 'evt_001')

        # Check if it already exists
        existing = (
            await self._client.table("events")
            .select("id")
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]["id"]

        # Insert new event row
        new_id = str(uuid.uuid4())
        await self._client.table("events").insert({
            "id": new_id,
            "external_id": external_id,
            "name": event.name,
            "location_name": event.location_name,
            "lat": event.coordinates.lat,
            "lng": event.coordinates.lng,
            "expected_attendance": event.expected_attendance,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
            "category": event.category,
            "source": "agent",
        }).execute()
        return new_id
