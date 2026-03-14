import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  loadOrSeedFleet,
  getActiveSchedulesFromDB,
  getLoopConfig,
  fleetSummary,
} from "../_shared/db.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  const client = createSupabaseClient();

  try {
    // 1. Load fleet
    const fleet = await loadOrSeedFleet(client);

    // 2. Get active schedules
    const schedules = await getActiveSchedulesFromDB(client);

    // 3. Get loop config
    const loopConfig = await getLoopConfig(client);

    // 4. Fetch recent events from DB (discovered in last 24h)
    const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    const { data: eventRows } = await client
      .from("events")
      .select("external_id, name, location_name, lat, lng, start_time, end_time, category, opportunity_score")
      .gte("start_time", since)
      .order("opportunity_score", { ascending: false })
      .limit(20);

    const events = (eventRows ?? []).map((r: Record<string, unknown>) => ({
      id: r["external_id"] as string,
      name: r["name"] as string,
      location_name: r["location_name"] as string,
      lat: r["lat"] as number,
      lng: r["lng"] as number,
      start_time: r["start_time"] as string,
      end_time: r["end_time"] as string,
      category: r["category"] as string | undefined,
      opportunity_score: r["opportunity_score"] as number | undefined,
    }));

    // 5. Fetch recent orchestration runs
    const { data: runRows } = await client
      .from("orchestration_runs")
      .select("completed_at, events_discovered, schedules_created, errors")
      .order("completed_at", { ascending: false })
      .limit(5);

    const recentCycles = (runRows ?? []).map((r: Record<string, unknown>, i: number) => ({
      cycle: (loopConfig.cycle_count ?? 0) - i,
      completed_at: r["completed_at"] as string,
      events_found: r["events_discovered"] as number,
      schedules_created: r["schedules_created"] as number,
      errors: (r["errors"] as string[]) ?? [],
    }));

    // 6. Build idle carts list
    const idleCarts: Array<{ id: string; name: string; status: string; lat: number | null; lng: number | null }> = [];
    for (const [, cart] of fleet.carts) {
      if (cart.status === "idle") {
        idleCarts.push({
          id: cart.id,
          name: cart.name,
          status: cart.status,
          lat: cart.current_location?.lat ?? null,
          lng: cart.current_location?.lng ?? null,
        });
      }
    }

    // 5. Determine events_source
    const eventsSource = Deno.env.get("TICKETMASTER_API_KEY") ? "ticketmaster" : "mock";

    const data = {
      fleet: fleetSummary(fleet),
      schedules,
      events,
      loop: {
        running: loopConfig.enabled,
        cycle_count: loopConfig.cycle_count,
        last_run_at: loopConfig.last_run_at,
        config: {
          interval_seconds: loopConfig.interval_seconds,
          radius_km: loopConfig.radius_km,
        },
        recent_cycles: recentCycles,
      },
      idle_carts: idleCarts,
      city: {
        name: loopConfig.city_name ?? "Salt Lake City, UT",
        lat: loopConfig.city_lat ?? 40.7608,
        lng: loopConfig.city_lng ?? -111.891,
        events_source: eventsSource,
      },
    };

    return new Response(JSON.stringify(data), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
