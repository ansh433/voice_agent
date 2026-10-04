-- Destructive deterministic fixture reset. The reference clock for all relative
-- appointment data is 2026-01-15 10:00:00 Asia/Kolkata.
BEGIN;
SET LOCAL TIME ZONE 'Asia/Kolkata';

TRUNCATE TABLE
    appointment_commands,
    appointments,
    knowledge_entries,
    branch_services,
    branch_hours,
    vehicles,
    service_types,
    branches,
    customers;

INSERT INTO customers (customer_id, full_name, phone, preferred_language) VALUES
    ('cus_001', 'Aarav Sharma', '+910000000001', 'hinglish'),
    ('cus_002', 'Aditi Rao', '+910000000002', 'en'),
    ('cus_003', 'Vivaan Mehta', '+910000000003', 'hi'),
    ('cus_004', 'Ishita Nair', '+910000000004', 'hinglish'),
    ('cus_005', 'Arjun Kapoor', '+910000000005', 'en'),
    ('cus_006', 'Meera Iyer', '+910000000006', 'hi'),
    ('cus_007', 'Kabir Deshmukh', '+910000000007', 'hinglish'),
    ('cus_008', 'Ananya Kulkarni', '+910000000008', 'en'),
    ('cus_009', 'Rohan Verma', '+910000000009', 'hi'),
    ('cus_010', 'Saanvi Joshi', '+910000000010', 'hinglish'),
    ('cus_011', 'Aditya Menon', '+910000000011', 'en'),
    ('cus_012', 'Priya Shah', '+910000000012', 'hi'),
    ('cus_013', 'Reyansh Patil', '+910000000013', 'hinglish'),
    ('cus_014', 'Diya Bhat', '+910000000014', 'en'),
    ('cus_015', 'Dhruv Malhotra', '+910000000015', 'hi'),
    ('cus_016', 'Kavya Pillai', '+910000000016', 'hinglish'),
    ('cus_017', 'Vihaan Singh', '+910000000017', 'en'),
    ('cus_018', 'Riya Chawla', '+910000000018', 'hi'),
    ('cus_019', 'Sai Krishnan', '+910000000019', 'hinglish'),
    ('cus_020', 'Nisha Jadhav', '+910000000020', 'en'),
    ('cus_021', 'Aryan Gupta', '+910000000021', 'hi'),
    ('cus_022', 'Tara Bose', '+910000000022', 'hinglish'),
    ('cus_023', 'Neil Fernandes', '+910000000023', 'en'),
    ('cus_024', 'Pooja Reddy', '+910000000024', 'hi'),
    ('cus_025', 'Yash Thakur', '+910000000025', 'hinglish'),
    ('cus_026', 'Maya Dsouza', '+910000000026', 'en'),
    ('cus_027', 'Krish Bansal', '+910000000027', 'hi'),
    ('cus_028', 'Leela George', '+910000000028', 'hinglish'),
    ('cus_029', 'Siddharth Jain', '+910000000029', 'en'),
    ('cus_030', 'Neha Mishra', '+910000000030', 'hi'),
    ('cus_031', 'Omkar Sawant', '+910000000031', 'hinglish'),
    ('cus_032', 'Fatima Khan', '+910000000032', 'en'),
    ('cus_033', 'Harsh Vora', '+910000000033', 'hi'),
    ('cus_034', 'Zoya Merchant', '+910000000034', 'hinglish'),
    ('cus_035', 'Manav Sethi', '+910000000035', 'en'),
    ('cus_036', 'Aditi Rao', '+910000000036', 'hi'),
    ('cus_037', 'Devika Shetty', '+910000000037', 'hinglish'),
    ('cus_038', 'Rahul Ahuja', '+910000000038', 'en'),
    ('cus_039', 'Tanvi Kamat', '+910000000039', 'hi'),
    ('cus_040', 'Imran Qureshi', '+910000000040', 'hinglish');

