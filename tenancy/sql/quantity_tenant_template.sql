-- Quantity tenant schema foundation, version 1.
-- SCHEMA-RELATIVE: provisioning sets search_path to the new tenant first.
-- This file intentionally contains no serial-number inventory objects.

CREATE TABLE tenant_schema_metadata (
    id boolean PRIMARY KEY DEFAULT true,
    family text NOT NULL DEFAULT 'quantity',
    version integer NOT NULL DEFAULT 1,
    base_currency_code char(3) NOT NULL DEFAULT 'PKR',
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tenant_schema_metadata_singleton CHECK (id),
    CONSTRAINT tenant_schema_metadata_quantity_family CHECK (family = 'quantity'),
    CONSTRAINT tenant_schema_metadata_positive_version CHECK (version >= 1),
    CONSTRAINT tenant_schema_metadata_currency_code CHECK (
        base_currency_code ~ '^[A-Z]{3}$'
    )
);

INSERT INTO tenant_schema_metadata (
    id, family, version, base_currency_code
) VALUES (
    true, 'quantity', 1, 'PKR'
);

CREATE TABLE quantity_seed_registry (
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

CREATE TABLE document_sequences (
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
ON CONFLICT (document_type) DO NOTHING;

CREATE SEQUENCE quantity_foundation_id_seq AS bigint START WITH 1 INCREMENT BY 1;

CREATE FUNCTION quantity_assert_schema_family(expected_family text DEFAULT 'quantity')
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

CREATE FUNCTION quantity_schema_fingerprint()
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
);
