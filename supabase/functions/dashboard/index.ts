import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  loadOrSeedFleet,
  getActiveSchedulesFromDB,
  getLoopConfig,
  fleetSummary,
} from "../_shared/db.ts";
import type { Cart } from "../_shared/types.ts";

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

    // 4. Build idle carts list
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
      loop: {
        running: loopConfig.enabled,
        cycle_count: loopConfig.cycle_count,
        last_run_at: loopConfig.last_run_at,
        config: {
          interval_seconds: loopConfig.interval_seconds,
          radius_km: loopConfig.radius_km,
        },
        recent_cycles: [],
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
