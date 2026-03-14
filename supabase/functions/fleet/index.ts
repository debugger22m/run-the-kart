import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  loadOrSeedFleet,
  upsertCart,
  deleteCart,
  getActiveSchedulesFromDB,
  fleetSummary,
} from "../_shared/db.ts";
import type { Cart } from "../_shared/types.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
};

const FLEET_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11";

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  const client = createSupabaseClient();
  const url = new URL(req.url);
  const pathname = url.pathname;

  // Normalize path: strip leading /fleet or /functions/v1/fleet prefix
  // pathname may be /fleet, /fleet/carts, /fleet/carts/:id
  const segments = pathname.replace(/^\/functions\/v1/, "").split("/").filter(Boolean);
  // segments[0] = "fleet", segments[1] = "carts" (optional), segments[2] = id (optional)
  const section = segments[1] ?? null;   // "carts" or null
  const cartId = segments[2] ?? null;    // UUID or null

  try {
    // GET /fleet → fleet overview + active schedule count
    if (req.method === "GET" && section === null) {
      const fleet = await loadOrSeedFleet(client, FLEET_ID);
      const schedules = await getActiveSchedulesFromDB(client);
      const summary = fleetSummary(fleet);
      return new Response(
        JSON.stringify({
          fleet_id: fleet.id,
          fleet_name: fleet.name,
          ...summary,
          active_schedule_count: schedules.length,
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // GET /fleet/carts → list all carts
    if (req.method === "GET" && section === "carts" && cartId === null) {
      const fleet = await loadOrSeedFleet(client, FLEET_ID);
      const carts = Array.from(fleet.carts.values()).map((c) => ({
        id: c.id,
        name: c.name,
        status: c.status,
        lat: c.current_location?.lat ?? null,
        lng: c.current_location?.lng ?? null,
        max_orders_per_hour: c.max_orders_per_hour,
        assigned_schedule_id: c.assigned_schedule_id ?? null,
      }));
      return new Response(JSON.stringify({ carts }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // GET /fleet/carts/:id → get single cart
    if (req.method === "GET" && section === "carts" && cartId !== null) {
      const { data, error } = await client
        .from("carts")
        .select("*")
        .eq("id", cartId)
        .eq("fleet_id", FLEET_ID)
        .single();

      if (error || !data) {
        return new Response(JSON.stringify({ error: "Cart not found" }), {
          status: 404,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      return new Response(
        JSON.stringify({
          id: data.id,
          name: data.name,
          status: data.status,
          lat: data.current_lat,
          lng: data.current_lng,
          max_orders_per_hour: data.max_orders_per_hour,
          assigned_schedule_id: data.assigned_schedule_id,
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // POST /fleet/carts → add a cart
    if (req.method === "POST" && section === "carts" && cartId === null) {
      const body = await req.json();
      const cart: Cart = {
        id: crypto.randomUUID(),
        fleet_id: FLEET_ID,
        name: body.name,
        status: "idle",
        current_location: { lat: body.latitude, lng: body.longitude },
        max_orders_per_hour: body.max_orders_per_hour ?? 50,
      };

      await upsertCart(client, cart, FLEET_ID);

      return new Response(
        JSON.stringify({
          message: "Cart added",
          cart_id: cart.id,
          cart: { id: cart.id, name: cart.name, status: "idle" },
        }),
        {
          status: 201,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    // DELETE /fleet/carts/:id → remove cart
    if (req.method === "DELETE" && section === "carts" && cartId !== null) {
      await deleteCart(client, cartId);
      return new Response(
        JSON.stringify({ message: "Cart deleted", cart_id: cartId }),
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
