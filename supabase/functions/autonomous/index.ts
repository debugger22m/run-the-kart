import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  getLoopConfig,
  updateLoopConfig,
} from "../_shared/db.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  const client = createSupabaseClient();
  const url = new URL(req.url);
  const pathname = url.pathname;

  // Normalize path segments
  const segments = pathname.replace(/^\/functions\/v1/, "").split("/").filter(Boolean);
  // segments[0] = "autonomous", segments[1] = "status" | "start" | "stop"
  const action = segments[1] ?? null;

  try {
    // GET /autonomous/status → returns current loop status
    if (req.method === "GET" && action === "status") {
      const loopConfig = await getLoopConfig(client);
      return new Response(
        JSON.stringify({
          running: loopConfig.enabled,
          cycle_count: loopConfig.cycle_count,
          last_run_at: loopConfig.last_run_at,
          config: {
            interval_seconds: loopConfig.interval_seconds,
            radius_km: loopConfig.radius_km,
            city_name: loopConfig.city_name ?? "Salt Lake City, UT",
          },
          recent_cycles: [],
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // POST /autonomous/start → enable the loop and optionally update config
    if (req.method === "POST" && action === "start") {
      let body: Record<string, unknown> = {};
      try {
        body = await req.json();
      } catch {
        // body is optional
      }

      const update: Parameters<typeof updateLoopConfig>[1] = { enabled: true };
      if (typeof body.interval_seconds === "number") update.interval_seconds = body.interval_seconds;
      if (typeof body.radius_km === "number") update.radius_km = body.radius_km;
      if (typeof body.hours_ahead === "number") update.hours_ahead = body.hours_ahead;

      await updateLoopConfig(client, update);

      const loopConfig = await getLoopConfig(client);
      return new Response(
        JSON.stringify({
          message: "Autonomous loop started",
          running: loopConfig.enabled,
          config: {
            interval_seconds: loopConfig.interval_seconds,
            radius_km: loopConfig.radius_km,
            city_name: loopConfig.city_name ?? "Salt Lake City, UT",
          },
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // POST /autonomous/stop → disable the loop
    if (req.method === "POST" && action === "stop") {
      await updateLoopConfig(client, { enabled: false });

      return new Response(
        JSON.stringify({
          message: "Autonomous loop stopped",
          running: false,
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    return new Response(JSON.stringify({ error: "Not found" }), {
      status: 404,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
