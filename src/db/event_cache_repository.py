"""
EventCacheRepository — read/write discovered events to the events table.

The EventAgent uses this to avoid re-fetching events that were already
discovered in a recent orchestration cycle.
"""

import logging
from datetime import datetime, timedelta

from supabase import AsyncClient

logger = logging.getLogger(__name__)

_DEFAULT_TTL_HOURS = 4


class EventCacheRepository:
    def __init__(self, client: AsyncClient, cache_ttl_hours: int = _DEFAULT_TTL_HOURS) -> None:
        self._client = client
        self._ttl = timedelta(hours=cache_ttl_hours)

    async def get_cached_events(
        self,
        date: str,
        min_attendance: int = 200,
    ) -> list[dict] | None:
        """
        Return cached events for a given date if fresh results exist.
        Returns None when the cache is empty or stale so the caller falls
        through to the live data source.
        """
        cutoff = (datetime.utcnow() - self._ttl).isoformat()
        response = await (
            self._client.table("events")
            .select("*")
            .gte("start_time", f"{date}T00:00:00Z")
            .lte("start_time", f"{date}T23:59:59Z")
            .gte("expected_attendance", min_attendance)
            .gte("discovered_at", cutoff)
            .order("opportunity_score", desc=True)
            .execute()
        )
        if response.data:
            logger.info("EventCacheRepository: cache hit — %d event(s) for %s", len(response.data), date)
            return self._rows_to_agent_format(response.data)

        logger.info("EventCacheRepository: cache miss for %s", date)
        return None

    async def cache_events(self, events: list[dict]) -> None:
        """
        Upsert a list of agent-format events into the events table.
        Skips events that have no external_id (can't dedup safely).
        """
        rows = []
        for e in events:
            external_id = e.get("id")
            if not external_id:
                continue
            rows.append({
                "external_id": external_id,
                "name": e["name"],
                "location_name": e.get("location_name", ""),
                "lat": e.get("latitude", e.get("lat", 0.0)),
                "lng": e.get("longitude", e.get("lng", 0.0)),
                "expected_attendance": e.get("expected_attendance", 0),
                "start_time": e.get("start_time"),
                "end_time": e.get("end_time"),
                "category": e.get("category"),
                "description": e.get("description"),
                "source": e.get("source", "agent"),
                "demand_score": e.get("demand_score"),
                "opportunity_score": e.get("opportunity_score"),
                "discovered_at": datetime.utcnow().isoformat(),
            })

        if rows:
            await (
                self._client.table("events")
                .upsert(rows, on_conflict="external_id")
                .execute()
            )
            logger.info("EventCacheRepository: cached %d event(s)", len(rows))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rows_to_agent_format(self, rows: list[dict]) -> list[dict]:
        """Convert DB rows back to the dict format the EventAgent expects."""
        result = []
        for row in rows:
            result.append({
                "id": row.get("external_id") or row["id"],
                "name": row["name"],
                "location_name": row["location_name"],
                "latitude": row["lat"],
                "longitude": row["lng"],
                "expected_attendance": row["expected_attendance"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "category": row.get("category"),
                "description": row.get("description"),
                "demand_score": row.get("demand_score"),
                "opportunity_score": row.get("opportunity_score"),
            })
        return result
