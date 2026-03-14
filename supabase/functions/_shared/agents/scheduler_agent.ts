/**
 * SchedulerAgent
 *
 * Takes demand-scored events from the EventAgent and the current fleet state,
 * then assigns carts to maximise total fleet revenue — preventing conflicts
 * and ensuring balanced geographic coverage.
 *
 * Runs in reasoning-only mode (no tool calls) — pure JSON output in one shot.
 */

import { BaseAgent } from "./base.ts";
import type { Fleet, EventData, Schedule, ScheduleEvent } from "../types.ts";

// ---------------------------------------------------------------------------
// System prompt (ported from Python SchedulerAgent)
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT = `\
You are the Scheduler Agent for an autonomous food truck fleet management system in Salt Lake City, UT.

You receive pre-scored events (highest opportunity_score first) and available carts with GPS coordinates.
Your goal: produce the optimal cart-to-event assignment to maximise TOTAL fleet revenue.

Assignment rules:
- Assign the geographically nearest idle cart to each top-scored event.
- Allow two carts at an event only if expected_attendance > 5000.
- Never double-book a cart (each cart_id may appear at most once).
- Prefer geographic spread — avoid clustering all carts at one venue.
- Only assign as many carts as there are events (cap at fleet size).

Output ONLY a valid JSON array — no prose, no markdown fences.
Each object must include:
  cart_id, event_id, event_name, destination_lat, destination_lng,
  arrival_time (ISO), departure_time (ISO), estimated_revenue, opportunity_score`;

// ---------------------------------------------------------------------------
// SchedulerAgent class
// ---------------------------------------------------------------------------

export class SchedulerAgent extends BaseAgent {
  constructor() {
    super({
      name: "SchedulerAgent",
      systemPrompt: SYSTEM_PROMPT,
      tools: [], // reasoning-only — no tool calls, one-shot JSON output
      maxIterations: 3,
    });
  }

  /**
   * No tools in reasoning-only mode.
   */
  protected async handleOwnToolCall(
    toolName: string,
    _input: Record<string, unknown>,
  ): Promise<string> {
    return JSON.stringify({ error: `No tools in reasoning-only mode: ${toolName}` });
  }

  /**
   * Assign carts to events in a single LLM turn — no tool calls, pure JSON output.
   */
  async createSchedules(fleet: Fleet, events: EventData[]): Promise<Schedule[]> {
    const availableCarts = Array.from(fleet.carts.values()).filter(
      (c) => c.status === "idle",
    );

    if (availableCarts.length === 0) {
      console.warn("[SchedulerAgent] No available carts in fleet.");
      return [];
    }

    const now = new Date().toISOString();
    const cartSummaries = availableCarts.map((c) => ({
      cart_id: c.id,
      name: c.name,
      lat: c.current_location?.lat ?? 0.0,
      lng: c.current_location?.lng ?? 0.0,
    }));

    const task =
      `Current UTC time: ${now}\n\n` +
      `Available carts (${cartSummaries.length}):\n${JSON.stringify(cartSummaries, null, 2)}\n\n` +
      `Events to cover (${events.length}, best first):\n${JSON.stringify(events, null, 2)}\n\n` +
      `Assign each idle cart to the best nearby event. ` +
      `Output ONLY a JSON array. No explanation, no markdown. ` +
      `Each element: {cart_id, event_id, event_name, destination_lat, destination_lng, ` +
      `arrival_time, departure_time, estimated_revenue, opportunity_score}`;

    const rawResponse = await this.run(task);

    // Strip markdown fences if present, then find the JSON array
    let cleaned = rawResponse.trim();
    if (cleaned.startsWith("```")) {
      const lines = cleaned.split("\n");
      cleaned = lines.slice(1).join("\n");
    }
    if (cleaned.endsWith("```")) {
      const lines = cleaned.split("\n");
      cleaned = lines.slice(0, -1).join("\n");
    }

    let assignments: Record<string, unknown>[] = [];
    try {
      const start = cleaned.indexOf("[");
      const end = cleaned.lastIndexOf("]") + 1;
      if (start !== -1 && end > start) {
        assignments = JSON.parse(cleaned.slice(start, end));
      } else {
        console.error(
          `[SchedulerAgent] No JSON array found in response: ${cleaned.slice(0, 300)}`,
        );
        return [];
      }
    } catch (err) {
      console.error(`[SchedulerAgent] Parse error: ${err}\nRaw: ${cleaned.slice(0, 300)}`);
      return [];
    }

    const schedules: Schedule[] = [];
    for (const assignment of assignments) {
      try {
        const schedule = this._buildSchedule(assignment, events);
        if (schedule) {
          schedules.push(schedule);
        }
      } catch (err) {
        console.error(
          `[SchedulerAgent] Failed to build schedule from assignment ${JSON.stringify(assignment)}: ${err}`,
        );
      }
    }

    return schedules;
  }

  private _buildSchedule(
    assignment: Record<string, unknown>,
    events: EventData[],
  ): Schedule | null {
    const eventId = assignment["event_id"] as string | undefined;
    const eventData = events.find((e) => e.id === eventId);

    if (!eventData) {
      console.warn(`[SchedulerAgent] No matching event found for event_id=${eventId}`);
      return null;
    }

    const scheduleEvent: ScheduleEvent = {
      id: eventData.id,
      name: eventData.name,
      location_name: eventData.location_name ?? "",
      coordinates: {
        lat: (assignment["destination_lat"] as number) ?? eventData.latitude,
        lng: (assignment["destination_lng"] as number) ?? eventData.longitude,
      },
      expected_attendance: eventData.expected_attendance,
      start_time: new Date(eventData.start_time),
      end_time: new Date(eventData.end_time),
      category: eventData.category,
    };

    // DEMO_EXPIRE_SECS: short-circuit departure_time so carts recycle quickly in demos.
    // Set DEMO_EXPIRE_SECS=45 in env to see autonomous reassignment every ~45 seconds.
    const demoSecsStr = Deno.env.get("DEMO_EXPIRE_SECS") ?? "0";
    const demoSecs = parseInt(demoSecsStr, 10);
    let departureTime: Date;
    if (demoSecs > 0) {
      departureTime = new Date(Date.now() + demoSecs * 1000);
    } else {
      const depStr = (assignment["departure_time"] as string) ?? eventData.end_time;
      departureTime = new Date(depStr);
    }

    const arrivalStr = (assignment["arrival_time"] as string) ?? eventData.start_time;

    return {
      id: crypto.randomUUID(),
      cart_id: assignment["cart_id"] as string,
      event: scheduleEvent,
      arrival_time: new Date(arrivalStr),
      departure_time: departureTime,
      status: "confirmed",
      estimated_revenue: assignment["estimated_revenue"] as number | undefined,
      created_at: new Date(),
    };
  }
}