INSERT INTO vehicles (
    vehicle_id,
    customer_id,
    registration_number,
    make,
    model,
    year
) VALUES
    ('veh_001', 'cus_001', 'TEST-MH-01-AA-0001', 'Maruti Suzuki', 'Baleno', 2021),
    ('veh_002', 'cus_002', 'TEST-MH-02-AB-0002', 'Hyundai', 'Creta', 2022),
    ('veh_003', 'cus_003', 'TEST-MH-03-AC-0003', 'Tata', 'Nexon', 2020),
    ('veh_004', 'cus_004', 'TEST-MH-04-AD-0004', 'Mahindra', 'XUV300', 2019),
    ('veh_005', 'cus_005', 'TEST-MH-05-AE-0005', 'Honda', 'City', 2023),
    ('veh_006', 'cus_006', 'TEST-MH-06-AF-0006', 'Toyota', 'Glanza', 2021),
    ('veh_007', 'cus_007', 'TEST-MH-07-AG-0007', 'Kia', 'Seltos', 2022),
    ('veh_008', 'cus_008', 'TEST-MH-08-AH-0008', 'Renault', 'Kiger', 2020),
    ('veh_009', 'cus_009', 'TEST-MH-09-AJ-0009', 'Skoda', 'Kushaq', 2023),
    ('veh_010', 'cus_010', 'TEST-MH-10-AK-0010', 'Volkswagen', 'Virtus', 2022),
    ('veh_011', 'cus_011', 'TEST-MH-11-AL-0011', 'Maruti Suzuki', 'Brezza', 2020),
    ('veh_012', 'cus_012', 'TEST-MH-12-AM-0012', 'Hyundai', 'i20', 2021),
    ('veh_013', 'cus_013', 'TEST-MH-13-AN-0013', 'Tata', 'Altroz', 2019),
    ('veh_014', 'cus_014', 'TEST-MH-14-AP-0014', 'Mahindra', 'Thar', 2023),
    ('veh_015', 'cus_015', 'TEST-MH-15-AQ-0015', 'Honda', 'Amaze', 2018),
    ('veh_016', 'cus_016', 'TEST-MH-16-AR-0016', 'Toyota', 'Urban Cruiser', 2022),
    ('veh_017', 'cus_017', 'TEST-MH-17-AS-0017', 'Kia', 'Sonet', 2021),
    ('veh_018', 'cus_018', 'TEST-MH-18-AT-0018', 'Renault', 'Triber', 2020),
    ('veh_019', 'cus_019', 'TEST-MH-19-AU-0019', 'Skoda', 'Slavia', 2023),
    ('veh_020', 'cus_020', 'TEST-MH-20-AV-0020', 'Volkswagen', 'Taigun', 2022),
    ('veh_021', 'cus_021', 'TEST-MH-21-AW-0021', 'Maruti Suzuki', 'Swift', 2019),
    ('veh_022', 'cus_022', 'TEST-MH-22-AX-0022', 'Hyundai', 'Venue', 2021),
    ('veh_023', 'cus_023', 'TEST-MH-23-AY-0023', 'Tata', 'Punch', 2022),
    ('veh_024', 'cus_024', 'TEST-MH-24-AZ-0024', 'Mahindra', 'Scorpio-N', 2023),
    ('veh_025', 'cus_025', 'TEST-MH-25-BA-0025', 'Honda', 'Elevate', 2024),
    ('veh_026', 'cus_026', 'TEST-MH-26-BB-0026', 'Toyota', 'Innova Crysta', 2020),
    ('veh_027', 'cus_027', 'TEST-MH-27-BC-0027', 'Kia', 'Carens', 2022),
    ('veh_028', 'cus_028', 'TEST-MH-28-BD-0028', 'Renault', 'Kwid', 2018),
    ('veh_029', 'cus_029', 'TEST-MH-29-BE-0029', 'Skoda', 'Kodiaq', 2021),
    ('veh_030', 'cus_030', 'TEST-MH-30-BF-0030', 'Volkswagen', 'Polo', 2017),
    ('veh_031', 'cus_031', 'TEST-MH-31-BG-0031', 'Maruti Suzuki', 'Fronx', 2023),
    ('veh_032', 'cus_032', 'TEST-MH-32-BH-0032', 'Hyundai', 'Verna', 2022),
    ('veh_033', 'cus_033', 'TEST-MH-33-BJ-0033', 'Tata', 'Harrier', 2021),
    ('veh_034', 'cus_034', 'TEST-MH-34-BK-0034', 'Mahindra', 'XUV700', 2023),
    ('veh_035', 'cus_035', 'TEST-MH-35-BL-0035', 'Honda', 'WR-V', 2019),
    ('veh_036', 'cus_001', 'TEST-MH-36-BM-0036', 'Toyota', 'Fortuner', 2020);

INSERT INTO branches (branch_id, name, locality, city) VALUES
    ('bra_001', 'MotorMitra Andheri Service Shop', 'Andheri East', 'Mumbai');

