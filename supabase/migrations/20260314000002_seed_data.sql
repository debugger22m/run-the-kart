-- Migration 002: Seed demo fleet and carts (Salt Lake City staging zones)
-- Matches the demo cart locations in src/api/state.py

INSERT INTO fleets (id, name)
VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'SLC-KartFleet');

INSERT INTO carts (id, fleet_id, name, status, current_lat, current_lng, max_orders_per_hour)
VALUES
    ('c1000000-0000-0000-0000-000000000001', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Pioneer',    'idle', 40.7580, -111.9012, 50),
    ('c1000000-0000-0000-0000-000000000002', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Gallivan',   'idle', 40.7611, -111.8906, 50),
    ('c1000000-0000-0000-0000-000000000003', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Gateway',    'idle', 40.7694, -111.9018, 50),
    ('c1000000-0000-0000-0000-000000000004', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Temple',     'idle', 40.7708, -111.8958, 50),
    ('c1000000-0000-0000-0000-000000000005', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Delta',      'idle', 40.7683, -111.9012, 50),
    ('c1000000-0000-0000-0000-000000000006', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Library',    'idle', 40.7607, -111.8912, 50),
    ('c1000000-0000-0000-0000-000000000007', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-CityCreek',  'idle', 40.7683, -111.8945, 50),
    ('c1000000-0000-0000-0000-000000000008', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-Trolley',    'idle', 40.7497, -111.8780, 50),
    ('c1000000-0000-0000-0000-000000000009', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-RiceEccles', 'idle', 40.7596, -111.8486, 50),
    ('c1000000-0000-0000-0000-000000000010', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'Kart-SugarHouse', 'idle', 40.7239, -111.8583, 50);
