BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TABLE customers (
    customer_id text PRIMARY KEY,
    full_name text NOT NULL CHECK (btrim(full_name) <> ''),
    phone text NOT NULL UNIQUE CHECK (phone ~ '^\+[0-9]{10,15}$'),
    preferred_language text NOT NULL
        CHECK (preferred_language IN ('en', 'hi', 'hinglish')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicles (
    vehicle_id text PRIMARY KEY,
    customer_id text NOT NULL REFERENCES customers (customer_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    registration_number text NOT NULL UNIQUE,
    make text NOT NULL CHECK (btrim(make) <> ''),
    model text NOT NULL CHECK (btrim(model) <> ''),
    year smallint NOT NULL CHECK (year BETWEEN 1886 AND 2100),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (vehicle_id, customer_id)
);

CREATE TABLE branches (
    branch_id text PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> ''),
    locality text NOT NULL CHECK (btrim(locality) <> ''),
    city text NOT NULL CHECK (btrim(city) <> ''),
    timezone text NOT NULL DEFAULT 'Asia/Kolkata'
        CHECK (timezone = 'Asia/Kolkata'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE branch_hours (
    branch_id text NOT NULL REFERENCES branches (branch_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    weekday smallint NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    opens_at time,
    closes_at time,
    is_closed boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (branch_id, weekday),
    CHECK (
        (is_closed AND opens_at IS NULL AND closes_at IS NULL)
        OR
        (NOT is_closed AND opens_at IS NOT NULL AND closes_at IS NOT NULL
            AND opens_at < closes_at)
    )
);

CREATE TABLE service_types (
    service_id text PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> ''),
    duration_minutes integer NOT NULL CHECK (duration_minutes BETWEEN 15 AND 1440),
    description text NOT NULL CHECK (btrim(description) <> ''),
    base_price numeric(10, 2) NOT NULL CHECK (base_price >= 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE branch_services (
    branch_id text NOT NULL REFERENCES branches (branch_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    service_id text NOT NULL REFERENCES service_types (service_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (branch_id, service_id)
);

CREATE TABLE appointments (
    appointment_id text PRIMARY KEY,
    customer_id text NOT NULL,
    vehicle_id text NOT NULL,
    branch_id text NOT NULL,
    service_id text NOT NULL,
    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('scheduled', 'confirmed', 'completed', 'cancelled', 'no_show')),
    idempotency_key text NOT NULL UNIQUE,
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT appointments_positive_interval CHECK (start_at < end_at),
    CONSTRAINT appointments_vehicle_owned_by_customer
        FOREIGN KEY (vehicle_id, customer_id)
        REFERENCES vehicles (vehicle_id, customer_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT appointments_supported_branch_service
        FOREIGN KEY (branch_id, service_id)
        REFERENCES branch_services (branch_id, service_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT appointments_branch_service_no_overlap
        EXCLUDE USING gist (
            branch_id WITH =,
            service_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        ) WHERE (status IN ('scheduled', 'confirmed')),
    CONSTRAINT appointments_vehicle_no_overlap
        EXCLUDE USING gist (
            vehicle_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        ) WHERE (status IN ('scheduled', 'confirmed'))
);

CREATE TABLE appointment_commands (
    idempotency_key text PRIMARY KEY,
    operation text NOT NULL CHECK (operation IN ('create', 'reschedule', 'cancel')),
    appointment_id text REFERENCES appointments (appointment_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    request_hash character(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    request_payload jsonb NOT NULL,
    response_payload jsonb,
    status text NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed', 'unknown')),
    confirmation_reference text,
    confirmed_at timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT appointment_commands_confirmation_pair CHECK (
        (confirmation_reference IS NULL) = (confirmed_at IS NULL)
    ),
    CONSTRAINT appointment_commands_success_has_response CHECK (
        status <> 'succeeded'
        OR (
            appointment_id IS NOT NULL
            AND response_payload IS NOT NULL
        )
    )
);

CREATE TABLE knowledge_entries (
    knowledge_id text PRIMARY KEY,
    source_id text NOT NULL UNIQUE,
    category text NOT NULL CHECK (category IN (
        'service', 'hours', 'warranty', 'pickup_drop', 'cancellation',
        'timeline', 'pricing', 'payment', 'roadside', 'safety'
    )),
    title text NOT NULL CHECK (btrim(title) <> ''),
    content text NOT NULL CHECK (btrim(content) <> ''),
    is_approved boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vehicles_customer_id
    ON vehicles (customer_id);
CREATE INDEX idx_branches_city_locality
    ON branches (city, locality);
CREATE INDEX idx_branch_hours_lookup
    ON branch_hours (branch_id, weekday) WHERE NOT is_closed;
CREATE INDEX idx_branch_services_service_active
    ON branch_services (service_id, branch_id) WHERE is_active;
CREATE INDEX idx_appointments_availability
    ON appointments (branch_id, service_id, start_at, end_at)
    WHERE status IN ('scheduled', 'confirmed');
CREATE INDEX idx_appointments_customer_status_start
    ON appointments (customer_id, status, start_at DESC);
CREATE INDEX idx_appointments_vehicle_start
    ON appointments (vehicle_id, start_at DESC);
CREATE INDEX idx_appointments_status_start
    ON appointments (status, start_at);
CREATE INDEX idx_appointment_commands_appointment
    ON appointment_commands (appointment_id, created_at DESC);
CREATE INDEX idx_knowledge_entries_category_approved
    ON knowledge_entries (category, source_id) WHERE is_approved;
CREATE INDEX idx_knowledge_entries_search
    ON knowledge_entries USING gin (
        to_tsvector('simple', title || ' ' || content)
    ) WHERE is_approved;

CREATE TRIGGER customers_set_updated_at
BEFORE UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER vehicles_set_updated_at
BEFORE UPDATE ON vehicles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER branches_set_updated_at
BEFORE UPDATE ON branches
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER branch_hours_set_updated_at
BEFORE UPDATE ON branch_hours
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER service_types_set_updated_at
BEFORE UPDATE ON service_types
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER branch_services_set_updated_at
BEFORE UPDATE ON branch_services
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER appointments_set_updated_at
BEFORE UPDATE ON appointments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER appointment_commands_set_updated_at
BEFORE UPDATE ON appointment_commands
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER knowledge_entries_set_updated_at
BEFORE UPDATE ON knowledge_entries
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
