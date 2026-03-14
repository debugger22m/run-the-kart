import Anthropic from "npm:@anthropic-ai/sdk";

// ---------------------------------------------------------------------------
// Tool definitions (Anthropic format)
// ---------------------------------------------------------------------------

export const FLEET_OPTIMIZATION_TOOLS: Anthropic.Tool[] = [
  {
    name: "check_assignment_conflicts",
    description:
      "Check whether a proposed cart assignment conflicts with existing assignments. " +
      "Returns whether the cart is free and any conflicting schedule details.",
    input_schema: {
      type: "object" as const,
      properties: {
        cart_id: { type: "string" },
        proposed_start: {
          type: "string",
          description: "ISO datetime string for proposed arrival",
        },
        proposed_end: {
          type: "string",
          description: "ISO datetime string for proposed departure",
        },
        existing_assignments: {
          type: "array",
          description: "List of already-confirmed assignments for this cart",
          items: {
            type: "object",
            properties: {
              cart_id: { type: "string" },
              arrival_time: { type: "string" },
              departure_time: { type: "string" },
              event_name: { type: "string" },
            },
          },
        },
      },
      required: ["cart_id", "proposed_start", "proposed_end", "existing_assignments"],
    },
  },
  {
    name: "calculate_opportunity_cost",
    description:
      "Given two competing assignments for the same cart, calculate which one " +
      "yields higher net value after accounting for travel time lost.",
    input_schema: {
      type: "object" as const,
      properties: {
        cart_id: { type: "string" },
        option_a: {
          type: "object",
          properties: {
            event_id: { type: "string" },
            estimated_revenue: { type: "number" },
            travel_minutes: { type: "number" },
            opportunity_score: { type: "number" },
          },
          required: ["event_id", "estimated_revenue", "travel_minutes", "opportunity_score"],
        },
        option_b: {
          type: "object",
          properties: {
            event_id: { type: "string" },
            estimated_revenue: { type: "number" },
            travel_minutes: { type: "number" },
            opportunity_score: { type: "number" },
          },
          required: ["event_id", "estimated_revenue", "travel_minutes", "opportunity_score"],
        },
      },
      required: ["cart_id", "option_a", "option_b"],
    },
  },
  {
    name: "check_coverage_balance",
    description:
      "Given a proposed set of assignments, check whether the fleet is spread " +
      "across the operating area or clustered. Returns a balance score and recommendations.",
    input_schema: {
      type: "object" as const,
      properties: {
        assignments: {
          type: "array",
          items: {
            type: "object",
            properties: {
              cart_id: { type: "string" },
              event_id: { type: "string" },
              latitude: { type: "number" },
              longitude: { type: "number" },
              estimated_revenue: { type: "number" },
            },
            required: ["cart_id", "event_id", "latitude", "longitude"],
          },
        },
      },
      required: ["assignments"],
    },
  },
];

// ---------------------------------------------------------------------------
// Tool handlers (pure computation, no async)
// ---------------------------------------------------------------------------

interface ExistingAssignment {
  cart_id: string;
  arrival_time: string;
  departure_time: string;
  event_name?: string;
}

interface OpportunityOption {
  event_id: string;
  estimated_revenue: number;
  travel_minutes: number;
  opportunity_score: number;
}

interface CoverageAssignment {
  cart_id: string;
  event_id: string;
  latitude: number;
  longitude: number;
  estimated_revenue?: number;
}

function checkAssignmentConflicts(input: Record<string, unknown>): Record<string, unknown> {
  const cartId = input["cart_id"] as string;
  const proposedStart = new Date(input["proposed_start"] as string);
  const proposedEnd = new Date(input["proposed_end"] as string);
  const existing = (input["existing_assignments"] as ExistingAssignment[]) ?? [];

  const conflicts: Record<string, unknown>[] = [];
  for (const a of existing) {
    if (a.cart_id !== cartId) continue;
    const aStart = new Date(a.arrival_time);
    const aEnd = new Date(a.departure_time);
    // Overlap: proposed starts before existing ends AND proposed ends after existing starts
    if (proposedStart < aEnd && proposedEnd > aStart) {
      conflicts.push({
        conflicting_event: a.event_name ?? null,
        conflict_start: a.arrival_time,
        conflict_end: a.departure_time,
      });
    }
  }

  return {
    cart_id: cartId,
    is_free: conflicts.length === 0,
    conflicts,
  };
}

