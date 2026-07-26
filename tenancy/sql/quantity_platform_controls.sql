-- Phase 20: shared platform controls for quantity-schema tenants.
-- Idempotent and safe for both rollout and fresh bootstrap.

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id BIGSERIAL PRIMARY KEY,
    document_type TEXT NOT NULL CHECK (document_type IN (
        'sale', 'purchase', 'sale_return', 'purchase_return',
        'payment', 'receipt', 'contra'
    )),
    document_id BIGINT NOT NULL,
    file_kind TEXT NOT NULL CHECK (file_kind IN ('image', 'pdf')),
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    uploaded_by INTEGER,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_type, document_id, file_kind)
);
CREATE INDEX IF NOT EXISTS document_attachments_document_idx
    ON document_attachments (document_type, document_id);

CREATE TABLE IF NOT EXISTS quantity_audit_events (
    event_id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
    actor_id INTEGER,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    old_data JSONB,
    new_data JSONB
);
CREATE INDEX IF NOT EXISTS quantity_audit_events_entity_idx
    ON quantity_audit_events (entity_type, entity_id, event_id DESC);
CREATE INDEX IF NOT EXISTS quantity_audit_events_time_idx
    ON quantity_audit_events (occurred_at DESC);

CREATE OR REPLACE FUNCTION quantity_reject_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'quantity audit events are immutable';
END;
$$;

DROP TRIGGER IF EXISTS quantity_audit_events_immutable ON quantity_audit_events;
CREATE TRIGGER quantity_audit_events_immutable
BEFORE UPDATE OR DELETE ON quantity_audit_events
FOR EACH ROW EXECUTE FUNCTION quantity_reject_audit_mutation();

CREATE OR REPLACE FUNCTION quantity_capture_audit_event()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    before_row JSONB := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END;
    after_row JSONB := CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END;
    source_row JSONB := COALESCE(after_row, before_row);
    key_name TEXT := TG_ARGV[0];
    event_actor INTEGER;
BEGIN
    event_actor := COALESCE(
        NULLIF(source_row->>'updated_by_id', '')::INTEGER,
        NULLIF(source_row->>'created_by_id', '')::INTEGER,
        NULLIF(source_row->>'created_by', '')::INTEGER,
        NULLIF(source_row->>'uploaded_by', '')::INTEGER
    );
    INSERT INTO quantity_audit_events (
        entity_type, entity_id, action, actor_id, old_data, new_data
    ) VALUES (
        TG_TABLE_NAME,
        COALESCE(source_row->>key_name, ''),
        CASE TG_OP WHEN 'INSERT' THEN 'create'
                   WHEN 'UPDATE' THEN 'update' ELSE 'delete' END,
        event_actor, before_row, after_row
    );
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    target RECORD;
    trigger_name TEXT;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('products','product_id'), ('product_variants','variant_id'),
            ('warehouses','warehouse_id'),
            ('opening_stock_documents','opening_stock_id'),
            ('opening_stock_lines','opening_stock_line_id'),
            ('purchase_invoices','purchase_invoice_id'),
            ('purchase_lines','purchase_line_id'),
            ('purchase_revisions','purchase_revision_id'),
            ('sale_invoices','sale_invoice_id'),
            ('sale_lines','sale_line_id'),
            ('sale_revisions','sale_revision_id'),
            ('sale_return_invoices','sale_return_id'),
            ('sale_return_lines','sale_return_line_id'),
            ('sale_return_cost_restorations','restoration_id'),
            ('sale_return_revisions','sale_return_revision_id'),
            ('purchase_return_invoices','purchase_return_id'),
            ('purchase_return_lines','purchase_return_line_id'),
            ('purchase_return_source_allocations','source_allocation_id'),
            ('purchase_return_revisions','purchase_return_revision_id'),
            ('warehouse_transfers','transfer_id'),
            ('warehouse_transfer_lines','transfer_line_id'),
            ('warehouse_transfer_cost_segments','segment_id'),
            ('warehouse_transfer_revisions','transfer_revision_id'),
            ('physical_counts','count_id'),
            ('physical_count_lines','count_line_id'),
            ('inventory_adjustments','adjustment_id'),
            ('inventory_adjustment_lines','adjustment_line_id'),
            ('stock_movements','movement_id'),
            ('stock_balances','variant_id'),
            ('fifo_layers','layer_id'),
            ('fifo_allocations','allocation_id'),
            ('journal_entries','journal_id'),
            ('journal_lines','line_id'),
            ('tax_codes','tax_code_id'),
            ('foreign_payments','payment_id'),
            ('payment_allocations','allocation_id'),
            ('foreign_receipts','receipt_id'),
            ('receipt_allocations','allocation_id'),
            ('parties','party_id'), ('payments','payment_id'),
            ('receipts','receipt_id'), ('contra_entries','contra_id'),
            ('opening_cash','opening_cash_id'),
            ('owner_equity_transactions','txn_id'),
            ('period_closes','period_close_id'),
            ('document_attachments','attachment_id')
        ) AS t(table_name, key_name)
    LOOP
        IF to_regclass(target.table_name) IS NOT NULL THEN
            trigger_name := 'quantity_audit_' || target.table_name;
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I',
                           trigger_name, target.table_name);
            EXECUTE format(
                'CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I '
                'FOR EACH ROW EXECUTE FUNCTION quantity_capture_audit_event(%L)',
                trigger_name, target.table_name, target.key_name
            );
        END IF;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION quantity_audit_log(
    p_entity_type TEXT DEFAULT NULL,
    p_entity_id TEXT DEFAULT NULL,
    p_limit INTEGER DEFAULT 200
) RETURNS JSONB LANGUAGE sql STABLE AS $$
    SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.event_id DESC), '[]'::jsonb)
    FROM (
        SELECT event_id, entity_type, entity_id, action, actor_id, occurred_at
        FROM quantity_audit_events
        WHERE (p_entity_type IS NULL OR entity_type = p_entity_type)
          AND (p_entity_id IS NULL OR entity_id = p_entity_id)
        ORDER BY event_id DESC
        LIMIT LEAST(GREATEST(COALESCE(p_limit, 200), 1), 1000)
    ) x;
$$;

INSERT INTO tenant_schema_metadata (id, family, version)
VALUES (TRUE, 'quantity', 20)
ON CONFLICT (id) DO UPDATE
SET family = EXCLUDED.family,
    version = GREATEST(tenant_schema_metadata.version, EXCLUDED.version),
    applied_at = now();
