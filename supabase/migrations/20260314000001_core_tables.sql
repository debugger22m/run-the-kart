-- Migration 001: Core tables for Run The Kart
-- ============================================================
-- ENUM types
-- ============================================================

CREATE TYPE cart_status AS ENUM ('idle', 'en_route', 'serving', 'maintenance');
CREATE TYPE schedule_status AS ENUM ('pending', 'confirmed', 'in_progress', 'completed', 'cancelled');

-- ============================================================
-- Fleets
-- ============================================================

CREATE TABLE fleets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Carts
-- ============================================================

CREATE TABLE carts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fleet_id                UUID NOT NULL REFERENCES fleets(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,
    status                  cart_status NOT NULL DEFAULT 'idle',
    current_lat             DOUBLE PRECISION,
    current_lng             DOUBLE PRECISION,
    max_orders_per_hour     INTEGER NOT NULL DEFAULT 50,
    assigned_schedule_id    UUID,   -- FK to schedules added below after that table exists
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- Events  (first-class entity; cached across orchestration cycles)
-- ============================================================

CREATE TABLE events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id         TEXT,       -- stable dedup key: hash of name+date+venue
    name                TEXT NOT NULL,
    location_name       TEXT NOT NULL DEFAULT '',
    lat                 DOUBLE PRECISION NOT NULL,
    lng                 DOUBLE PRECISION NOT NULL,
    expected_attendance INTEGER NOT NULL DEFAULT 0,
    start_time          TIMESTAMPTZ NOT NULL,
    end_time            TIMESTAMPTZ NOT NULL,
    category            TEXT,
    description         TEXT,
    source              TEXT,       -- 'mock' | 'web_search' | 'eventbrite' | etc.
    demand_score        DOUBLE PRECISION,
    opportunity_score   DOUBLE PRECISION,
    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_events_external_id UNIQUE (external_id)
);

-- ============================================================
-- Schedules
-- ============================================================

CREATE TABLE schedules (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id             UUID NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    event_id            UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    arrival_time        TIMESTAMPTZ NOT NULL,
    departure_time      TIMESTAMPTZ NOT NULL,
    status              schedule_status NOT NULL DEFAULT 'pending',
    estimated_revenue   DOUBLE PRECISION,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Circular FK: carts.assigned_schedule_id → schedules
ALTER TABLE carts
    ADD CONSTRAINT fk_carts_assigned_schedule
    FOREIGN KEY (assigned_schedule_id) REFERENCES schedules(id) ON DELETE SET NULL;

-- ============================================================
-- Orchestration runs  (append-only audit log)
-- ============================================================

CREATE TABLE orchestration_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fleet_id            UUID NOT NULL REFERENCES fleets(id) ON DELETE CASCADE,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    search_lat          DOUBLE PRECISION,
    search_lng          DOUBLE PRECISION,
    radius_km           DOUBLE PRECISION,
    events_discovered   INTEGER NOT NULL DEFAULT 0,
    schedules_created   INTEGER NOT NULL DEFAULT 0,
    fleet_summary       JSONB,
    errors              JSONB DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- updated_at trigger
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fleets_updated_at
    BEFORE UPDATE ON fleets FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_carts_updated_at
    BEFORE UPDATE ON carts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_events_updated_at
    BEFORE UPDATE ON events FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_schedules_updated_at
    BEFORE UPDATE ON schedules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX idx_carts_fleet_id            ON carts(fleet_id);
CREATE INDEX idx_carts_status              ON carts(status);

CREATE INDEX idx_events_start_time         ON events(start_time);
CREATE INDEX idx_events_opportunity_score  ON events(opportunity_score DESC NULLS LAST);

CREATE INDEX idx_schedules_cart_id         ON schedules(cart_id);
CREATE INDEX idx_schedules_event_id        ON schedules(event_id);
CREATE INDEX idx_schedules_status          ON schedules(status);
CREATE INDEX idx_schedules_arrival_time    ON schedules(arrival_time);

CREATE INDEX idx_orch_runs_fleet_id        ON orchestration_runs(fleet_id);
CREATE INDEX idx_orch_runs_started_at      ON orchestration_runs(started_at DESC);
