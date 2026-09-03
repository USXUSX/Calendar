PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
  version INTEGER NOT NULL CHECK (version = 3)
);
INSERT INTO schema_meta (version) VALUES (3);

CREATE TABLE trips (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  visibility TEXT NOT NULL DEFAULT 'owner' CHECK (visibility IN ('owner', 'participants')),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at)
);

CREATE TABLE events (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  title TEXT NOT NULL CHECK (length(title) > 0),
  start_date TEXT NOT NULL CHECK (strftime('%Y-%m-%d', start_date) IS start_date),
  start_time TEXT CHECK (start_time IS NULL OR (start_time GLOB '[0-2][0-9]:[0-5][0-9]' AND substr(start_time, 1, 2) <= '23')),
  end_date TEXT CHECK (end_date IS NULL OR strftime('%Y-%m-%d', end_date) IS end_date),
  end_time TEXT CHECK (end_time IS NULL OR (end_time GLOB '[0-2][0-9]:[0-5][0-9]' AND substr(end_time, 1, 2) <= '23')),
  time_zone TEXT,
  notes TEXT,
  visibility TEXT NOT NULL CHECK (visibility IN ('owner', 'participants')),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at),
  CHECK (end_time IS NULL OR end_date IS NOT NULL)
);

CREATE TABLE todos (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  label TEXT NOT NULL CHECK (length(label) > 0),
  due_date TEXT CHECK (due_date IS NULL OR strftime('%Y-%m-%d', due_date) IS due_date),
  due_time TEXT CHECK (due_time IS NULL OR (due_time GLOB '[0-2][0-9]:[0-5][0-9]' AND substr(due_time, 1, 2) <= '23')),
  completed_at TEXT CHECK (completed_at IS NULL OR strftime('%Y-%m-%dT%H:%M:%SZ', completed_at) IS completed_at),
  trip_id TEXT REFERENCES trips(id),
  event_id TEXT REFERENCES events(id),
  trip_item_id TEXT,
  visibility TEXT NOT NULL CHECK (visibility IN ('owner', 'participants')),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at),
  CHECK (due_time IS NULL OR due_date IS NOT NULL),
  CHECK (trip_item_id IS NULL OR (trip_id IS NOT NULL AND length(trip_item_id) > 0)),
  CHECK (NOT (trip_id IS NOT NULL AND event_id IS NOT NULL))
);
CREATE INDEX todos_by_trip ON todos(trip_id);
CREATE INDEX todos_by_event ON todos(event_id);

CREATE TABLE ai_instructions (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  trip_id TEXT NOT NULL REFERENCES trips(id),
  instruction TEXT NOT NULL CHECK (length(instruction) > 0),
  state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'applied', 'cancelled')),
  base_version INTEGER CHECK (base_version IS NULL OR base_version >= 1),
  base_hash TEXT CHECK (base_hash IS NULL OR (length(base_hash) = 64 AND base_hash NOT GLOB '*[^0-9a-f]*')),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at),
  CHECK ((base_version IS NULL) = (base_hash IS NULL))
);
CREATE INDEX ai_instructions_by_trip_state ON ai_instructions(trip_id, state);

CREATE TABLE generation_requests (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  instruction_id TEXT NOT NULL UNIQUE REFERENCES ai_instructions(id),
  trip_id TEXT NOT NULL REFERENCES trips(id),
  state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'processing', 'completed', 'cancelled')),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at)
);
CREATE INDEX generation_requests_by_state_created ON generation_requests(state, created_at, id);
CREATE UNIQUE INDEX one_processing_request_per_trip
  ON generation_requests(trip_id) WHERE state = 'processing';

CREATE TABLE direct_overrides (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  trip_id TEXT NOT NULL REFERENCES trips(id),
  source_item_id TEXT NOT NULL CHECK (length(source_item_id) > 0),
  field_path TEXT NOT NULL CHECK (length(field_path) > 0),
  value_json TEXT NOT NULL CHECK (json_valid(value_json)),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at),
  UNIQUE (trip_id, source_item_id, field_path)
);
CREATE INDEX direct_overrides_by_trip_active ON direct_overrides(trip_id, active);

CREATE TABLE working_trips (
  trip_id TEXT PRIMARY KEY REFERENCES trips(id),
  base_trip_version INTEGER NOT NULL CHECK (base_trip_version >= 1),
  base_effective_hash TEXT NOT NULL CHECK (length(base_effective_hash) = 64 AND base_effective_hash NOT GLOB '*[^0-9a-f]*'),
  state_json TEXT NOT NULL CHECK (
    json_valid(state_json)
    AND json_type(state_json) = 'object'
    AND json_type(state_json, '$.item_changes') IS 'array'
    AND json_type(state_json, '$.temporary_items') IS 'array'
    AND json_type(state_json, '$.day_instructions') IS 'array'
  ),
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at)
);