INSERT INTO branch_hours (
    branch_id,
    weekday,
    opens_at,
    closes_at,
    is_closed
)
SELECT
    branch_id,
    weekday,
    CASE
        WHEN weekday = 6 THEN '09:00'::time
        ELSE '08:00'::time
    END,
    CASE
        WHEN weekday = 6 THEN '14:00'::time
        ELSE '19:00'::time
    END,
    false
FROM branches
CROSS JOIN generate_series(0, 6) AS weekdays (weekday);

INSERT INTO service_types (
    service_id,
    name,
    duration_minutes,
    description,
    base_price
) VALUES
    ('svc_001', 'General Inspection', 60, 'Multi-point visual and diagnostic inspection.', 999.00),
    ('svc_002', 'Periodic Maintenance', 180, 'Scheduled maintenance based on age and mileage.', 3499.00),
    ('svc_003', 'Engine Diagnostics', 90, 'Electronic scan and technician-led engine assessment.', 1799.00),
    ('svc_004', 'Brake Service', 120, 'Brake inspection, cleaning, and approved part replacement estimate.', 2499.00),
    ('svc_005', 'Battery Service', 45, 'Battery health, charging, and terminal inspection.', 699.00),
    ('svc_006', 'Wheel Alignment', 60, 'Wheel alignment and tyre wear inspection.', 1199.00),
    ('svc_007', 'Air Conditioning Service', 120, 'Cooling performance and refrigerant system inspection.', 2199.00),
    ('svc_008', 'Interior and Exterior Detailing', 240, 'Vehicle cleaning and non-mechanical detailing package.', 4999.00),
    ('svc_009', 'Pickup and Drop', 30, 'Scheduled vehicle pickup or return within the supported zone.', 499.00),
    ('svc_010', 'Roadside Safety Inspection', 60, 'Non-emergency safety inspection after roadside assistance.', 1299.00);

INSERT INTO branch_services (branch_id, service_id) VALUES
    ('bra_001', 'svc_001'), ('bra_001', 'svc_002'), ('bra_001', 'svc_003'),
    ('bra_001', 'svc_004'), ('bra_001', 'svc_005'), ('bra_001', 'svc_006'),
    ('bra_001', 'svc_007'), ('bra_001', 'svc_008'), ('bra_001', 'svc_009');

WITH fixture AS (
    SELECT
        n,
        'apt_' || lpad(n::text, 3, '0') AS appointment_id,
        'cus_' || lpad((((n - 1) % 35) + 1)::text, 3, '0') AS customer_id,
        'veh_' || lpad((((n - 1) % 35) + 1)::text, 3, '0') AS vehicle_id,
        'bra_001' AS branch_id,
        'svc_' || lpad((((n - 1) % 6) + 1)::text, 3, '0') AS service_id,
        CASE
            WHEN n <= 18 THEN 'completed'
            WHEN n <= 23 THEN 'no_show'
            WHEN n <= 40 THEN 'cancelled'
            WHEN n <= 50 THEN 'scheduled'
            ELSE 'confirmed'
        END AS status,
        CASE
            WHEN n <= 30 THEN
                timestamptz '2026-01-15 10:00:00+05:30' - make_interval(days => 41 - n)
            WHEN n <= 40 THEN
                timestamptz '2026-01-15 10:00:00+05:30' + make_interval(days => n - 30)
            ELSE
                timestamptz '2026-01-15 10:00:00+05:30' + make_interval(days => n - 41)
        END AS start_at
    FROM generate_series(1, 60) AS series (n)
)
INSERT INTO appointments (
    appointment_id,
    customer_id,
    vehicle_id,
    branch_id,
    service_id,
    start_at,
    end_at,
    status,
    idempotency_key,
    version,
    created_at,
    updated_at
)
SELECT
    fixture.appointment_id,
    fixture.customer_id,
    fixture.vehicle_id,
    fixture.branch_id,
    fixture.service_id,
    fixture.start_at,
    fixture.start_at + make_interval(mins => services.duration_minutes),
    fixture.status,
    'seed-create-' || fixture.appointment_id,
    1,
    timestamptz '2026-01-15 10:00:00+05:30' - interval '90 days'
        + make_interval(hours => fixture.n),
    timestamptz '2026-01-15 10:00:00+05:30' - interval '30 days'
        + make_interval(hours => fixture.n)
