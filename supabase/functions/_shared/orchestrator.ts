/**
 * Orchestrator — stateless autonomous coordinator for the food truck fleet.
 *
 * Each cycle:
 *   1. Auto-expires schedules whose departure_time has passed → carts return to idle.
 *   2. Derives search centre from options or fleet centroid.
 *   3. Runs EventAgent to discover and score today's events.
 *   4. Runs SchedulerAgent to assign idle carts to the best events.
 *   5. Applies assignments to the in-memory fleet Map.
 *
 * The caller (edge function) is responsible for all DB reads and writes:
 *   - Load fleet before calling runOrchestrationCycle
 *   - Write newSchedules to DB via createScheduleInDB
 *   - Update cart statuses via updateCart
 *   - Mark expired schedules via updateScheduleStatus
 *   - Log the run via saveOrchestrationRun
 */

import { EventAgent } from "./agents/event_agent.ts";
import { SchedulerAgent } from "./agents/scheduler_agent.ts";
import { getAvailableCarts, fleetSummary } from "./db.ts";
import type {
  Fleet,
  Schedule,
  ScheduleSummary,
  OrchestrationResult,
  EventData,
} from "./types.ts";

export interface OrchestratorOptions {
  radiusKm?: number;
  hoursAhead?: number;
  lat?: number;
  lng?: number;
}

function scheduleToSummary(schedule: Schedule): ScheduleSummary {
  return {
    schedule_id: schedule.id,
    cart_id: schedule.cart_id,
    event_name: schedule.event.name,
    location: schedule.event.location_name,
    coordinates: schedule.event.coordinates,
    arrival_time: schedule.arrival_time.toISOString(),
    departure_time: schedule.departure_time.toISOString(),
    status: schedule.status,
    estimated_revenue: schedule.estimated_revenue,
    category: schedule.event.category,
  };
}

/**
 * Compute the average lat/lng of all carts that have a known location.
 * Falls back to downtown SLC if no located carts exist.
 */
function fleetCentroid(fleet: Fleet): [number, number] {
  const located = Array.from(fleet.carts.values()).filter(
    (c) => c.current_location != null,
  );
  if (located.length === 0) {
    return [40.7608, -111.891]; // Downtown SLC fallback
  }
  const lat = located.reduce((sum, c) => sum + c.current_location!.lat, 0) / located.length;
  const lng = located.reduce((sum, c) => sum + c.current_location!.lng, 0) / located.length;
  return [lat, lng];
}

/**
 * Run one full autonomous orchestration cycle.
 *
 * @param fleet            In-memory fleet loaded from DB (mutated in place).
 * @param activeSchedules  Current active schedules loaded from DB.
 * @param options          Optional search centre and radius overrides.
 *
 * @returns result          OrchestrationResult for the dashboard / logging.
 * @returns newSchedules    Newly created Schedule objects (caller persists to DB).
 * @returns expiredScheduleIds  IDs of schedules that have expired (caller updates DB status).
 */
