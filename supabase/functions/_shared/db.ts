import { createClient as _createClient, SupabaseClient } from "npm:@supabase/supabase-js@2";
import type {
  Cart,
  CartStatus,
  Fleet,
  Schedule,
  ScheduleSummary,
  LoopConfig,
  OrchestrationResult,
  EventData,
  FleetSummary,
} from "./types.ts";

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

export function createSupabaseClient(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set");
  }
  return _createClient(url, key);
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const DEFAULT_FLEET_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11";
export const DEFAULT_FLEET_NAME = "SLC-KartFleet";

// 10 demo carts across SLC staging zones: [name, lat, lng]
const DEMO_CARTS: Array<[string, number, number]> = [
  ["Kart-Pioneer",    40.7580, -111.9012],
  ["Kart-Gallivan",   40.7611, -111.8906],
  ["Kart-Gateway",    40.7694, -111.9018],
  ["Kart-Temple",     40.7708, -111.8958],
  ["Kart-Delta",      40.7683, -111.9012],
  ["Kart-Library",    40.7607, -111.8912],
  ["Kart-CityCreek",  40.7683, -111.8945],
  ["Kart-Trolley",    40.7497, -111.8780],
  ["Kart-RiceEccles", 40.7596, -111.8486],
  ["Kart-SugarHouse", 40.7239, -111.8583],
];

// ---------------------------------------------------------------------------
// Fleet helpers
// ---------------------------------------------------------------------------

function rowToCart(row: Record<string, unknown>): Cart {
  const lat = row["current_lat"] as number | null;
  const lng = row["current_lng"] as number | null;
  return {
    id: row["id"] as string,
    fleet_id: row["fleet_id"] as string | undefined,
    name: row["name"] as string,
    status: (row["status"] as CartStatus) ?? "idle",
    current_location:
      lat != null && lng != null ? { lat, lng } : undefined,
    max_orders_per_hour: (row["max_orders_per_hour"] as number) ?? 50,
    assigned_schedule_id: row["assigned_schedule_id"] as string | undefined,
  };
}

function cartToRow(cart: Cart, fleetId: string): Record<string, unknown> {
  return {
    id: cart.id,
    fleet_id: fleetId,
    name: cart.name,
    status: cart.status,
    current_lat: cart.current_location?.lat ?? null,
    current_lng: cart.current_location?.lng ?? null,
    max_orders_per_hour: cart.max_orders_per_hour,
    assigned_schedule_id: cart.assigned_schedule_id ?? null,
  };
}

/**
 * Load carts from DB. If none exist, seed DEMO_CARTS.
 * Also ensures the fleet row exists in the fleets table.
 */
export async function loadOrSeedFleet(
  client: SupabaseClient,
  fleetId: string = DEFAULT_FLEET_ID,
  fleetName: string = DEFAULT_FLEET_NAME,
): Promise<Fleet> {
  // Ensure fleet row exists
  const { data: fleetRows, error: fleetErr } = await client
    .from("fleets")
    .select("id")
    .eq("id", fleetId)
    .limit(1);

  if (fleetErr) {
    throw new Error(`loadOrSeedFleet: fleets query failed — ${fleetErr.message}`);
  }

  if (!fleetRows || fleetRows.length === 0) {
    const { error: insertErr } = await client.from("fleets").insert({
      id: fleetId,
      name: fleetName,
    });
    if (insertErr) {
      throw new Error(`loadOrSeedFleet: fleet insert failed — ${insertErr.message}`);
    }
  }

  // Load carts
  const { data: cartRows, error: cartErr } = await client
    .from("carts")
    .select("*")
    .eq("fleet_id", fleetId);

  if (cartErr) {
    throw new Error(`loadOrSeedFleet: carts query failed — ${cartErr.message}`);
  }

  const fleet: Fleet = {
    id: fleetId,
    name: fleetName,
    carts: new Map<string, Cart>(),
  };

  if (cartRows && cartRows.length > 0) {
    for (const row of cartRows) {
      const cart = rowToCart(row as Record<string, unknown>);
      fleet.carts.set(cart.id, cart);
    }
    return fleet;
  }

  // Seed demo carts
  const seedRows: Record<string, unknown>[] = [];
  const seededCarts: Cart[] = [];

  for (const [name, lat, lng] of DEMO_CARTS) {
    const cart: Cart = {
      id: crypto.randomUUID(),
      fleet_id: fleetId,
      name,
      status: "idle",
      current_location: { lat, lng },
      max_orders_per_hour: 50,
    };
    seededCarts.push(cart);
    seedRows.push(cartToRow(cart, fleetId));
  }

  const { error: seedErr } = await client.from("carts").insert(seedRows);
  if (seedErr) {
    throw new Error(`loadOrSeedFleet: cart seed failed — ${seedErr.message}`);
  }

  for (const cart of seededCarts) {
    fleet.carts.set(cart.id, cart);
  }

  return fleet;
}

