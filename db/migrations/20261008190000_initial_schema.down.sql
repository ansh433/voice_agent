BEGIN;

DROP TABLE IF EXISTS appointment_commands;
DROP TABLE IF EXISTS appointments;
DROP TABLE IF EXISTS knowledge_entries;
DROP TABLE IF EXISTS branch_services;
DROP TABLE IF EXISTS branch_hours;
DROP TABLE IF EXISTS service_types;
DROP TABLE IF EXISTS branches;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS customers;
DROP FUNCTION IF EXISTS set_updated_at();
DROP EXTENSION IF EXISTS btree_gist;

COMMIT;
