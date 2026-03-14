import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  updateLoopConfig,
} from "../_shared/db.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
};

function randomOffset(range: number): number {
  return (Math.random() * 2 - 1) * range;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const client = createSupabaseClient();

  try {
    // 1. Parse body
    const body = await req.json();
    const { name, lat, lng } = body as { name: string; lat: number; lng: number };

    if (!name || lat === undefined || lng === undefined) {
      return new Response(
        JSON.stringify({ error: "name, lat, and lng are required" }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    // 2. Update loop_config city fields
    await updateLoopConfig(client, {
      city_name: name,
      city_lat: lat,
      city_lng: lng,
    });

    // 3. Mark all active schedules as completed
    await client
      .from("schedules")
      .update({ status: "completed" })
      .in("status", ["confirmed", "in_progress"]);

    // 4. Reposition all carts to random locations near the new city
    const { data: cartRows, error: cartError } = await client
      .from("carts")
      .select("id");

    if (cartError) {
      throw new Error(`Failed to fetch carts: ${cartError.message}`);
    }

    const carts = cartRows ?? [];

    for (const cartRow of carts) {
      await client
        .from("carts")
        .update({
          current_lat: lat + randomOffset(0.027),
          current_lng: lng + randomOffset(0.036),
          status: "idle",
          assigned_schedule_id: null,
        })
        .eq("id", cartRow.id);
    }

    return new Response(
      JSON.stringify({
        message: `City updated to ${name}`,
        lat,
        lng,
        carts_repositioned: carts.length,
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
