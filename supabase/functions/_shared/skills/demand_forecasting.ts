import Anthropic from "npm:@anthropic-ai/sdk";

// ---------------------------------------------------------------------------
// Tool definitions (Anthropic format)
// ---------------------------------------------------------------------------

export const DEMAND_FORECASTING_TOOLS: Anthropic.Tool[] = [
  {
    name: "forecast_demand",
    description:
      "Forecast food truck customer demand for an event based on its type and attendance. " +
      "Returns estimated customers, average order value, and a raw demand score (0-100).",
    input_schema: {
      type: "object" as const,
      properties: {
        event_id: { type: "string" },
        event_category: {
          type: "string",
          description: "Event type: market, conference, music, food, sports, festival, etc.",
        },
        expected_attendance: { type: "integer" },
        duration_hours: {
          type: "number",
          description: "How long the event runs in hours",
        },
      },
      required: ["event_id", "event_category", "expected_attendance", "duration_hours"],
    },
  },
  {
    name: "score_event_opportunity",
    description:
      "Combine raw demand with time-of-day and event duration to produce a final " +
      "opportunity score (0-100). Higher is better for deployment.",
    input_schema: {
      type: "object" as const,
      properties: {
        event_id: { type: "string" },
        demand_score: {
          type: "number",
          description: "Raw demand score from forecast_demand",
        },
        start_hour: {
          type: "integer",
          description: "Hour of day the event starts (0-23, UTC)",
        },
        duration_hours: { type: "number" },
        estimated_revenue: {
          type: "number",
          description: "High-end revenue estimate in USD",
        },
      },
      required: [
        "event_id",
        "demand_score",
        "start_hour",
        "duration_hours",
        "estimated_revenue",
      ],
    },
  },
];

// ---------------------------------------------------------------------------
// Category profiles (direct port from Python)
// ---------------------------------------------------------------------------

interface CategoryProfile {
  conversion: number;
  avg_order: number;
}

const CATEGORY_PROFILE: Record<string, CategoryProfile> = {
  music:      { conversion: 0.12, avg_order: 14.0 },
  conference: { conversion: 0.09, avg_order: 16.0 },
  market:     { conversion: 0.14, avg_order: 11.0 },
  food:       { conversion: 0.08, avg_order: 13.0 },
  festival:   { conversion: 0.15, avg_order: 12.0 },
  sports:     { conversion: 0.10, avg_order: 10.0 },
};

const DEFAULT_PROFILE: CategoryProfile = { conversion: 0.08, avg_order: 11.0 };

// ---------------------------------------------------------------------------
// Tool handlers (pure computation, no async)
// ---------------------------------------------------------------------------

function forecastDemand(input: Record<string, unknown>): Record<string, unknown> {
  const eventId = input["event_id"] as string;
  const category = ((input["event_category"] as string) ?? "").toLowerCase();
  const attendance = input["expected_attendance"] as number;
  const durationHours = input["duration_hours"] as number;

  const profile = CATEGORY_PROFILE[category] ?? DEFAULT_PROFILE;
  const estimatedCustomers = Math.floor(attendance * profile.conversion);
  const estimatedRevenue = Math.round(estimatedCustomers * profile.avg_order * 100) / 100;

  const customersPerHour = estimatedCustomers / Math.max(durationHours, 1);
  const demandScore = Math.min(100, Math.round(customersPerHour * 2 * 10) / 10);

  return {
    event_id: eventId,
    estimated_customers: estimatedCustomers,
    avg_order_value: profile.avg_order,
    estimated_revenue: estimatedRevenue,
    demand_score: demandScore,
  };
}

function scoreEventOpportunity(input: Record<string, unknown>): Record<string, unknown> {
  const eventId = input["event_id"] as string;
  const demandScore = input["demand_score"] as number;
  const startHour = input["start_hour"] as number;
  const durationHours = input["duration_hours"] as number;
  const estimatedRevenue = input["estimated_revenue"] as number;

  // Peak meal hours (11-14, 17-21) get a bonus
  let timeBonus: number;
  if ((startHour >= 11 && startHour <= 14) || (startHour >= 17 && startHour <= 21)) {
    timeBonus = 15;
  } else if (startHour >= 9 && startHour <= 16) {
    timeBonus = 5;
  } else {
    timeBonus = -10; // late night / early morning penalty
  }

  // Longer events give more serving time (capped at 6h bonus = 10 pts)
  const durationBonus = durationHours > 2 ? Math.min(10, (durationHours - 2) * 2) : 0;

  // Revenue floor bonus — high revenue events get a small push
  const revenueBonus = Math.min(10, Math.log10(Math.max(estimatedRevenue, 1)) * 2);

  const rawScore = demandScore + timeBonus + durationBonus + revenueBonus;
  const opportunityScore = Math.round(Math.min(100, Math.max(0, rawScore)) * 10) / 10;

  return {
    event_id: eventId,
    opportunity_score: opportunityScore,
    breakdown: {
      demand_score: demandScore,
      time_bonus: timeBonus,
      duration_bonus: durationBonus,
      revenue_bonus: Math.round(revenueBonus * 10) / 10,
    },
  };
}

export function handleDemandForecastingTool(
  toolName: string,
  input: Record<string, unknown>,
): string {
  try {
    if (toolName === "forecast_demand") {
      return JSON.stringify(forecastDemand(input));
    }
    if (toolName === "score_event_opportunity") {
      return JSON.stringify(scoreEventOpportunity(input));
    }
    return JSON.stringify({ error: `Unknown demand forecasting tool: ${toolName}` });
  } catch (err) {
    return JSON.stringify({ error: String(err) });
  }
}

// ---------------------------------------------------------------------------
// Prompt module injected into EventAgent system prompt
// ---------------------------------------------------------------------------

export const DEMAND_FORECASTING_PROMPT_MODULE = `
## Demand Forecasting Skill
You have access to demand forecasting tools. Use them to:
- Call \`forecast_demand\` for every event you discover to get a revenue score.
- Call \`score_event_opportunity\` to combine demand with practical factors (duration, time of day).
- Only pass events with an opportunity_score >= 40 to the final ranked list.
- Always sort your final answer by opportunity_score descending so the Scheduler
  picks the highest-value events first.
`.trim();