export function getAvailableCarts(fleet: Fleet): Cart[] {
  return Array.from(fleet.carts.values()).filter((c) => c.status === "idle");
}

export function fleetSummary(fleet: Fleet): FleetSummary {
  const breakdown: Record<CartStatus, number> = {
    idle: 0,
    en_route: 0,
    serving: 0,
    maintenance: 0,
  };
  for (const cart of fleet.carts.values()) {
    breakdown[cart.status] = (breakdown[cart.status] ?? 0) + 1;
  }
  return {
    total_carts: fleet.carts.size,
    status_breakdown: breakdown,
  };
}

// ---------------------------------------------------------------------------
// Cart CRUD
// ---------------------------------------------------------------------------

export async function upsertCart(
  client: SupabaseClient,
  cart: Cart,
  fleetId: string,
): Promise<void> {
  const { error } = await client
    .from("carts")
    .upsert(cartToRow(cart, fleetId), { onConflict: "id" });
  if (error) {
    throw new Error(`upsertCart: ${error.message}`);
  }
}

export async function updateCart(
  client: SupabaseClient,
  cart: Partial<Cart> & { id: string },
): Promise<void> {
  const patch: Record<string, unknown> = {};
  if (cart.status !== undefined) patch["status"] = cart.status;
  if (cart.current_location !== undefined) {
    patch["current_lat"] = cart.current_location?.lat ?? null;
    patch["current_lng"] = cart.current_location?.lng ?? null;
  }
  if (cart.assigned_schedule_id !== undefined) {
    patch["assigned_schedule_id"] = cart.assigned_schedule_id ?? null;
  }

  const { error } = await client
    .from("carts")
    .update(patch)
    .eq("id", cart.id);
  if (error) {
    throw new Error(`updateCart: ${error.message}`);
  }
}

export async function deleteCart(
  client: SupabaseClient,
  cartId: string,
): Promise<void> {
  const { error } = await client.from("carts").delete().eq("id", cartId);
  if (error) {
    throw new Error(`deleteCart: ${error.message}`);
  }
}

// ---------------------------------------------------------------------------
// Schedule repository
// ---------------------------------------------------------------------------

export async function getActiveSchedulesFromDB(
  client: SupabaseClient,
): Promise<ScheduleSummary[]> {
  const { data, error } = await client
    .from("schedules")
    .select("*, events(*)")
    .in("status", ["confirmed", "in_progress"]);

  if (error) {
    throw new Error(`getActiveSchedulesFromDB: ${error.message}`);
  }

  if (!data) return [];

  return data.map((row: Record<string, unknown>) => {
    const event = row["events"] as Record<string, unknown> | null;
    return {
      schedule_id: row["id"] as string,
      cart_id: row["cart_id"] as string,
      event_name: (event?.["name"] as string) ?? "Unknown Event",
      location: (event?.["location_name"] as string) ?? "",
      coordinates: {
        lat: (event?.["lat"] as number) ?? 0,
        lng: (event?.["lng"] as number) ?? 0,
      },
      arrival_time: row["arrival_time"] as string,
      departure_time: row["departure_time"] as string,
      status: row["status"] as string,
      estimated_revenue: row["estimated_revenue"] as number | undefined,
      category: (event?.["category"] as string) ?? undefined,
    } satisfies ScheduleSummary;
  });
}

/**
 * Upsert the event row (by external_id), then insert the schedule row.
 */
