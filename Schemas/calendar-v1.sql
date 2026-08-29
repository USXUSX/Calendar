PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
  version INTEGER PRIMARY KEY CHECK (version = 1),
  applied_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', applied_at) IS applied_at)
);
INSERT INTO schema_meta (version, applied_at) VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

CREATE TABLE trips (
  id TEXT PRIMARY KEY CHECK (length(id) > 0),
  visibility TEXT NOT NULL CHECK (visibility IN ('owner', 'participants')),
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
  created_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', created_at) IS created_at),
  updated_at TEXT NOT NULL CHECK (strftime('%Y-%m-%dT%H:%M:%SZ', updated_at) IS updated_at)
);
CREATE INDEX ai_instructions_by_trip_state ON ai_instructions(trip_id, state);

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
