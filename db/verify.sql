\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    actual_count bigint;
BEGIN
    SELECT count(*) INTO actual_count FROM branches;
    IF actual_count <> 1 THEN
        RAISE EXCEPTION 'expected 1 branch, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count FROM service_types;
    IF actual_count <> 10 THEN
        RAISE EXCEPTION 'expected 10 services, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count FROM customers;
    IF actual_count <> 40 THEN
        RAISE EXCEPTION 'expected 40 customers, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count FROM vehicles;
    IF actual_count <> 36 THEN
        RAISE EXCEPTION 'expected 36 vehicles, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count FROM appointments;
    IF actual_count <> 60 THEN
        RAISE EXCEPTION 'expected 60 appointments, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count FROM appointment_commands;
    IF actual_count <> 60 THEN
        RAISE EXCEPTION 'expected 60 appointment commands, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count FROM knowledge_entries;
    IF actual_count <> 15 THEN
        RAISE EXCEPTION 'expected 15 knowledge entries, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM appointments
    WHERE status = 'scheduled';
    IF actual_count <> 10 THEN
        RAISE EXCEPTION 'expected 10 scheduled appointments, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM appointments
    WHERE status = 'confirmed';
    IF actual_count <> 10 THEN
        RAISE EXCEPTION 'expected 10 confirmed appointments, found %', actual_count;
    END IF;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO appointments (
            appointment_id,
            customer_id,
            vehicle_id,
            branch_id,
            service_id,
            start_at,
            end_at,
            status,
            idempotency_key
        ) VALUES (
            'verify_branch_overlap',
            'cus_002',
            'veh_002',
            'bra_001',
            'svc_005',
            timestamptz '2026-01-15 10:15:00+05:30',
            timestamptz '2026-01-15 10:30:00+05:30',
            'scheduled',
            'verify-branch-overlap'
        );
        RAISE EXCEPTION 'branch/service overlap was accepted';
    EXCEPTION
        WHEN exclusion_violation THEN NULL;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO appointments (
            appointment_id,
            customer_id,
            vehicle_id,
            branch_id,
            service_id,
            start_at,
            end_at,
            status,
            idempotency_key
        ) VALUES (
            'verify_vehicle_overlap',
            'cus_006',
            'veh_006',
            'bra_001',
            'svc_001',
            timestamptz '2026-01-15 10:15:00+05:30',
            timestamptz '2026-01-15 10:30:00+05:30',
            'scheduled',
            'verify-vehicle-overlap'
        );
        RAISE EXCEPTION 'vehicle overlap was accepted';
    EXCEPTION
        WHEN exclusion_violation THEN NULL;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO appointments (
            appointment_id,
            customer_id,
            vehicle_id,
            branch_id,
            service_id,
            start_at,
            end_at,
            status,
            idempotency_key
        ) VALUES (
            'verify_wrong_owner',
            'cus_002',
            'veh_001',
            'bra_001',
            'svc_001',
            timestamptz '2027-01-15 10:00:00+05:30',
            timestamptz '2027-01-15 11:00:00+05:30',
            'scheduled',
            'verify-wrong-owner'
        );
        RAISE EXCEPTION 'vehicle ownership mismatch was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO appointments (
            appointment_id,
            customer_id,
            vehicle_id,
            branch_id,
            service_id,
            start_at,
            end_at,
            status,
            idempotency_key
        ) VALUES (
            'verify_unsupported_service',
            'cus_001',
            'veh_001',
            'bra_001',
            'svc_008',
            timestamptz '2027-01-15 10:00:00+05:30',
            timestamptz '2027-01-15 14:00:00+05:30',
            'scheduled',
            'verify-unsupported-service'
        );
        RAISE EXCEPTION 'unsupported branch/service was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO appointment_commands (
            idempotency_key,
            operation,
            appointment_id,
            request_hash,
            request_payload,
            status
        ) VALUES (
            'verify-missing-response',
            'cancel',
            'apt_001',
            repeat('0', 64),
            '{}'::jsonb,
            'succeeded'
        );
        RAISE EXCEPTION 'succeeded command without a response was accepted';
    EXCEPTION
        WHEN check_violation THEN NULL;
    END;
END;
$$;

ROLLBACK;

SELECT 'database fixture and constraints verified' AS result;