function calculateOpportunityCost(input: Record<string, unknown>): Record<string, unknown> {
  const cartId = input["cart_id"] as string;
  const optA = input["option_a"] as OpportunityOption;
  const optB = input["option_b"] as OpportunityOption;

  // Travel penalty: each minute of travel = ~$0.50 opportunity cost
  const travelPenaltyPerMin = 0.50;

  const netA = optA.estimated_revenue - optA.travel_minutes * travelPenaltyPerMin;
  const netB = optB.estimated_revenue - optB.travel_minutes * travelPenaltyPerMin;

  // Weight by opportunity score (0-100)
  const weightedA = netA * (optA.opportunity_score / 100);
  const weightedB = netB * (optB.opportunity_score / 100);

  const winner = weightedA >= weightedB ? "option_a" : "option_b";

  return {
    cart_id: cartId,
    recommended: winner,
    option_a: {
      event_id: optA.event_id,
      net_value: Math.round(netA * 100) / 100,
      weighted_value: Math.round(weightedA * 100) / 100,
    },
    option_b: {
      event_id: optB.event_id,
      net_value: Math.round(netB * 100) / 100,
      weighted_value: Math.round(weightedB * 100) / 100,
    },
  };
}

function checkCoverageBalance(input: Record<string, unknown>): Record<string, unknown> {
  const assignments = (input["assignments"] as CoverageAssignment[]) ?? [];

  if (assignments.length < 2) {
    return {
      balance_score: 100,
      recommendation: "Only one assignment — no balance check needed.",
    };
  }

  const lats = assignments.map((a) => a.latitude);
  const lngs = assignments.map((a) => a.longitude);

  const latSpread = Math.max(...lats) - Math.min(...lats);
  const lngSpread = Math.max(...lngs) - Math.min(...lngs);

  // Spread in degrees: > 0.05 (~5 km) is reasonable coverage
  const spreadScore = Math.min(100, Math.round(((latSpread + lngSpread) / 0.1) * 100));
  const totalRevenue = assignments.reduce((sum, a) => sum + (a.estimated_revenue ?? 0), 0);

  const recommendation =
    spreadScore >= 50
      ? "Good geographic spread across the fleet."
      : "Carts are clustered — consider reassigning one cart to a more distant event.";

  return {
    balance_score: spreadScore,
    lat_spread_deg: Math.round(latSpread * 10000) / 10000,
    lng_spread_deg: Math.round(lngSpread * 10000) / 10000,
    total_estimated_revenue: Math.round(totalRevenue * 100) / 100,
    recommendation,
  };
}

export function handleFleetOptimizationTool(
  toolName: string,
  input: Record<string, unknown>,
): string {
  try {
    if (toolName === "check_assignment_conflicts") {
      return JSON.stringify(checkAssignmentConflicts(input));
    }
    if (toolName === "calculate_opportunity_cost") {
      return JSON.stringify(calculateOpportunityCost(input));
    }
    if (toolName === "check_coverage_balance") {
      return JSON.stringify(checkCoverageBalance(input));
    }
    return JSON.stringify({ error: `Unknown fleet optimization tool: ${toolName}` });
  } catch (err) {
    return JSON.stringify({ error: String(err) });
  }
}

// ---------------------------------------------------------------------------
// Prompt module
// NOTE: SchedulerAgent runs in reasoning-only mode (no tools) so this module
// is NOT included in its system prompt. Defined here for completeness.
// ---------------------------------------------------------------------------

export const FLEET_OPTIMIZATION_PROMPT_MODULE = `
## Fleet Optimization Skill
You have access to fleet optimization tools. Use them to:
- Call \`check_assignment_conflicts\` before finalizing any cart-to-event assignment
  to ensure no cart is double-booked.
- Call \`calculate_opportunity_cost\` to compare assignments and always pick the
  combination that maximises TOTAL fleet revenue, not just individual event revenue.
- Call \`check_coverage_balance\` to ensure the fleet isn't clustered in one area —
  spread carts across events in different locations where possible.
- Never assign more than one cart to the same event unless the event attendance > 3000.
- Always resolve conflicts by choosing the assignment with the higher opportunity_score.
`.trim();