export async function createScheduleInDB(
  client: SupabaseClient,
  schedule: Schedule,
  _fleetId: string,
): Promise<void> {
  const event = schedule.event;
  const externalId = event.id;

  // 1. Upsert event
  const { error: upsertErr } = await client.from("events").upsert(
    {
      external_id: externalId,
      name: event.name,
      location_name: event.location_name,
      lat: event.coordinates.lat,
      lng: event.coordinates.lng,
      expected_attendance: event.expected_attendance,
      start_time: event.start_time.toISOString(),
      end_time: event.end_time.toISOString(),
      category: event.category ?? null,
      source: "agent",
    },
    { onConflict: "external_id" },
  );
  if (upsertErr) {
    throw new Error(`createScheduleInDB: event upsert failed — ${upsertErr.message}`);
  }

  // 2. Retrieve the event's DB UUID
  const { data: eventRows, error: selectErr } = await client
    .from("events")
    .select("id")
    .eq("external_id", externalId)
    .limit(1);
  if (selectErr || !eventRows || eventRows.length === 0) {
    throw new Error(
      `createScheduleInDB: could not retrieve event UUID — ${selectErr?.message ?? "no row"}`,
    );
  }
  const eventDbId: string = (eventRows[0] as Record<string, unknown>)["id"] as string;

  // 3. Insert schedule
  const { error: scheduleErr } = await client.from("schedules").insert({
    id: schedule.id,
    cart_id: schedule.cart_id,
    event_id: eventDbId,
    arrival_time: schedule.arrival_time.toISOString(),
    departure_time: schedule.departure_time.toISOString(),
    status: schedule.status,
    estimated_revenue: schedule.estimated_revenue ?? null,
    notes: schedule.notes ?? null,
  });
  if (scheduleErr) {
    throw new Error(`createScheduleInDB: schedule insert failed — ${scheduleErr.message}`);
  }
}

export async function updateScheduleStatus(
  client: SupabaseClient,
  scheduleId: string,
  status: string,
): Promise<void> {
  const { error } = await client
    .from("schedules")
    .update({ status })
    .eq("id", scheduleId);
  if (error) {
    throw new Error(`updateScheduleStatus: ${error.message}`);
  }
}

// ---------------------------------------------------------------------------
// Event cache
// ---------------------------------------------------------------------------

/**
 * Check events table for events on `date` discovered within ttlHours.
 * Returns null on cache miss.
 */
export async function getCachedEvents(
  client: SupabaseClient,
  date: string,
  ttlHours = 4,
): Promise<EventData[] | null> {
  const cutoff = new Date(Date.now() - ttlHours * 60 * 60 * 1000).toISOString();

  const { data, error } = await client
    .from("events")
    .select("*")
    .gte("start_time", `${date}T00:00:00Z`)
    .lte("start_time", `${date}T23:59:59Z`)
    .gte("expected_attendance", 200)
    .gte("discovered_at", cutoff)
    .order("opportunity_score", { ascending: false });

  if (error) {
    throw new Error(`getCachedEvents: ${error.message}`);
  }

  if (!data || data.length === 0) return null;

  return data.map((row: Record<string, unknown>) => ({
    id: (row["external_id"] as string) ?? (row["id"] as string),
    name: row["name"] as string,
    location_name: row["location_name"] as string,
    latitude: row["lat"] as number,
    longitude: row["lng"] as number,
    expected_attendance: row["expected_attendance"] as number,
    start_time: row["start_time"] as string,
    end_time: row["end_time"] as string,
    category: row["category"] as string | undefined,
    demand_score: row["demand_score"] as number | undefined,
    opportunity_score: row["opportunity_score"] as number | undefined,
  }));
}

export async function cacheEvents(
  client: SupabaseClient,
  events: EventData[],
): Promise<void> {
  if (events.length === 0) return;

  const rows = events
    .filter((e) => !!e.id)
    .map((e) => ({
      external_id: e.id,
      name: e.name,
      location_name: e.location_name ?? "",
      lat: e.latitude,
      lng: e.longitude,
      expected_attendance: e.expected_attendance,
      start_time: e.start_time,
      end_time: e.end_time,
      category: e.category ?? null,
      source: "agent",
      demand_score: e.demand_score ?? null,
      opportunity_score: e.opportunity_score ?? null,
      discovered_at: new Date().toISOString(),
    }));

  if (rows.length === 0) return;

  const { error } = await client
    .from("events")
    .upsert(rows, { onConflict: "external_id" });
  if (error) {
    throw new Error(`cacheEvents: ${error.message}`);
  }
}

