"""
Autonomous orchestration loop.

Runs a full orchestration cycle (EventAgent → SchedulerAgent) on a fixed interval
so the fleet is managed without any manual API calls.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..agents.orchestrator import OrchestrationResult

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    latitude: float | None = None   # derived from fleet centroid if None
    longitude: float | None = None  # derived from fleet centroid if None
    radius_km: float = 10.0
    hours_ahead: int = 12
    interval_seconds: int = 30


@dataclass
class LoopStatus:
    running: bool = False
    cycle_count: int = 0
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    config: Optional[LoopConfig] = None
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "cycle_count": self.cycle_count,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "config": {
                "latitude": self.config.latitude or "auto (fleet centroid)",
                "longitude": self.config.longitude or "auto (fleet centroid)",
                "radius_km": self.config.radius_km,
                "interval_seconds": self.config.interval_seconds,
            } if self.config else None,
            "recent_cycles": self.history[-5:],  # last 5 cycles
        }


class AutonomousLoop:
    """
    Wraps the OrchestratorAgent in an asyncio task that fires every N seconds.
    Call start() to begin, stop() to cancel.
    """

    def __init__(self, orchestrator) -> None:
        self._orchestrator = orchestrator
        self._task: Optional[asyncio.Task] = None
        self.status = LoopStatus()

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, config: LoopConfig) -> None:
        if self.is_running():
            logger.warning("AutonomousLoop already running — stop it first.")
            return

        self.status.config = config
        self.status.running = True
        self.status.last_error = None
        self._task = asyncio.create_task(self._loop(config))
        logger.info(
            "AutonomousLoop started — centre=(%.4f, %.4f), interval=%ds",
            config.latitude, config.longitude, config.interval_seconds,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.status.running = False
        self._task = None
        logger.info("AutonomousLoop stopped after %d cycle(s).", self.status.cycle_count)

    async def _loop(self, config: LoopConfig) -> None:
        while True:
            await self._run_cycle(config)
            await asyncio.sleep(config.interval_seconds)

    async def _run_cycle(self, config: LoopConfig) -> None:
        self.status.last_run_at = datetime.utcnow()
        self.status.cycle_count += 1
        cycle_num = self.status.cycle_count

        logger.info("AutonomousLoop — starting cycle #%d", cycle_num)
        try:
            result: OrchestrationResult = await self._orchestrator.run_cycle(
                latitude=config.latitude,
                longitude=config.longitude,
                radius_km=config.radius_km,
                hours_ahead=config.hours_ahead,
            )
            self.status.last_error = None
            summary = {
                "cycle": cycle_num,
                "timestamp": self.status.last_run_at.isoformat(),
                "events_found": len(result.discovered_events),
                "schedules_created": len(result.schedules),
                "errors": result.errors,
            }
            self.status.history.append(summary)
            logger.info(
                "AutonomousLoop — cycle #%d complete: %d event(s), %d schedule(s)",
                cycle_num, len(result.discovered_events), len(result.schedules),
            )
        except Exception as exc:
            self.status.last_error = str(exc)
            logger.error("AutonomousLoop — cycle #%d failed: %s", cycle_num, exc)