FROM fixture
JOIN service_types AS services USING (service_id);

INSERT INTO appointment_commands (
    idempotency_key,
    operation,
    appointment_id,
    request_hash,
    request_payload,
    response_payload,
    status,
    confirmation_reference,
    confirmed_at,
    created_at,
    updated_at
)
SELECT
    idempotency_key,
    'create',
    appointment_id,
    md5(idempotency_key) || md5(idempotency_key || ':fixture'),
    jsonb_build_object(
        'customer_id', customer_id,
        'vehicle_id', vehicle_id,
        'branch_id', branch_id,
        'service_id', service_id,
        'start_at', start_at
    ),
    jsonb_build_object('appointment_id', appointment_id, 'status', status),
    'succeeded',
    'seed-confirmation-' || right(appointment_id, 3),
    created_at - interval '5 minutes',
    created_at,
    updated_at
FROM appointments;

INSERT INTO knowledge_entries (
    knowledge_id,
    source_id,
    category,
    title,
    content
) VALUES
    ('knw_001', 'KB-SVC-001', 'service', 'Periodic maintenance scope',
        'Periodic maintenance includes scheduled checks and approved consumable replacement based on vehicle age and mileage. Final work begins only after the customer approves the estimate.'),
    ('knw_002', 'KB-SVC-002', 'service', 'Diagnostic limitations',
        'Remote conversation can collect symptoms and schedule an inspection, but it cannot confirm a mechanical diagnosis or declare a vehicle safe to drive.'),
    ('knw_003', 'KB-HRS-001', 'hours', 'Standard branch hours',
        'The MotorMitra Andheri shop operates Monday through Friday from 08:00 to 19:00 and Saturday from 09:00 to 14:00 Asia/Kolkata. Sunday hours must be checked against the shop schedule before offering a slot.'),
    ('knw_004', 'KB-WAR-001', 'warranty', 'Service workmanship warranty',
        'Warranty eligibility depends on the completed job card, installed part, and inspection. The agent must not promise coverage before staff verification.'),
    ('knw_005', 'KB-PUD-001', 'pickup_drop', 'Pickup and drop coverage',
        'Pickup and drop is available only at supported branches and within their service zone. The address and fee must be confirmed before scheduling.'),
    ('knw_006', 'KB-CAN-001', 'cancellation', 'Cancellation policy',
        'Appointments may be cancelled before the scheduled start. Any fee or refund question requires staff verification; the agent must not invent a charge.'),
    ('knw_007', 'KB-CAN-002', 'cancellation', 'Rescheduling policy',
        'A reschedule requires a newly available slot and explicit customer confirmation. The existing appointment remains authoritative until the reschedule succeeds.'),
    ('knw_008', 'KB-TIM-001', 'timeline', 'Estimated service timelines',
        'Published service durations are planning estimates. Inspection findings, parts availability, and workshop load can change the completion time.'),
    ('knw_009', 'KB-PRC-001', 'pricing', 'Pricing guidance',
        'Base prices are indicative starting prices. A branch estimate and customer approval are required before additional work or parts are charged.'),
    ('knw_010', 'KB-PAY-001', 'payment', 'Accepted payment methods',
        'Branches accept common digital payment methods and cards. Cash availability and financing questions must be confirmed with the selected branch.'),
    ('knw_011', 'KB-RDS-001', 'roadside', 'Immediate danger guidance',
        'For a collision, fire, medical emergency, fuel leak, or unsafe roadside position, contact local emergency services and move to safety when possible. The agent must not provide a mechanical diagnosis.'),
    ('knw_012', 'KB-RDS-002', 'roadside', 'Roadside assistance escalation',
        'For a disabled vehicle without immediate danger, collect the caller location and callback number, then request human roadside assistance.'),
    ('knw_013', 'KB-SAF-001', 'safety', 'Prohibited safety claims',
        'The agent must not state that a vehicle is safe to drive, recommend bypassing warning lights, or instruct the caller to perform hazardous repairs.'),
    ('knw_014', 'KB-SAF-002', 'safety', 'Unsupported questions',
        'If approved knowledge does not answer a policy or mechanical question, say that the information is unavailable and offer a human callback.'),
    ('knw_015', 'KB-PUD-002', 'pickup_drop', 'Vehicle handover',
        'The customer or an authorized representative must be present for pickup and handover with the vehicle key and requested documents.');

COMMIT;
