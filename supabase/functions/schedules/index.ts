import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  getActiveSchedulesFromDB,
  updateScheduleStatus,
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
  // segments[0] = "schedules", segments[1] = "complete" (optional)
  const action = segments[1] ?? null;

  try {
    // GET /schedules → list active schedules
    if (req.method === "GET" && action === null) {
      const schedules = await getActiveSchedulesFromDB(client);
      return new Response(JSON.stringify({ schedules }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // POST /schedules/complete → mark a schedule completed
    if (req.method === "POST" && action === "complete") {
      const body = await req.json();
      const { schedule_id } = body;

      if (!schedule_id) {
        return new Response(JSON.stringify({ error: "schedule_id is required" }), {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      // Look up the cart assigned to this schedule
      const { data: scheduleRows } = await client
        .from("schedules")
        .select("cart_id")
        .eq("id", schedule_id)
        .single();

      if (scheduleRows) {
        // Free the cart back to idle
        await client
          .from("carts")
          .update({ status: "idle", assigned_schedule_id: null })
          .eq("id", scheduleRows.cart_id);
      }

      await updateScheduleStatus(client, schedule_id, "completed");

      return new Response(
        JSON.stringify({ message: "Schedule completed", schedule_id }),
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
