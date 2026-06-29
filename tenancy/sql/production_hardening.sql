-- Production hardening rollout for existing tenant schemas.
-- Run with:
--   python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql

CREATE TABLE IF NOT EXISTS tenant_schema_version (
    id boolean PRIMARY KEY DEFAULT true,
    version integer NOT NULL,
    applied_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tenant_schema_version_singleton CHECK (id)
);

INSERT INTO tenant_schema_version (id, version)
VALUES (true, 1)
ON CONFLICT (id) DO UPDATE
SET version = GREATEST(tenant_schema_version.version, EXCLUDED.version),
    applied_at = CURRENT_TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS ux_purchaseunits_serial_number
    ON purchaseunits (upper(serial_number));

CREATE INDEX IF NOT EXISTS idx_purchaseunits_serial_in_stock
    ON purchaseunits (upper(serial_number), in_stock);

CREATE UNIQUE INDEX IF NOT EXISTS ux_soldunits_one_active_sale_per_unit
    ON soldunits (unit_id)
    WHERE status = 'Sold';
