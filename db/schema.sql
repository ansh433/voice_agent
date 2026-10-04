\set ON_ERROR_STOP on

-- Canonical schema entrypoint. The migration remains the source of truth.
\ir migrations/20261008190000_initial_schema.up.sql
