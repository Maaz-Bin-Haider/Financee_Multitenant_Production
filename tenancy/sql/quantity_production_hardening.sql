-- Idempotent production hardening for QUANTITY schemas only, version 1.
-- The opening guard rejects serial or uninitialized schemas before mutation.

DO $$
DECLARE
    actual_family text;
BEGIN
    IF to_regclass('tenant_schema_metadata') IS NULL THEN
        RAISE EXCEPTION 'Quantity hardening refused: metadata table missing.';
    END IF;
    SELECT family INTO actual_family
      FROM tenant_schema_metadata
     WHERE id = true;
    IF actual_family IS DISTINCT FROM 'quantity' THEN
        RAISE EXCEPTION 'Quantity hardening refused: schema family mismatch.';
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS quantity_seed_registry (
    seed_key text PRIMARY KEY,
    seed_version integer NOT NULL DEFAULT 1,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    applied_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT quantity_seed_registry_key CHECK (
        seed_key ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT quantity_seed_registry_version CHECK (seed_version >= 1),
    CONSTRAINT quantity_seed_registry_payload_object CHECK (
        jsonb_typeof(payload) = 'object'
    )
);

CREATE TABLE IF NOT EXISTS document_sequences (
    document_type text PRIMARY KEY,
    prefix varchar(8) NOT NULL UNIQUE,
    next_number bigint NOT NULL DEFAULT 1,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT document_sequences_type CHECK (
        document_type ~ '^[a-z][a-z_]{1,31}$'
    ),
    CONSTRAINT document_sequences_prefix CHECK (
        prefix ~ '^[A-Z][A-Z0-9-]{1,7}$'
    ),
    CONSTRAINT document_sequences_positive_next CHECK (next_number >= 1)
);

INSERT INTO document_sequences (document_type, prefix)
VALUES
    ('purchase', 'PUR'),
    ('sale', 'SAL'),
    ('purchase_return', 'PR'),
    ('sale_return', 'SR'),
    ('payment', 'PAY'),
    ('receipt', 'REC'),
    ('contra', 'CON'),
    ('transfer', 'TRF'),
    ('stock_count', 'CNT'),
    ('adjustment', 'ADJ')
ON CONFLICT (document_type) DO UPDATE
SET prefix = EXCLUDED.prefix;

CREATE SEQUENCE IF NOT EXISTS quantity_foundation_id_seq
    AS bigint START WITH 1 INCREMENT BY 1;

CREATE OR REPLACE FUNCTION quantity_assert_schema_family(
    expected_family text DEFAULT 'quantity'
)
RETURNS void
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    actual_family text;
BEGIN
    SELECT family INTO actual_family
      FROM tenant_schema_metadata
     WHERE id = true;
    IF actual_family IS DISTINCT FROM expected_family THEN
        RAISE EXCEPTION 'Schema family mismatch.'
            USING ERRCODE = 'check_violation';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION quantity_schema_fingerprint()
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
    SELECT jsonb_build_object(
        'family', family,
        'version', version,
        'base_currency_code', base_currency_code,
        'foundation_tables', ARRAY[
            'document_sequences',
            'quantity_seed_registry',
            'tenant_schema_metadata'
        ],
        'foundation_sequences', ARRAY['quantity_foundation_id_seq']
    )
    FROM tenant_schema_metadata
    WHERE id = true;
$$;

INSERT INTO quantity_seed_registry (seed_key, seed_version, payload)
VALUES (
    'quantity.foundation',
    1,
    '{"schema_version": 1, "document_sequences": 10}'::jsonb
)
ON CONFLICT (seed_key) DO UPDATE
SET seed_version = GREATEST(
        quantity_seed_registry.seed_version,
        EXCLUDED.seed_version
    ),
    payload = EXCLUDED.payload,
    applied_at = CURRENT_TIMESTAMP;

UPDATE tenant_schema_metadata
   SET version = GREATEST(version, 1),
       applied_at = CURRENT_TIMESTAMP
 WHERE id = true
   AND family = 'quantity';
