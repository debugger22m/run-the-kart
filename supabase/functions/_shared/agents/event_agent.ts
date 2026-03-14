/**
 * EventAgent
 *
 * Discovers high-value local events near the fleet's operating area using web search
 * and returns demand-scored event data for the SchedulerAgent to act on.
 *
 * Tools:
 *   - web_search (built-in Claude tool — server-side, no client handler needed)
 *   - forecast_demand (DemandForecastingSkill)
 *   - score_event_opportunity (DemandForecastingSkill)
 */

import Anthropic from "npm:@anthropic-ai/sdk";
import { BaseAgent } from "./base.ts";
import {
  DEMAND_FORECASTING_TOOLS,
  DEMAND_FORECASTING_PROMPT_MODULE,
  handleDemandForecastingTool,
} from "../skills/demand_forecasting.ts";
import type { EventData } from "../types.ts";

// ---------------------------------------------------------------------------
// System prompt (ported from Python EventAgent)
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT = `\
You are a revenue-maximisation scout for an autonomous food truck fleet. Your single
goal is to identify the highest-revenue deployment opportunities for today and return
them as machine-readable JSON so the scheduling system can act immediately.

## Step 1 — Discover events via web search

Search for real events happening today near the target coordinates. Try 2-3 searches
covering different event types, for example:
- "[date] events today [city/neighbourhood]"
- "concerts festivals [date] [city]"
- "farmers markets sports games [date] [city]"

Extract every event you find: name, venue, start/end time, category, estimated attendance.

## Step 2 — Geocode venues

Assign latitude and longitude to each event. Use your knowledge of well-known venues.
Common SF reference points:
- Chase Center: 37.7680, -122.3877
- Oracle Park: 37.7786, -122.3893
- Golden Gate Park: 37.7694, -122.4862
- Moscone Center: 37.7845, -122.4008
- Ferry Building: 37.7956, -122.3933
- Civic Center / Market St: 37.7793, -122.4193
- Bill Graham Civic Auditorium: 37.7784, -122.4177
- The Fillmore: 37.7840, -122.4330
- Pier 39 / Fisherman's Wharf: 37.8087, -122.4098
- Union Square: 37.7879, -122.4074
- Yerba Buena Center: 37.7845, -122.4025
- Castro Theatre: 37.7620, -122.4350

No null coordinates are permitted. If you cannot determine coordinates, exclude the event.

## Step 3 — Estimate attendance

Attendance is rarely stated directly. Estimate using:
- Venue capacity (e.g., 20,000-seat arena at 80% = 16,000)
- Event type baselines: farmers market 500-2,000; street fair 2,000-10,000;
  major concert 5,000-50,000; conference 500-5,000; parade 10,000-100,000
- Historical data for recurring events
- Any ticket counts or registration numbers mentioned

Never leave attendance as null or 0. Always make your best informed estimate.
Discard events with expected_attendance < 200.

## Step 4 — Score each event

Call \`forecast_demand\` for ALL events in a single batch, then call \`score_event_opportunity\`
for ALL events in a single batch. Do not interleave — batch each tool across all events before
moving to the next tool. Discard events with opportunity_score < 40.

## Step 5 — Return results

Return ONLY a JSON array sorted by opportunity_score descending.
No markdown fences, no text before or after the array. Each element must have exactly:
{
  "id": "evt_001",
  "name": "Event Name",
  "location_name": "Venue Name",
  "latitude": 37.7786,
  "longitude": -122.3893,
  "expected_attendance": 8000,
  "start_time": "2026-03-14T12:00:00-07:00",
  "end_time": "2026-03-14T16:00:00-07:00",
  "category": "sports",
  "estimated_customers": 800,
  "estimated_revenue_high": 8000.0,
  "demand_score": 100.0,
  "opportunity_score": 100.0
}`;

// ---------------------------------------------------------------------------
// EventAgent class
// ---------------------------------------------------------------------------

export class EventAgent extends BaseAgent {
  constructor() {
    // Combine built-in web_search tool with demand forecasting skill tools
    const webSearchTool = {
      type: "web_search_20250305",
      name: "web_search",
      max_uses: 5,
    } as unknown as Anthropic.Tool;

    const allTools: Anthropic.Tool[] = [webSearchTool, ...DEMAND_FORECASTING_TOOLS];

    super({
      name: "EventAgent",
      // Append demand forecasting prompt module to the base system prompt
      systemPrompt: `${SYSTEM_PROMPT}\n\n${DEMAND_FORECASTING_PROMPT_MODULE}`,
      tools: allTools,
      maxIterations: 20,
    });
  }

  /**
   * Handle tool calls that belong to this agent.
   * web_search is server-side (handled by Claude), so only demand forecasting
   * tools need client-side handlers.
   */
  protected async handleOwnToolCall(
    toolName: string,
    input: Record<string, unknown>,
  ): Promise<string> {
    if (toolName === "forecast_demand" || toolName === "score_event_opportunity") {
      return handleDemandForecastingTool(toolName, input);
    }
    // web_search is handled server-side by Claude; any other tool is unknown
    return JSON.stringify({ error: `Unknown tool: ${toolName}` });
  }

  /**
   * Discover, score, and rank today's events near a location via web search.
   * Returns events sorted by opportunity_score descending.
   */
  async findEvents(
    latitude: number,
    longitude: number,
    dateFrom: string,
    dateTo: string,
    radiusKm = 10.0,
  ): Promise<EventData[]> {
    const task =
      `Find and score today's best events for food truck deployment near ` +
      `(${latitude}, ${longitude}) within ${radiusKm} km. ` +
      `Today is ${dateFrom}.`;

    const rawResponse = await this.run(task);

    try {
      const start = rawResponse.indexOf("[");
      const end = rawResponse.lastIndexOf("]") + 1;
      if (start !== -1 && end > start) {
        return JSON.parse(rawResponse.slice(start, end)) as EventData[];
      }
    } catch (err) {
      console.error(
        `[EventAgent] Response parse error: ${err}\nRaw: ${rawResponse.slice(0, 500)}`,
      );
    }

    return [];
  }
}
