export type CartStatus = 'idle' | 'en_route' | 'serving' | 'maintenance';
export type ScheduleStatus = 'pending' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled';

export interface Coordinates {
  lat: number;
  lng: number;
}

export interface Cart {
  id: string;
  fleet_id?: string;
  name: string;
  status: CartStatus;
  current_location?: Coordinates;
  max_orders_per_hour: number;
  assigned_schedule_id?: string;
}

export interface Fleet {
  id: string;
  name: string;
  carts: Map<string, Cart>;
}

// What the EventAgent returns per event
export interface EventData {
  id: string;
  name: string;
  location_name: string;
  latitude: number;
  longitude: number;
  expected_attendance: number;
  start_time: string;   // ISO string
  end_time: string;     // ISO string
  category?: string;
  demand_score?: number;
  opportunity_score?: number;
  estimated_customers?: number;
  estimated_revenue_high?: number;
}

// Schedule's embedded event
export interface ScheduleEvent {
  id: string;
  name: string;
  location_name: string;
  coordinates: Coordinates;
  expected_attendance: number;
  start_time: Date;
  end_time: Date;
  category?: string;
}

export interface Schedule {
  id: string;
  cart_id: string;
  event: ScheduleEvent;
  arrival_time: Date;
  departure_time: Date;
  status: ScheduleStatus;
  estimated_revenue?: number;
  notes?: string;
  created_at: Date;
}

// Summary shape for the dashboard / API responses
export interface ScheduleSummary {
  schedule_id: string;
  cart_id: string;
  event_name: string;
  location: string;
  coordinates: Coordinates;
  arrival_time: string;   // ISO
  departure_time: string; // ISO
  status: string;
  estimated_revenue?: number;
  category?: string;
}

export interface FleetSummary {
  total_carts: number;
  status_breakdown: Record<CartStatus, number>;
}

export interface OrchestrationResult {
  timestamp: string;  // ISO
  fleet_summary: FleetSummary;
  discovered_events: EventData[];
  schedules: ScheduleSummary[];
  expired_schedules: number;
  errors: string[];
}

// Loop/autonomous config stored in DB
export interface LoopConfig {
  enabled: boolean;
  interval_seconds: number;
  radius_km: number;
  hours_ahead: number;
  city_name?: string;
  city_lat?: number;
  city_lng?: number;
  cycle_count: number;
  last_run_at?: string | null;
}