// ---------------------------------------------------------------------------
// Orchestration runs
// ---------------------------------------------------------------------------

export async function saveOrchestrationRun(
  client: SupabaseClient,
  fleetId: string,
  result: OrchestrationResult,
  searchLat: number,
  searchLng: number,
  radiusKm: number,
): Promise<void> {
  const { error } = await client.from("orchestration_runs").insert({
    fleet_id: fleetId,
    completed_at: new Date().toISOString(),
    search_lat: searchLat,
    search_lng: searchLng,
    radius_km: radiusKm,
    events_discovered: result.discovered_events.length,
    schedules_created: result.schedules.length,
    fleet_summary: result.fleet_summary,
    errors: result.errors,
  });
  if (error) {
    throw new Error(`saveOrchestrationRun: ${error.message}`);
  }
}

// ---------------------------------------------------------------------------
// Loop config (singleton row, id = 1)
// ---------------------------------------------------------------------------

const DEFAULT_LOOP_CONFIG: LoopConfig = {
  enabled: false,
  interval_seconds: 300,
  radius_km: 10,
  hours_ahead: 12,
  city_name: "Salt Lake City, UT",
  city_lat: 40.7608,
  city_lng: -111.8910,
  cycle_count: 0,
  last_run_at: null,
};

export async function getLoopConfig(client: SupabaseClient): Promise<LoopConfig> {
  const { data, error } = await client
    .from("loop_config")
    .select("*")
    .eq("id", 1)
    .limit(1);

  if (error) {
    throw new Error(`getLoopConfig: ${error.message}`);
  }

  if (!data || data.length === 0) return { ...DEFAULT_LOOP_CONFIG };

  const row = data[0] as Record<string, unknown>;
  return {
    enabled: (row["enabled"] as boolean) ?? DEFAULT_LOOP_CONFIG.enabled,
    interval_seconds:
      (row["interval_seconds"] as number) ?? DEFAULT_LOOP_CONFIG.interval_seconds,
    radius_km: (row["radius_km"] as number) ?? DEFAULT_LOOP_CONFIG.radius_km,
    hours_ahead: (row["hours_ahead"] as number) ?? DEFAULT_LOOP_CONFIG.hours_ahead,
    city_name: (row["city_name"] as string) ?? DEFAULT_LOOP_CONFIG.city_name,
    city_lat: (row["city_lat"] as number) ?? DEFAULT_LOOP_CONFIG.city_lat,
    city_lng: (row["city_lng"] as number) ?? DEFAULT_LOOP_CONFIG.city_lng,
    cycle_count: (row["cycle_count"] as number) ?? 0,
    last_run_at: (row["last_run_at"] as string | null) ?? null,
  };
}

export async function updateLoopConfig(
  client: SupabaseClient,
  config: Partial<LoopConfig>,
): Promise<void> {
  const patch: Record<string, unknown> = { id: 1, updated_at: new Date().toISOString() };
  if (config.enabled !== undefined) patch["enabled"] = config.enabled;
  if (config.interval_seconds !== undefined) patch["interval_seconds"] = config.interval_seconds;
  if (config.radius_km !== undefined) patch["radius_km"] = config.radius_km;
  if (config.hours_ahead !== undefined) patch["hours_ahead"] = config.hours_ahead;
  if (config.city_name !== undefined) patch["city_name"] = config.city_name;
  if (config.city_lat !== undefined) patch["city_lat"] = config.city_lat;
  if (config.city_lng !== undefined) patch["city_lng"] = config.city_lng;
  if (config.cycle_count !== undefined) patch["cycle_count"] = config.cycle_count;
  if (config.last_run_at !== undefined) patch["last_run_at"] = config.last_run_at;

  const { error } = await client
    .from("loop_config")
    .upsert(patch, { onConflict: "id" });
  if (error) {
    throw new Error(`updateLoopConfig: ${error.message}`);
  }
}
