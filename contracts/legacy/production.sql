-- Starting Postgres schema. Apply through a migration system in the deployed app.
CREATE TABLE missions (
    id uuid PRIMARY KEY,
    owner_id text NOT NULL,
    idempotency_key text NOT NULL,
    input_hash char(64) NOT NULL,
    specification jsonb NOT NULL,
    state text NOT NULL CHECK (state IN ('queued','running','succeeded','failed','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(owner_id, idempotency_key)
);

CREATE TABLE assets (
    id uuid PRIMARY KEY,
    owner_id text NOT NULL,
    source_id text NOT NULL,
    product_id text NOT NULL,
    product_version text NOT NULL,
    sha256 char(64) NOT NULL,
    object_key text NOT NULL,
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(owner_id, source_id, product_id, product_version, sha256)
);

CREATE TABLE snapshots (
    id uuid PRIMARY KEY,
    mission_id uuid NOT NULL REFERENCES missions(id),
    sha256 char(64) NOT NULL,
    manifest jsonb NOT NULL,
    UNIQUE(mission_id, sha256)
);

CREATE TABLE tasks (
    id uuid PRIMARY KEY,
    mission_id uuid NOT NULL REFERENCES missions(id),
    snapshot_id uuid NOT NULL REFERENCES snapshots(id),
    phase text NOT NULL,
    task_key char(64) NOT NULL,
    state text NOT NULL CHECK (state IN ('queued','running','retry_wait','succeeded','failed','cancelled','quarantined')),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    fencing_token bigint NOT NULL DEFAULT 0,
    lease_until timestamptz,
    available_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL,
    result_manifest jsonb,
    UNIQUE(mission_id, task_key)
);
CREATE INDEX tasks_ready ON tasks(state, available_at);

CREATE TABLE task_dependencies (
    task_id uuid NOT NULL REFERENCES tasks(id),
    dependency_id uuid NOT NULL REFERENCES tasks(id),
    PRIMARY KEY(task_id, dependency_id),
    CHECK(task_id <> dependency_id)
);
-- Application enforces graph acyclicity before publishing the plan.

CREATE TABLE events (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mission_id uuid NOT NULL REFERENCES missions(id),
    task_id uuid REFERENCES tasks(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    event_type text NOT NULL,
    payload jsonb NOT NULL
);
CREATE INDEX events_mission_sequence ON events(mission_id, sequence);

CREATE TABLE transformations (
    id uuid PRIMARY KEY,
    input_asset_id uuid NOT NULL REFERENCES assets(id),
    output_asset_id uuid NOT NULL REFERENCES assets(id),
    rule_id text NOT NULL,
    rule_version text NOT NULL,
    parameters jsonb NOT NULL,
    affected_count bigint NOT NULL CHECK (affected_count >= 0)
);

CREATE TABLE feature_observations (
    id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES snapshots(id),
    site_id text NOT NULL,
    feature_id text NOT NULL,
    observation_hash char(64) NOT NULL,
    record jsonb NOT NULL,
    UNIQUE(snapshot_id, observation_hash)
);

CREATE TABLE findings (
    id uuid PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES tasks(id),
    severity text NOT NULL CHECK(severity IN ('info','warning','critical')),
    record jsonb NOT NULL
);

CREATE TABLE portfolios (
    id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES snapshots(id),
    scenario_hash char(64) NOT NULL,
    site_set_hash char(64) NOT NULL,
    record jsonb NOT NULL,
    UNIQUE(snapshot_id, scenario_hash, site_set_hash)
);

CREATE TABLE reports (
    id uuid PRIMARY KEY,
    mission_id uuid NOT NULL REFERENCES missions(id),
    snapshot_id uuid NOT NULL REFERENCES snapshots(id),
    object_key text NOT NULL,
    sha256 char(64) NOT NULL,
    release_decision jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Claim inside one transaction. Dependency-ready tasks must be selected explicitly.
-- SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1;
-- UPDATE tasks SET state='running', fencing_token=fencing_token+1, lease_until=...;
-- Insert corresponding event and commit in the same transaction.
-- Complete using WHERE id=:id AND fencing_token=:token AND state='running'
-- AND lease_until > now(), then publish result_manifest and event atomically.
-- Add tenant-aware policies and service-role grants before internet deployment.

-- Enforce one user-selected site or zone per body at the relational boundary.
CREATE TABLE mission_anchors (
    mission_id uuid NOT NULL REFERENCES missions(id),
    body text NOT NULL CHECK (body IN ('Earth','Moon','Mars')),
    location_id text NOT NULL,
    location jsonb NOT NULL,
    PRIMARY KEY(mission_id, body)
);
CREATE TABLE mission_comparisons (
    mission_id uuid NOT NULL REFERENCES missions(id),
    source_body text NOT NULL DEFAULT 'Earth' CHECK (source_body = 'Earth'),
    target_body text NOT NULL CHECK (target_body IN ('Moon','Mars')),
    target_profiles jsonb NOT NULL,
    PRIMARY KEY(mission_id, target_body)
);
-- Within the mission-creation transaction, validate Earth compare_with, exact site matches or reference containment within selected zones and the frozen Earth candidate search policy.

-- Selection JSON stores kind=site|zone and geometry. target_profiles is a
-- location-indexed array, validated for unique IDs and zone containment.
-- Canonical field-site identity is separate from sample cells and selections.
-- Freeze portfolio_mode and reference weighting in the mission specification.
