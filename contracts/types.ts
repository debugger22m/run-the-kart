// ============================================================
// Run The Kart — API Contracts
// Shared types between React/TypeScript frontend and Python backend.
// Keep in sync with src/models/ and src/api/routes.py
// ============================================================

// ------------------------------------------------------------
// Enums
// ------------------------------------------------------------

export enum CartStatus {
  Idle = "idle",
  EnRoute = "en_route",
  Serving = "serving",
  Maintenance = "maintenance",
}

export enum CartType {
  Taco = "taco",
  Italian = "italian",
  Burger = "burger",
  Pizza = "pizza",
  Asian = "asian",
  BBQ = "bbq",
  Dessert = "dessert",
  Mediterranean = "mediterranean",
}

export enum ScheduleStatus {
  Pending = "pending",
  Confirmed = "confirmed",
  InProgress = "in_progress",
  Completed = "completed",
  Cancelled = "cancelled",
}

// ------------------------------------------------------------
// Core models
// ------------------------------------------------------------

export interface Coordinates {
  lat: number;
  lng: number;
}

export interface Cart {
  id: string;
  name: string;
  status: CartStatus;
  cart_type: CartType;
  current_location: Coordinates | null;
  max_orders_per_hour: number;
  assigned_schedule_id: string | null;
}

/** Lightweight summary returned by GET /fleet/carts and fleet.summary() */
export interface CartSummary {
  id: string;
  name: string;
  status: CartStatus;
  cart_type: CartType;
  location: string | null;
}

export interface Fleet {
  fleet_id: string;
  fleet_name: string;
  total_carts: number;
  status_breakdown: Partial<Record<CartStatus, number>>;
  carts: CartSummary[];
}

export interface Event {
  id: string;
  name: string;
  location_name: string;
  coordinates: Coordinates;
  expected_attendance: number;
  start_time: string; // ISO 8601
  end_time: string;   // ISO 8601
  category: string | null;
}

export interface Schedule {
  id: string;
  cart_id: string;
  event: Event;
  arrival_time: string;   // ISO 8601
  departure_time: string; // ISO 8601
  status: ScheduleStatus;
  estimated_revenue: number | null;
  notes: string | null;
  created_at: string; // ISO 8601
}

/** Lightweight summary returned by GET /schedules */
export interface ScheduleSummary {
  schedule_id: string;
  cart_id: string;
  event_name: string;
  location: string;
  coordinates: Coordinates;
  arrival_time: string;
  departure_time: string;
  status: ScheduleStatus;
  estimated_revenue: number | null;
}

// ------------------------------------------------------------
// Request bodies
// ------------------------------------------------------------

export interface AddCartRequest {
  name: string;
  cart_type: CartType;
  latitude: number;
  longitude: number;
  max_orders_per_hour?: number; // default: 50
}

export interface OrchestrationRequest {
  latitude: number;
  longitude: number;
  radius_km?: number;   // default: 10.0
  hours_ahead?: number; // default: 12
}

export interface CompleteScheduleRequest {
  schedule_id: string;
}

// ------------------------------------------------------------
// Response bodies
// ------------------------------------------------------------

export interface AddCartResponse {
  message: string;
  cart_id: string;
  cart: CartSummary;
}

export interface RemoveCartResponse {
  message: string;
  cart_id: string;
}

export interface CompleteScheduleResponse {
  message: string;
  schedule_id: string;
}

export interface OrchestrationResult {
  fleet_summary: Fleet;
  discovered_events: Event[];
  schedules: Schedule[];
  errors: string[];
  timestamp: string; // ISO 8601
}
