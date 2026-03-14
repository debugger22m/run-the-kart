"""
OrchestrationRepository — append-only log of orchestration cycle results.
"""

import logging
from datetime import datetime

from supabase import AsyncClient

logger = logging.getLogger(__name__)


class OrchestrationRepository:
    def __init__(self, client: AsyncClient, fleet_id: str) -> None:
        self._client = client
        self._fleet_id = fleet_id

    async def save_run(self, result) -> None:
        """Persist an OrchestrationResult as an audit log entry."""
        await self._client.table("orchestration_runs").insert({
            "fleet_id": self._fleet_id,
            "completed_at": datetime.utcnow().isoformat(),
            "events_discovered": len(result.discovered_events),
            "schedules_created": len(result.schedules),
            "fleet_summary": result.fleet_summary,
            "errors": result.errors,
        }).execute()
        logger.info(
            "OrchestrationRepository: saved run — %d events, %d schedules",
            len(result.discovered_events), len(result.schedules),
        )

    async def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Return the most recent orchestration runs for a fleet."""
        response = await (
            self._client.table("orchestration_runs")
            .select("id, completed_at, events_discovered, schedules_created, errors")
            .eq("fleet_id", self._fleet_id)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
