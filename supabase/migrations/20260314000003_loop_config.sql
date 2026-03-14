-- Loop configuration singleton (id always = 1)
CREATE TABLE IF NOT EXISTS loop_config (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    radius_km       DOUBLE PRECISION NOT NULL DEFAULT 10.0,
    hours_ahead     INTEGER NOT NULL DEFAULT 12,
    city_name       TEXT DEFAULT 'Salt Lake City, UT',
    city_lat        DOUBLE PRECISION DEFAULT 40.7608,
    city_lng        DOUBLE PRECISION DEFAULT -111.8910,
    cycle_count     INTEGER NOT NULL DEFAULT 0,
    last_run_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure exactly one row exists
INSERT INTO loop_config (id, enabled) VALUES (1, true) ON CONFLICT (id) DO NOTHING;