export async function runOrchestrationCycle(
  fleet: Fleet,
  activeSchedules: Schedule[],
  options: OrchestratorOptions = {},
): Promise<{
  result: OrchestrationResult;
  newSchedules: Schedule[];
  expiredScheduleIds: string[];
}> {
  const errors: string[] = [];
  const now = new Date();

  // -------------------------------------------------------------------------
  // Step 1: Expire schedules whose departure_time has passed
  // -------------------------------------------------------------------------
  const expiredScheduleIds: string[] = [];
  for (const schedule of activeSchedules) {
    if (schedule.departure_time <= now) {
      expiredScheduleIds.push(schedule.id);

      // Return the corresponding cart to idle in the in-memory fleet
      const cart = fleet.carts.get(schedule.cart_id);
      if (cart) {
        cart.status = "idle";
        cart.assigned_schedule_id = undefined;
      }
    }
  }

  if (expiredScheduleIds.length > 0) {
    console.log(
      `[Orchestrator] Auto-expired ${expiredScheduleIds.length} schedule(s) — carts returned to idle.`,
    );
  }

  // -------------------------------------------------------------------------
  // Step 2: Derive search centre
  // -------------------------------------------------------------------------
  let searchLat: number;
  let searchLng: number;

  if (options.lat != null && options.lng != null) {
    searchLat = options.lat;
    searchLng = options.lng;
    console.log(
      `[Orchestrator] Using provided coordinates — (${searchLat.toFixed(4)}, ${searchLng.toFixed(4)})`,
    );
  } else {
    [searchLat, searchLng] = fleetCentroid(fleet);
    console.log(
      `[Orchestrator] Using fleet centroid — (${searchLat.toFixed(4)}, ${searchLng.toFixed(4)})`,
    );
  }

  const radiusKm = options.radiusKm ?? 10.0;
  const hoursAhead = options.hoursAhead ?? 12;

  const dateFrom = now.toISOString().slice(0, 10); // YYYY-MM-DD
  const dateToDate = new Date(now.getTime() + hoursAhead * 60 * 60 * 1000);
  const dateTo = dateToDate.toISOString().slice(0, 10);

  console.log(
    `[Orchestrator] Cycle start — centre=(${searchLat.toFixed(4)}, ${searchLng.toFixed(4)}) ` +
      `radius=${radiusKm}km idle_carts=${getAvailableCarts(fleet).length}`,
  );

  // -------------------------------------------------------------------------
  // Step 3: Discover events via EventAgent
  // -------------------------------------------------------------------------
  let discoveredEvents: EventData[] = [];
  try {
    const eventAgent = new EventAgent();
    discoveredEvents = await eventAgent.findEvents(
      searchLat,
      searchLng,
      dateFrom,
      dateTo,
      radiusKm,
    );
    console.log(`[Orchestrator] ${discoveredEvents.length} event(s) discovered.`);
  } catch (err) {
    const msg = `EventAgent error: ${err}`;
    console.error(`[Orchestrator] ${msg}`);
    errors.push(msg);
  }

  // -------------------------------------------------------------------------
  // Step 4: Assign idle carts to events via SchedulerAgent
  // -------------------------------------------------------------------------
  let newSchedules: Schedule[] = [];
  const availableCarts = getAvailableCarts(fleet);

  if (availableCarts.length === 0) {
    console.log("[Orchestrator] All carts busy — skipping scheduling this cycle.");
  } else if (discoveredEvents.length === 0) {
    console.log("[Orchestrator] No events found — skipping scheduling this cycle.");
  } else {
    try {
      const schedulerAgent = new SchedulerAgent();
      newSchedules = await schedulerAgent.createSchedules(fleet, discoveredEvents);
      console.log(`[Orchestrator] ${newSchedules.length} new schedule(s) created.`);
    } catch (err) {
      const msg = `SchedulerAgent error: ${err}`;
      console.error(`[Orchestrator] ${msg}`);
      errors.push(msg);
    }
  }

  // -------------------------------------------------------------------------
  // Step 5: Apply new schedules to the in-memory fleet
  // -------------------------------------------------------------------------
  for (const schedule of newSchedules) {
    const cart = fleet.carts.get(schedule.cart_id);
    if (!cart) {
      console.warn(`[Orchestrator] Cart ${schedule.cart_id} not found in fleet.`);
      continue;
    }
    cart.status = "en_route";
    cart.current_location = schedule.event.coordinates;
    cart.assigned_schedule_id = schedule.id;

    console.log(
      `[Orchestrator] '${cart.name}' → '${schedule.event.name}' ` +
        `(departs ${schedule.departure_time.toISOString()})`,
    );
  }

  // -------------------------------------------------------------------------
  // Build result
  // -------------------------------------------------------------------------
  const result: OrchestrationResult = {
    timestamp: now.toISOString(),
    fleet_summary: fleetSummary(fleet),
    discovered_events: discoveredEvents,
    schedules: newSchedules.map(scheduleToSummary),
    expired_schedules: expiredScheduleIds.length,
    errors,
  };

  return { result, newSchedules, expiredScheduleIds };
}
