import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  createSupabaseClient,
  loadOrSeedFleet,
  getActiveSchedulesFromDB,
  getLoopConfig,
  updateScheduleStatus,
  createScheduleInDB,
  saveOrchestrationRun,
  updateLoopConfig,
  cacheEvents,
} from "../_shared/db.ts";
import type { Schedule, ScheduleStatus } from "../_shared/types.ts";
import { runOrchestrationCycle } from "../_shared/orchestrator.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const client = createSupabaseClient();
  const url = new URL(req.url);

  try {
    // Parse optional query params
    const queryRadiusKm = url.searchParams.get("radius_km");
    const queryHoursAhead = url.searchParams.get("hours_ahead");

    // 1. Load fleet from DB
    const fleet = await loadOrSeedFleet(client);

    // 2. Get active schedules and convert ScheduleSummary → minimal Schedule objects
    const scheduleSummaries = await getActiveSchedulesFromDB(client);
    const activeSchedules: Schedule[] = scheduleSummaries.map((s) => ({
      id: s.schedule_id,
      cart_id: s.cart_id,
      departure_time: new Date(s.departure_time),
      event: {
        id: "",
        name: s.event_name,
        location_name: s.location,
        coordinates: s.coordinates,
        expected_attendance: 0,
        start_time: new Date(),
        end_time: new Date(s.departure_time),
        category: s.category,
      },
      arrival_time: new Date(s.arrival_time),
      status: "confirmed" as ScheduleStatus,
      estimated_revenue: s.estimated_revenue,
      created_at: new Date(),
    }));

    // 3. Get loop config for city/options override
    const loopConfig = await getLoopConfig(client);

    const radiusKm = queryRadiusKm ? parseFloat(queryRadiusKm) : loopConfig.radius_km;
    const hoursAhead = queryHoursAhead ? parseInt(queryHoursAhead, 10) : loopConfig.hours_ahead;
    const lat = loopConfig.city_lat ?? 40.7608;
    const lng = loopConfig.city_lng ?? -111.891;

    // 4. Run orchestration cycle
    const { result, newSchedules, expiredScheduleIds } = await runOrchestrationCycle(
      fleet,
      activeSchedules,
      { radiusKm, hoursAhead, lat, lng },
    );

    // 5. Mark expired schedules as completed and free their carts
    for (const scheduleId of expiredScheduleIds) {
      // Find the cart_id for this schedule
      const { data: schedRow } = await client
        .from("schedules")
        .select("cart_id")
        .eq("id", scheduleId)
        .single();

      if (schedRow) {
        await client
          .from("carts")
          .update({ status: "idle", assigned_schedule_id: null })
          .eq("id", schedRow.cart_id);
      }

      await updateScheduleStatus(client, scheduleId, "completed");
    }

    // 6. Persist new schedules and update cart statuses to en_route
    for (const schedule of newSchedules) {
      await createScheduleInDB(client, schedule, fleet.id);

      await client
        .from("carts")
        .update({
          status: "en_route",
          assigned_schedule_id: schedule.id,
          current_lat: schedule.event.coordinates.lat,
          current_lng: schedule.event.coordinates.lng,
        })
        .eq("id", schedule.cart_id);
    }

    // 7. Save orchestration run audit record
    await saveOrchestrationRun(client, fleet.id, result, lat, lng, radiusKm);

    // 8. Increment cycle_count and set last_run_at
    await updateLoopConfig(client, {
      cycle_count: loopConfig.cycle_count + 1,
      last_run_at: new Date().toISOString(),
    });

    // 9. Cache discovered events
    if (result.discovered_events && result.discovered_events.length > 0) {
      await cacheEvents(client, result.discovered_events);
    }

    // 10. Return result
    return new Response(
      JSON.stringify({
        ...result,
        new_schedules_created: newSchedules.length,
        expired_schedules_removed: expiredScheduleIds.length,
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
