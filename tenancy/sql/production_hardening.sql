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
VALUES (true, 2)
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

CREATE OR REPLACE FUNCTION assert_sale_invoice_has_no_returns(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM SalesItems si
        JOIN SoldUnits su ON su.sales_item_id = si.sales_item_id
        JOIN PurchaseUnits pu ON pu.unit_id = su.unit_id
        JOIN SalesReturnItems sri ON sri.serial_number = pu.serial_number
        WHERE si.sales_invoice_id = p_invoice_id
    ) THEN
        RAISE EXCEPTION 'Cannot modify sale invoice % because one or more serials have sale return history.', p_invoice_id;
    END IF;
END; $$;

CREATE OR REPLACE FUNCTION create_sale_return(p_party_name text, p_serials jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_return_id   BIGINT;
    v_customer_id BIGINT;
    v_serial      TEXT;
    v_unit        RECORD;
    v_total       NUMERIC(14,2) := 0;
BEGIN
    SELECT party_id INTO v_customer_id FROM Parties WHERE party_name = p_party_name LIMIT 1;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Party "%" not found', p_party_name;
    END IF;

    INSERT INTO SalesReturns(customer_id, return_date, total_amount, created_by)
    VALUES (v_customer_id, CURRENT_DATE, 0, p_created_by)
    RETURNING sales_return_id INTO v_return_id;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        SELECT su.sold_unit_id, su.unit_id, su.sold_price, si.item_id,
               si.sales_invoice_id, pu.serial_number, pi.unit_price, s.customer_id
        INTO v_unit
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN SalesInvoices s ON si.sales_invoice_id = s.sales_invoice_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
        WHERE pu.serial_number = v_serial
          AND su.status = 'Sold'
        ORDER BY su.sold_unit_id DESC
        LIMIT 1
        FOR UPDATE OF su, pu;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Serial % is not currently sold (nothing to return)', v_serial;
        END IF;
        IF v_unit.customer_id <> v_customer_id THEN
            RAISE EXCEPTION 'Serial % was not sold to this customer', v_serial;
        END IF;

        UPDATE SoldUnits SET status = 'Returned' WHERE sold_unit_id = v_unit.sold_unit_id;
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = v_unit.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_unit.item_id, v_serial, 'IN', 'SalesReturn', v_return_id, 1);

        INSERT INTO SalesReturnItems(sales_return_id, item_id, sold_price, cost_price, serial_number)
        VALUES (v_return_id, v_unit.item_id, v_unit.sold_price, v_unit.unit_price, v_serial);

        v_total := v_total + v_unit.sold_price;
    END LOOP;

    UPDATE SalesReturns SET total_amount = v_total WHERE sales_return_id = v_return_id;
    PERFORM rebuild_sales_return_journal(v_return_id);
    RETURN v_return_id;
END; $$;

CREATE OR REPLACE FUNCTION update_sale_return(p_return_id bigint, p_serials jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec           RECORD;
    v_serial      TEXT;
    v_unit        RECORD;
    v_total       NUMERIC(14,2) := 0;
    v_customer_id BIGINT;
BEGIN
    FOR rec IN
        SELECT serial_number, item_id
        FROM SalesReturnItems
        WHERE sales_return_id = p_return_id
    LOOP
        IF EXISTS (
            SELECT 1
            FROM SoldUnits su
            JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
            WHERE pu.serial_number = rec.serial_number
              AND su.status = 'Sold'
        ) THEN
            RAISE EXCEPTION 'Cannot update this sale return: serial % has since been re-sold. Reverse the later sale first.', rec.serial_number;
        END IF;

        UPDATE SoldUnits SET status = 'Sold'
        WHERE sold_unit_id = (
            SELECT su2.sold_unit_id
            FROM SoldUnits su2
            JOIN PurchaseUnits pu2 ON su2.unit_id = pu2.unit_id
            WHERE pu2.serial_number = rec.serial_number
              AND su2.status = 'Returned'
            ORDER BY su2.sold_unit_id DESC
            LIMIT 1
        );

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE serial_number = rec.serial_number;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'SalesReturn-Update-Reverse', p_return_id, 1);
    END LOOP;

    DELETE FROM SalesReturnItems WHERE sales_return_id = p_return_id;

    SELECT customer_id INTO v_customer_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_customer_id IS NULL THEN
        RAISE EXCEPTION 'Sale return % not found', p_return_id;
    END IF;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        SELECT su.sold_unit_id, su.unit_id, su.sold_price, si.item_id,
               si.sales_invoice_id, pu.serial_number, pi.unit_price, s.customer_id
        INTO v_unit
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN SalesInvoices s ON si.sales_invoice_id = s.sales_invoice_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
        WHERE pu.serial_number = v_serial
          AND su.status = 'Sold'
        ORDER BY su.sold_unit_id DESC
        LIMIT 1
        FOR UPDATE OF su, pu;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Serial % is not currently sold (nothing to return)', v_serial;
        END IF;
        IF v_unit.customer_id <> v_customer_id THEN
            RAISE EXCEPTION 'Serial % was not sold to this customer', v_serial;
        END IF;

        UPDATE SoldUnits SET status = 'Returned' WHERE sold_unit_id = v_unit.sold_unit_id;
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = v_unit.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_unit.item_id, v_serial, 'IN', 'SalesReturn-Update', p_return_id, 1);

        INSERT INTO SalesReturnItems(sales_return_id, item_id, sold_price, cost_price, serial_number)
        VALUES (p_return_id, v_unit.item_id, v_unit.sold_price, v_unit.unit_price, v_serial);

        v_total := v_total + v_unit.sold_price;
    END LOOP;

    UPDATE SalesReturns
    SET total_amount = v_total,
        created_by = COALESCE(p_created_by, created_by)
    WHERE sales_return_id = p_return_id;

    PERFORM rebuild_sales_return_journal(p_return_id);
END; $$;

CREATE OR REPLACE FUNCTION delete_sale_return(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    v_journal_id BIGINT;
BEGIN
    FOR rec IN
        SELECT sri.serial_number, sri.item_id
        FROM SalesReturnItems sri
        WHERE sri.sales_return_id = p_return_id
    LOOP
        IF EXISTS (
            SELECT 1
            FROM SoldUnits su
            JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
            WHERE pu.serial_number = rec.serial_number
              AND su.status = 'Sold'
        ) THEN
            RAISE EXCEPTION 'Cannot delete this sale return: serial % has since been re-sold. Reverse the later sale first.', rec.serial_number;
        END IF;

        UPDATE SoldUnits SET status = 'Sold'
        WHERE sold_unit_id = (
            SELECT su2.sold_unit_id
            FROM SoldUnits su2
            JOIN PurchaseUnits pu2 ON su2.unit_id = pu2.unit_id
            WHERE pu2.serial_number = rec.serial_number
              AND su2.status = 'Returned'
            ORDER BY su2.sold_unit_id DESC
            LIMIT 1
        );

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE serial_number = rec.serial_number;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'SalesReturn-Delete', p_return_id, 1);
    END LOOP;

    SELECT journal_id INTO v_journal_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF v_journal_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = v_journal_id;
    END IF;

    DELETE FROM SalesReturnItems WHERE sales_return_id = p_return_id;
    DELETE FROM SalesReturns WHERE sales_return_id = p_return_id;
END; $$;

CREATE OR REPLACE FUNCTION delete_sale(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    v_journal_id BIGINT;
BEGIN
    PERFORM assert_sale_invoice_has_no_returns(p_invoice_id);

    FOR rec IN
        SELECT su.unit_id, pu.serial_number, si.item_id
        FROM SoldUnits su
        JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
        JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
        WHERE si.sales_invoice_id = p_invoice_id
    LOOP
        UPDATE PurchaseUnits SET in_stock = TRUE WHERE unit_id = rec.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'IN', 'SalesInvoice-Delete', p_invoice_id, 1);
    END LOOP;

    SELECT journal_id INTO v_journal_id FROM SalesInvoices WHERE sales_invoice_id = p_invoice_id;
    IF v_journal_id IS NOT NULL THEN
        DELETE FROM JournalLines WHERE journal_id = v_journal_id;
        DELETE FROM JournalEntries WHERE journal_id = v_journal_id;
    END IF;

    DELETE FROM SalesInvoices WHERE sales_invoice_id = p_invoice_id;
END; $$;

CREATE OR REPLACE FUNCTION update_sale_invoice(
    p_invoice_id bigint,
    p_items jsonb,
    p_party_name text DEFAULT NULL::text,
    p_invoice_date date DEFAULT NULL::date
) RETURNS void
    LANGUAGE plpgsql AS $$
BEGIN
    PERFORM update_sale_invoice(p_invoice_id, p_items, p_party_name, p_invoice_date, NULL::integer);
END; $$;

CREATE OR REPLACE FUNCTION update_sale_invoice(
    p_invoice_id bigint,
    p_items jsonb,
    p_party_name text DEFAULT NULL::text,
    p_invoice_date date DEFAULT NULL::date,
    p_created_by integer DEFAULT NULL::integer
) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_item          JSONB;
    v_item_id       BIGINT;
    v_total         NUMERIC(14,2) := 0;
    v_sales_item_id BIGINT;
    v_serial        TEXT;
    v_unit_id       BIGINT;
    v_new_party_id  BIGINT;
BEGIN
    PERFORM assert_sale_invoice_has_no_returns(p_invoice_id);

    IF p_party_name IS NOT NULL THEN
        SELECT party_id INTO v_new_party_id
        FROM Parties WHERE party_name = p_party_name LIMIT 1;

        IF v_new_party_id IS NULL THEN
            RAISE EXCEPTION 'Customer "%" not found in Parties table.', p_party_name;
        END IF;

        UPDATE SalesInvoices SET customer_id = v_new_party_id WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_invoice_date IS NOT NULL THEN
        UPDATE SalesInvoices SET invoice_date = p_invoice_date WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_created_by IS NOT NULL THEN
        UPDATE SalesInvoices SET created_by = p_created_by WHERE sales_invoice_id = p_invoice_id;
    END IF;

    UPDATE PurchaseUnits pu
    SET in_stock = TRUE
    FROM SoldUnits su
    JOIN SalesItems si ON si.sales_item_id = su.sales_item_id
    WHERE pu.unit_id = su.unit_id
      AND si.sales_invoice_id = p_invoice_id;

    DELETE FROM StockMovements
    WHERE reference_type = 'SalesInvoice' AND reference_id = p_invoice_id;

    DELETE FROM SoldUnits
    WHERE sales_item_id IN (
        SELECT sales_item_id FROM SalesItems WHERE sales_invoice_id = p_invoice_id
    );

    DELETE FROM SalesItems WHERE sales_invoice_id = p_invoice_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id
        FROM Items WHERE item_name = (v_item->>'item_name') LIMIT 1;

        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" not found in Items table for update_sale_invoice',
                            (v_item->>'item_name');
        END IF;

        INSERT INTO SalesItems(sales_invoice_id, item_id, quantity, unit_price)
        VALUES (p_invoice_id, v_item_id,
                (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING sales_item_id INTO v_sales_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            SELECT unit_id INTO v_unit_id
            FROM PurchaseUnits
            WHERE serial_number = v_serial AND in_stock = TRUE
            LIMIT 1
            FOR UPDATE;

            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial % not found in PurchaseUnits', v_serial;
            END IF;

            UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_unit_id;

            INSERT INTO SoldUnits(sales_item_id, unit_id, sold_price, status)
            VALUES (v_sales_item_id, v_unit_id, (v_item->>'unit_price')::NUMERIC, 'Sold');

            INSERT INTO StockMovements(item_id, serial_number, movement_type,
                                       reference_type, reference_id, quantity)
            VALUES (v_item_id, v_serial, 'OUT', 'SalesInvoice', p_invoice_id, 1);
        END LOOP;
    END LOOP;

    UPDATE SalesInvoices SET total_amount = v_total
    WHERE sales_invoice_id = p_invoice_id;

    PERFORM rebuild_sales_journal(p_invoice_id);
END; $$;


-- ============================================================================
-- Transaction integrity guards (delete_purchase / qty-vs-serial / COGS reflow)
-- Folded in from tenancy/sql/fix_transaction_integrity_guards.sql
-- ============================================================================
-- ----------------------------------------------------------------------------
-- Idempotent patch for three data-integrity defects surfaced by the deep
-- transaction lifecycle review (tests/test_transaction_lifecycle_deep.py):
--
--   1. delete_purchase had NO guard against deleting a purchase whose serials
--      were already sold. Because soldunits_unit_id_fkey is ON DELETE CASCADE,
--      the delete silently removed the SoldUnits rows and orphaned the sale
--      invoice / revenue journal, corrupting COGS and stock.
--
--   2. create_sale / update_sale_invoice trusted the payload `qty` for revenue
--      and SalesItems.quantity while shipping only the listed serials, so
--      revenue and units shipped could diverge (the trial balance still
--      balanced, hiding the discrepancy).
--
--   3. update_purchase_invoice rebuilt only the purchase journal. A price-only
--      correction after a sale left that sale's COGS frozen at the old cost,
--      while a later sale return recaptured cost from the edited price,
--      producing silent inventory/COGS drift.
--
-- Safe to run repeatedly (CREATE OR REPLACE). Apply to existing tenants with:
--   python manage.py apply_sql_all_tenants tenancy/sql/fix_transaction_integrity_guards.sql
-- ============================================================================

-- --------------------------------------------------------------------------
-- Fix 1: block delete_purchase when serials have downstream history.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION assert_purchase_invoice_deletable(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM PurchaseItems pi
        JOIN PurchaseUnits pu ON pu.purchase_item_id = pi.purchase_item_id
        JOIN SoldUnits su ON su.unit_id = pu.unit_id
        WHERE pi.purchase_invoice_id = p_invoice_id
    ) THEN
        RAISE EXCEPTION 'Cannot delete purchase invoice % because one or more of its serials have sale history.', p_invoice_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM PurchaseItems pi
        JOIN PurchaseUnits pu ON pu.purchase_item_id = pi.purchase_item_id
        JOIN PurchaseReturnItems pri ON pri.serial_number = pu.serial_number
        WHERE pi.purchase_invoice_id = p_invoice_id
    ) THEN
        RAISE EXCEPTION 'Cannot delete purchase invoice % because one or more of its serials have purchase-return history.', p_invoice_id;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION delete_purchase(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
    j_id BIGINT;
BEGIN
    -- Guard: never destroy a purchase whose serials have sale/return history.
    PERFORM assert_purchase_invoice_deletable(p_invoice_id);

    -- 1. Capture the related journal_id (if any)
    SELECT journal_id INTO j_id
    FROM PurchaseInvoices
    WHERE purchase_invoice_id = p_invoice_id;

    -- 2. Log stock OUT movements before deleting
    FOR rec IN
        SELECT pu.serial_number, pi.item_id, pu.purchase_item_id
        FROM PurchaseUnits pu
        JOIN PurchaseItems pi ON pi.purchase_item_id = pu.purchase_item_id
        WHERE pi.purchase_invoice_id = p_invoice_id
    LOOP
        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (rec.item_id, rec.serial_number, 'OUT', 'PurchaseInvoice-Delete', p_invoice_id, 1);
    END LOOP;

    -- 3. Delete purchase units (serials)
    DELETE FROM PurchaseUnits
    WHERE purchase_item_id IN (
        SELECT purchase_item_id FROM PurchaseItems WHERE purchase_invoice_id = p_invoice_id
    );

    -- 4. Delete purchase items
    DELETE FROM PurchaseItems
    WHERE purchase_invoice_id = p_invoice_id;

    -- 5. Delete journal lines + journal entry if exists
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalLines WHERE journal_id = j_id;
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    -- 6. Delete the purchase invoice itself
    DELETE FROM PurchaseInvoices
    WHERE purchase_invoice_id = p_invoice_id;
END;
$$;

-- --------------------------------------------------------------------------
-- Fix 2: reject qty that does not match the number of serials shipped.
-- Enforced only when serials are supplied, so any non-serial line is untouched.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION create_sale(p_party_id bigint, p_invoice_date date, p_items jsonb, p_created_by integer DEFAULT NULL::integer) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_invoice_id    BIGINT;
    v_sales_item_id BIGINT;
    v_total         NUMERIC(14,2) := 0;
    v_unit_id       BIGINT;
    v_serial        TEXT;
    v_item_id       BIGINT;
    v_item          JSONB;
BEGIN
    INSERT INTO SalesInvoices(customer_id, invoice_date, total_amount, created_by)
    VALUES (p_party_id, p_invoice_date, 0, p_created_by)
    RETURNING sales_invoice_id INTO v_invoice_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id FROM Items
        WHERE item_name = (v_item->>'item_name') LIMIT 1;
        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" not found in Items table', (v_item->>'item_name');
        END IF;

        -- Quantity must match the serials actually shipped.
        IF v_item ? 'serials'
           AND jsonb_typeof(v_item->'serials') = 'array'
           AND jsonb_array_length(v_item->'serials') > 0
           AND (v_item->>'qty')::INT <> jsonb_array_length(v_item->'serials') THEN
            RAISE EXCEPTION 'Quantity (%) does not match the number of serials (%) for item "%".',
                (v_item->>'qty')::INT, jsonb_array_length(v_item->'serials'), (v_item->>'item_name');
        END IF;

        INSERT INTO SalesItems(sales_invoice_id, item_id, quantity, unit_price)
        VALUES (v_invoice_id, v_item_id, (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING sales_item_id INTO v_sales_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            SELECT unit_id INTO v_unit_id FROM PurchaseUnits
            WHERE serial_number = v_serial AND in_stock = TRUE
            LIMIT 1
            FOR UPDATE;
            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial % not found or already sold', v_serial;
            END IF;
            INSERT INTO SoldUnits(sales_item_id, unit_id, sold_price, status)
            VALUES (v_sales_item_id, v_unit_id, (v_item->>'unit_price')::NUMERIC, 'Sold');
            UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_unit_id;
            INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
            VALUES (v_item_id, v_serial, 'OUT', 'SalesInvoice', v_invoice_id, 1);
        END LOOP;
    END LOOP;

    UPDATE SalesInvoices SET total_amount = v_total WHERE sales_invoice_id = v_invoice_id;
    PERFORM rebuild_sales_journal(v_invoice_id);
    RETURN v_invoice_id;
END;
$$;

CREATE OR REPLACE FUNCTION update_sale_invoice(
    p_invoice_id bigint,
    p_items jsonb,
    p_party_name text DEFAULT NULL::text,
    p_invoice_date date DEFAULT NULL::date,
    p_created_by integer DEFAULT NULL::integer
) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_item          JSONB;
    v_item_id       BIGINT;
    v_total         NUMERIC(14,2) := 0;
    v_sales_item_id BIGINT;
    v_serial        TEXT;
    v_unit_id       BIGINT;
    v_new_party_id  BIGINT;
BEGIN
    PERFORM assert_sale_invoice_has_no_returns(p_invoice_id);

    IF p_party_name IS NOT NULL THEN
        SELECT party_id INTO v_new_party_id
        FROM Parties WHERE party_name = p_party_name LIMIT 1;

        IF v_new_party_id IS NULL THEN
            RAISE EXCEPTION 'Customer "%" not found in Parties table.', p_party_name;
        END IF;

        UPDATE SalesInvoices SET customer_id = v_new_party_id WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_invoice_date IS NOT NULL THEN
        UPDATE SalesInvoices SET invoice_date = p_invoice_date WHERE sales_invoice_id = p_invoice_id;
    END IF;

    IF p_created_by IS NOT NULL THEN
        UPDATE SalesInvoices SET created_by = p_created_by WHERE sales_invoice_id = p_invoice_id;
    END IF;

    UPDATE PurchaseUnits pu
    SET in_stock = TRUE
    FROM SoldUnits su
    JOIN SalesItems si ON si.sales_item_id = su.sales_item_id
    WHERE pu.unit_id = su.unit_id
      AND si.sales_invoice_id = p_invoice_id;

    DELETE FROM StockMovements
    WHERE reference_type = 'SalesInvoice' AND reference_id = p_invoice_id;

    DELETE FROM SoldUnits
    WHERE sales_item_id IN (
        SELECT sales_item_id FROM SalesItems WHERE sales_invoice_id = p_invoice_id
    );

    DELETE FROM SalesItems WHERE sales_invoice_id = p_invoice_id;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id
        FROM Items WHERE item_name = (v_item->>'item_name') LIMIT 1;

        IF v_item_id IS NULL THEN
            RAISE EXCEPTION 'Item "%" not found in Items table for update_sale_invoice',
                            (v_item->>'item_name');
        END IF;

        -- Quantity must match the serials actually shipped.
        IF v_item ? 'serials'
           AND jsonb_typeof(v_item->'serials') = 'array'
           AND jsonb_array_length(v_item->'serials') > 0
           AND (v_item->>'qty')::INT <> jsonb_array_length(v_item->'serials') THEN
            RAISE EXCEPTION 'Quantity (%) does not match the number of serials (%) for item "%".',
                (v_item->>'qty')::INT, jsonb_array_length(v_item->'serials'), (v_item->>'item_name');
        END IF;

        INSERT INTO SalesItems(sales_invoice_id, item_id, quantity, unit_price)
        VALUES (p_invoice_id, v_item_id,
                (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING sales_item_id INTO v_sales_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT jsonb_array_elements_text(v_item->'serials')
        LOOP
            SELECT unit_id INTO v_unit_id
            FROM PurchaseUnits
            WHERE serial_number = v_serial AND in_stock = TRUE
            LIMIT 1
            FOR UPDATE;

            IF v_unit_id IS NULL THEN
                RAISE EXCEPTION 'Serial % not found in PurchaseUnits', v_serial;
            END IF;

            UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_unit_id;

            INSERT INTO SoldUnits(sales_item_id, unit_id, sold_price, status)
            VALUES (v_sales_item_id, v_unit_id, (v_item->>'unit_price')::NUMERIC, 'Sold');

            INSERT INTO StockMovements(item_id, serial_number, movement_type,
                                       reference_type, reference_id, quantity)
            VALUES (v_item_id, v_serial, 'OUT', 'SalesInvoice', p_invoice_id, 1);
        END LOOP;
    END LOOP;

    UPDATE SalesInvoices SET total_amount = v_total
    WHERE sales_invoice_id = p_invoice_id;

    PERFORM rebuild_sales_journal(p_invoice_id);
END;
$$;

-- --------------------------------------------------------------------------
-- Fix 3: keep sale COGS in sync when a purchase price is corrected.
-- After rebuilding the purchase journal, rebuild the journal of every sale
-- that consumed units from this purchase invoice.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_purchase_invoice(p_invoice_id bigint, p_items jsonb, p_party_name text DEFAULT NULL::text, p_invoice_date date DEFAULT NULL::date, p_created_by integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    v_item              JSONB;
    v_item_id           BIGINT;
    v_total             NUMERIC(14,2) := 0;
    v_purchase_item_id  BIGINT;
    v_serial            JSONB;
    v_new_party_id      BIGINT;
    v_existing_serials  TEXT[];
    v_new_serials       TEXT[];
    v_serials_to_remove TEXT[];
    v_serials_to_keep   TEXT[];
    v_validation        JSONB;
    v_temp_item_id      BIGINT := -999999;
    v_sale              RECORD;
BEGIN
    -- Validate
    v_validation := validate_purchase_update2(p_invoice_id, p_items);
    IF (v_validation->>'is_valid')::BOOLEAN = FALSE THEN
        RAISE EXCEPTION '%', v_validation->>'message';
    END IF;

    -- Update Party
    IF p_party_name IS NOT NULL THEN
        SELECT party_id INTO v_new_party_id
        FROM Parties WHERE party_name = p_party_name LIMIT 1;

        IF v_new_party_id IS NULL THEN
            RAISE EXCEPTION 'Vendor "%" not found.', p_party_name;
        END IF;

        UPDATE PurchaseInvoices
        SET vendor_id = v_new_party_id
        WHERE purchase_invoice_id = p_invoice_id;
    END IF;

    -- Update Date
    IF p_invoice_date IS NOT NULL THEN
        UPDATE PurchaseInvoices
        SET invoice_date = p_invoice_date
        WHERE purchase_invoice_id = p_invoice_id;
    END IF;

    -- Update last modifier
    IF p_created_by IS NOT NULL THEN
        UPDATE PurchaseInvoices
        SET created_by = p_created_by
        WHERE purchase_invoice_id = p_invoice_id;
    END IF;

    -- Existing serials
    SELECT ARRAY_AGG(pu.serial_number)
    INTO v_existing_serials
    FROM PurchaseUnits pu
    JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
    WHERE pi.purchase_invoice_id = p_invoice_id;

    IF v_existing_serials IS NULL THEN v_existing_serials := ARRAY[]::TEXT[]; END IF;

    -- New serials from JSON
    SELECT ARRAY_AGG(serial_obj->>'serial')
    INTO v_new_serials
    FROM jsonb_array_elements(p_items) AS item,
         jsonb_array_elements(item->'serials') AS serial_obj;

    IF v_new_serials IS NULL THEN v_new_serials := ARRAY[]::TEXT[]; END IF;

    -- Serials to remove
    SELECT ARRAY_AGG(s) INTO v_serials_to_remove
    FROM unnest(v_existing_serials) AS s WHERE s <> ALL(v_new_serials);
    IF v_serials_to_remove IS NULL THEN v_serials_to_remove := ARRAY[]::TEXT[]; END IF;

    -- Serials to keep
    SELECT ARRAY_AGG(s) INTO v_serials_to_keep
    FROM unnest(v_existing_serials) AS s WHERE s = ANY(v_new_serials);
    IF v_serials_to_keep IS NULL THEN v_serials_to_keep := ARRAY[]::TEXT[]; END IF;

    -- Temp item placeholder
    INSERT INTO PurchaseItems(purchase_invoice_id, item_id, quantity, unit_price)
    VALUES (p_invoice_id, 1, 1, 0)
    RETURNING purchase_item_id INTO v_temp_item_id;

    UPDATE PurchaseUnits SET purchase_item_id = v_temp_item_id
    WHERE serial_number = ANY(v_serials_to_keep);

    -- Remove old stock movements for removed serials
    DELETE FROM StockMovements
    WHERE reference_type = 'PurchaseInvoice'
      AND reference_id = p_invoice_id
      AND serial_number = ANY(v_serials_to_remove);

    -- Delete old items
    DELETE FROM PurchaseItems
    WHERE purchase_invoice_id = p_invoice_id
      AND purchase_item_id != v_temp_item_id;

    -- Recreate items
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        SELECT item_id INTO v_item_id
        FROM Items WHERE item_name = (v_item->>'item_name') LIMIT 1;

        IF v_item_id IS NULL THEN
            INSERT INTO Items(item_name, sale_price)
            VALUES ((v_item->>'item_name'), (v_item->>'unit_price')::NUMERIC)
            RETURNING item_id INTO v_item_id;
        END IF;

        INSERT INTO PurchaseItems(purchase_invoice_id, item_id, quantity, unit_price)
        VALUES (p_invoice_id, v_item_id,
                (v_item->>'qty')::INT, (v_item->>'unit_price')::NUMERIC)
        RETURNING purchase_item_id INTO v_purchase_item_id;

        v_total := v_total + ((v_item->>'qty')::INT * (v_item->>'unit_price')::NUMERIC);

        FOR v_serial IN SELECT * FROM jsonb_array_elements(v_item->'serials')
        LOOP
            IF (v_serial->>'serial') = ANY(v_serials_to_keep) THEN
                UPDATE PurchaseUnits
                SET purchase_item_id = v_purchase_item_id,
                    serial_comment = NULLIF(TRIM(COALESCE(v_serial->>'comment','')), '')
                WHERE serial_number = v_serial->>'serial'
                  AND purchase_item_id = v_temp_item_id;
            ELSE
                INSERT INTO PurchaseUnits(purchase_item_id, serial_number, serial_comment, in_stock)
                VALUES (v_purchase_item_id, v_serial->>'serial',
                        NULLIF(TRIM(COALESCE(v_serial->>'comment','')), ''), TRUE);

                INSERT INTO StockMovements(item_id, serial_number, movement_type,
                                           reference_type, reference_id, quantity)
                VALUES (v_item_id, v_serial->>'serial', 'IN', 'PurchaseInvoice', p_invoice_id, 1);
            END IF;
        END LOOP;
    END LOOP;

    DELETE FROM PurchaseItems WHERE purchase_item_id = v_temp_item_id;

    UPDATE PurchaseInvoices SET total_amount = v_total
    WHERE purchase_invoice_id = p_invoice_id;

    PERFORM rebuild_purchase_journal(p_invoice_id);

    -- Keep COGS in sync: rebuild the journal of every sale that consumed a unit
    -- from this purchase invoice, so a price correction reflows into COGS.
    FOR v_sale IN
        SELECT DISTINCT si.sales_invoice_id AS sid
        FROM PurchaseItems pi
        JOIN PurchaseUnits pu ON pu.purchase_item_id = pi.purchase_item_id
        JOIN SoldUnits su ON su.unit_id = pu.unit_id
        JOIN SalesItems si ON si.sales_item_id = su.sales_item_id
        WHERE pi.purchase_invoice_id = p_invoice_id
    LOOP
        PERFORM rebuild_sales_journal(v_sale.sid);
    END LOOP;
END;
$$;

-- Bump the tenant schema version so the guard is visible to the middleware.
UPDATE tenant_schema_version
SET version = GREATEST(version, 3),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;


-- ============================================================================
-- Tenant drift heal (purchase-return guard / item_transaction_history overload /
-- get_item_names_like) — folded from tenancy/sql/fix_tenant_drift.sql
-- ============================================================================
-- ----------------------------------------------------------------------------
-- Idempotent patch that heals tenant schema drift found by the full-system test
-- suite (tests/suite/). Safe to run repeatedly and on tenants that already have
-- the corrected objects.
--
--   1. create_purchase_return had no in-stock guard on some tenants, so a sold
--      serial could be purchase-returned and serials could be double-returned.
--      Add the in-stock guard (matches the already-correct tenants).
--
--   2. item_transaction_history existed as BOTH a 1-arg and a 3-arg-with-defaults
--      overload on some tenants, making a 1-arg call ambiguous. Drop the
--      redundant 1-arg overload; the 3-arg (defaulted) covers 1-arg calls.
--
--   3. get_item_names_like referenced an unqualified `item_name` that collides
--      with its OUT column on PostgreSQL 16 (ambiguous column). Qualify it.
--
-- Apply to existing tenants with:
--   python manage.py apply_sql_all_tenants tenancy/sql/fix_tenant_drift.sql
-- ============================================================================

-- --------------------------------------------------------------------------
-- 1. In-stock guard for purchase returns.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION create_purchase_return(p_party_name text, p_serials jsonb, p_created_by integer DEFAULT NULL::integer)
    RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_return_id BIGINT;
    v_vendor_id BIGINT;
    v_serial    TEXT;
    v_rec       RECORD;
    v_total     NUMERIC(14,2) := 0;
BEGIN
    SELECT party_id INTO v_vendor_id FROM Parties WHERE party_name = p_party_name LIMIT 1;
    IF v_vendor_id IS NULL THEN
        RAISE EXCEPTION 'Vendor "%" not found', p_party_name;
    END IF;

    INSERT INTO PurchaseReturns(vendor_id, return_date, total_amount, created_by)
    VALUES (v_vendor_id, CURRENT_DATE, 0, p_created_by)
    RETURNING purchase_return_id INTO v_return_id;

    FOR v_serial IN SELECT jsonb_array_elements_text(p_serials)
    LOOP
        -- Only an in-stock serial belonging to this vendor may be returned.
        SELECT pu.unit_id, pu.purchase_item_id, pi2.unit_price, pi2.item_id,
               pi2.purchase_invoice_id, pu.serial_number
        INTO v_rec
        FROM PurchaseUnits pu
        JOIN PurchaseItems pi2 ON pu.purchase_item_id = pi2.purchase_item_id
        JOIN PurchaseInvoices pinv ON pi2.purchase_invoice_id = pinv.purchase_invoice_id
        WHERE pu.serial_number = v_serial
          AND pinv.vendor_id = v_vendor_id
          AND pu.in_stock = TRUE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Serial % is not in stock or not found for this vendor', v_serial;
        END IF;

        UPDATE PurchaseUnits SET in_stock = FALSE WHERE unit_id = v_rec.unit_id;

        INSERT INTO StockMovements(item_id, serial_number, movement_type, reference_type, reference_id, quantity)
        VALUES (v_rec.item_id, v_serial, 'OUT', 'PurchaseReturn', v_return_id, 1);

        INSERT INTO PurchaseReturnItems(purchase_return_id, item_id, unit_price, serial_number)
        VALUES (v_return_id, v_rec.item_id, v_rec.unit_price, v_serial);

        v_total := v_total + v_rec.unit_price;
    END LOOP;

    UPDATE PurchaseReturns SET total_amount = v_total WHERE purchase_return_id = v_return_id;
    PERFORM rebuild_purchase_return_journal(v_return_id);
    RETURN v_return_id;
END;
$$;

-- --------------------------------------------------------------------------
-- 2. Remove the redundant 1-arg item_transaction_history overload.
--    The 3-arg (p_item_name text, p_from_date date DEFAULT NULL,
--    p_to_date date DEFAULT NULL) handles 1-arg calls unambiguously.
-- --------------------------------------------------------------------------
DROP FUNCTION IF EXISTS item_transaction_history(text);

-- --------------------------------------------------------------------------
-- 3. Fix the ambiguous column in get_item_names_like.
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_item_names_like(search_term text)
    RETURNS TABLE(item_name text)
    LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT i.item_name::text
    FROM items i
    WHERE UPPER(i.item_name) LIKE UPPER(search_term) || '%'
    ORDER BY i.item_name;
END;
$$;

-- Bump tenant schema version.
UPDATE tenant_schema_version
SET version = GREATEST(version, 4),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;

-- ============================================================================
-- Cash-party feature on every tenant (from fix_cash_party_port.sql; v5),
-- including its invoice-description prerequisite and the pre-flag journal
-- backfill. Idempotent; heals tenants bootstrapped before the feature existed.
-- ============================================================================

ALTER TABLE salesinvoices    ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE purchaseinvoices ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE salesreturns     ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE purchasereturns  ADD COLUMN IF NOT EXISTS description text;

-- 2) Read functions: return the invoice's own description --------------------

CREATE OR REPLACE FUNCTION get_current_sale(p_invoice_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'sales_invoice_id', si.sales_invoice_id,
        'Party',            p.party_name,
        'invoice_date',     si.invoice_date,
        'total_amount',     si.total_amount,
        'description',      si.description,
        'created_by',       COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',  i.item_name,
                'qty',        s_items.quantity,
                'unit_price', s_items.unit_price,
                'serials', (
                    SELECT json_agg(pu.serial_number)
                    FROM SoldUnits su
                    JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
                    WHERE su.sales_item_id = s_items.sales_item_id
                )
            ))
            FROM SalesItems s_items
            JOIN Items i ON i.item_id = s_items.item_id
            WHERE s_items.sales_invoice_id = si.sales_invoice_id
        )
    ) INTO result
    FROM SalesInvoices si
    JOIN Parties p ON p.party_id = si.customer_id
    LEFT JOIN auth_user u ON u.id = si.created_by
    WHERE si.sales_invoice_id = p_invoice_id;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_current_purchase(p_invoice_id bigint)
 RETURNS json LANGUAGE plpgsql AS $function$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'purchase_invoice_id', pi.purchase_invoice_id,
        'Party',               p.party_name,
        'invoice_date',        pi.invoice_date,
        'total_amount',        pi.total_amount,
        'description',         pi.description,
        'created_by',          COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',  i.item_name,
                'qty',        pi2.quantity,
                'unit_price', pi2.unit_price,
                'serials', (
                    SELECT json_agg(json_build_object('serial', pu.serial_number, 'comment', pu.serial_comment))
                    FROM PurchaseUnits pu
                    WHERE pu.purchase_item_id = pi2.purchase_item_id
                )
            ))
            FROM PurchaseItems pi2
            JOIN Items i ON i.item_id = pi2.item_id
            WHERE pi2.purchase_invoice_id = pi.purchase_invoice_id
        )
    ) INTO result
    FROM PurchaseInvoices pi
    JOIN Parties p ON p.party_id = pi.vendor_id
    LEFT JOIN auth_user u ON u.id = pi.created_by
    WHERE pi.purchase_invoice_id = p_invoice_id
      AND NOT COALESCE(pi.is_opening, false);
    RETURN result;
END; $function$;

CREATE OR REPLACE FUNCTION get_current_sales_return(p_return_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'sales_return_id', sr.sales_return_id,
        'Customer',        pa.party_name,
        'return_date',     sr.return_date,
        'total_amount',    sr.total_amount,
        'description',     sr.description,
        'created_by',      COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',     i.item_name,
                'sold_price',    sri.sold_price,
                'cost_price',    sri.cost_price,
                'serial_number', sri.serial_number
            ))
            FROM SalesReturnItems sri
            JOIN Items i ON i.item_id = sri.item_id
            WHERE sri.sales_return_id = sr.sales_return_id
        )
    ) INTO result
    FROM SalesReturns sr
    JOIN Parties pa ON pa.party_id = sr.customer_id
    LEFT JOIN auth_user u ON u.id = sr.created_by
    WHERE sr.sales_return_id = p_return_id;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_current_purchase_return(p_return_id bigint) RETURNS json
    LANGUAGE plpgsql
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'purchase_return_id', pr.purchase_return_id,
        'Vendor',             pa.party_name,
        'return_date',        pr.return_date,
        'total_amount',       pr.total_amount,
        'description',        pr.description,
        'created_by',         COALESCE(u.username, 'N/A'),
        'items', (
            SELECT json_agg(json_build_object(
                'item_name',     i.item_name,
                'unit_price',    pri.unit_price,
                'serial_number', pri.serial_number
            ))
            FROM PurchaseReturnItems pri
            JOIN Items i ON i.item_id = pri.item_id
            WHERE pri.purchase_return_id = pr.purchase_return_id
        )
    ) INTO result
    FROM PurchaseReturns pr
    JOIN Parties pa ON pa.party_id = pr.vendor_id
    LEFT JOIN auth_user u ON u.id = pr.created_by
    WHERE pr.purchase_return_id = p_return_id;
    RETURN result;
END;
$$;

-- 1) Flag on Parties ---------------------------------------------------------
ALTER TABLE Parties ADD COLUMN IF NOT EXISTS is_cash boolean DEFAULT false;

-- 2) Sentinel cash parties: get-or-create, return id -------------------------
CREATE OR REPLACE FUNCTION get_cash_party_id(p_kind text) RETURNS bigint
    LANGUAGE plpgsql AS $$
DECLARE
    v_id   bigint;
    v_name text;
    v_type text;
BEGIN
    IF p_kind = 'sale' THEN
        v_name := 'Cash Sale';     v_type := 'Customer';
    ELSIF p_kind = 'purchase' THEN
        v_name := 'Cash Purchase'; v_type := 'Vendor';
    ELSE
        RAISE EXCEPTION 'get_cash_party_id: kind must be sale|purchase, got %', p_kind;
    END IF;

    SELECT party_id INTO v_id FROM Parties WHERE party_name = v_name LIMIT 1;
    IF v_id IS NULL THEN
        PERFORM add_party_from_json(jsonb_build_object(
            'party_name', v_name, 'party_type', v_type,
            'opening_balance', 0, 'balance_type', 'Debit'));
        SELECT party_id INTO v_id FROM Parties WHERE party_name = v_name LIMIT 1;
    END IF;
    UPDATE Parties SET is_cash = true WHERE party_id = v_id AND COALESCE(is_cash,false) = false;
    RETURN v_id;
END; $$;

-- ============================================================================
-- 3) Journal builders — add the cash branch (everything else unchanged)
-- ============================================================================

-- 3a) SALES ------------------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_sales_journal(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    rev_acc BIGINT;
    party_acc BIGINT;
    cogs_acc BIGINT;
    inv_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    total_cost NUMERIC(14,2);
    total_revenue NUMERIC(14,2);
    v_customer_id BIGINT;
    v_invoice_date DATE;
BEGIN
    SELECT journal_id INTO j_id FROM SalesInvoices WHERE sales_invoice_id = p_invoice_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalLines WHERE journal_id = j_id;
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT s.customer_id, s.total_amount, s.invoice_date
    INTO v_customer_id, total_revenue, v_invoice_date
    FROM SalesInvoices s WHERE s.sales_invoice_id = p_invoice_id;

    SELECT account_id INTO rev_acc  FROM ChartOfAccounts WHERE account_name='Sales Revenue';
    SELECT account_id INTO cogs_acc FROM ChartOfAccounts WHERE account_name='Cost of Goods Sold';
    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ar_account_id INTO party_acc FROM Parties WHERE party_id = v_customer_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_customer_id;

    INSERT INTO JournalEntries(entry_date, description)
    VALUES (v_invoice_date, 'Sale Invoice ' || p_invoice_id)
    RETURNING journal_id INTO j_id;

    UPDATE SalesInvoices SET journal_id = j_id WHERE sales_invoice_id = p_invoice_id;

    -- (1) Debit Customer AR  OR  Cash (cash sale -> no party, cash increases now)
    IF v_is_cash THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)
        VALUES (j_id, cash_acc, total_revenue);
    ELSE
        INSERT INTO JournalLines(journal_id, account_id, party_id, debit)
        VALUES (j_id, party_acc, v_customer_id, total_revenue);
    END IF;

    -- (2) Credit Revenue
    INSERT INTO JournalLines(journal_id, account_id, credit)
    VALUES (j_id, rev_acc, total_revenue);

    -- (3) Debit COGS / Credit Inventory
    SELECT COALESCE(SUM(pi.unit_price),0) INTO total_cost
    FROM SoldUnits su
    JOIN PurchaseUnits pu ON su.unit_id = pu.unit_id
    JOIN PurchaseItems pi ON pu.purchase_item_id = pi.purchase_item_id
    JOIN SalesItems si ON su.sales_item_id = si.sales_item_id
    WHERE si.sales_invoice_id = p_invoice_id;

    IF total_cost > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)  VALUES (j_id, cogs_acc, total_cost);
        INSERT INTO JournalLines(journal_id, account_id, credit) VALUES (j_id, inv_acc, total_cost);
    END IF;
END; $$;

-- 3b) PURCHASES --------------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_purchase_journal(p_invoice_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    inv_acc BIGINT;
    party_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    v_total NUMERIC(14,2);
    v_vendor_id BIGINT;
BEGIN
    SELECT journal_id INTO j_id FROM PurchaseInvoices WHERE purchase_invoice_id = p_invoice_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT vendor_id, total_amount INTO v_vendor_id, v_total
    FROM PurchaseInvoices WHERE purchase_invoice_id = p_invoice_id;

    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ap_account_id INTO party_acc FROM Parties WHERE party_id = v_vendor_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_vendor_id;

    INSERT INTO JournalEntries(entry_date, description)
    SELECT invoice_date, 'Purchase Invoice ' || purchase_invoice_id
    FROM PurchaseInvoices WHERE purchase_invoice_id = p_invoice_id
    RETURNING journal_id INTO j_id;

    UPDATE PurchaseInvoices SET journal_id = j_id WHERE purchase_invoice_id = p_invoice_id;

    -- (6) Debit Inventory
    INSERT INTO JournalLines(journal_id, account_id, debit)
    VALUES (j_id, inv_acc, v_total);

    -- (7) Credit Vendor AP  OR  Cash (cash purchase -> no party, cash decreases now)
    IF v_is_cash THEN
        INSERT INTO JournalLines(journal_id, account_id, credit)
        VALUES (j_id, cash_acc, v_total);
    ELSE
        INSERT INTO JournalLines(journal_id, account_id, party_id, credit)
        VALUES (j_id, party_acc, v_vendor_id, v_total);
    END IF;
END; $$;

-- 3c) SALES RETURN -----------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_sales_return_journal(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    rev_acc BIGINT;
    cogs_acc BIGINT;
    inv_acc BIGINT;
    party_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    v_total NUMERIC(14,2);
    v_cost NUMERIC(14,2);
    v_customer_id BIGINT;
    v_date DATE;
BEGIN
    SELECT journal_id INTO j_id FROM SalesReturns WHERE sales_return_id = p_return_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT customer_id, total_amount, return_date
    INTO v_customer_id, v_total, v_date
    FROM SalesReturns WHERE sales_return_id = p_return_id;

    SELECT COALESCE(SUM(cost_price),0) INTO v_cost
    FROM SalesReturnItems WHERE sales_return_id = p_return_id;

    SELECT account_id INTO rev_acc  FROM ChartOfAccounts WHERE account_name='Sales Revenue';
    SELECT account_id INTO cogs_acc FROM ChartOfAccounts WHERE account_name='Cost of Goods Sold';
    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ar_account_id INTO party_acc FROM Parties WHERE party_id = v_customer_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_customer_id;

    INSERT INTO JournalEntries(entry_date, description)
    VALUES (v_date, 'Sales Return ' || p_return_id)
    RETURNING journal_id INTO j_id;

    UPDATE SalesReturns SET journal_id = j_id WHERE sales_return_id = p_return_id;

    -- (1) Debit Sales Revenue
    IF v_total > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)
        VALUES (j_id, rev_acc, v_total);
    END IF;

    -- (2) Credit Customer AR  OR  Cash (cash sale return -> refund cash, no party)
    IF v_total > 0 THEN
        IF v_is_cash THEN
            INSERT INTO JournalLines(journal_id, account_id, credit)
            VALUES (j_id, cash_acc, v_total);
        ELSE
            INSERT INTO JournalLines(journal_id, account_id, party_id, credit)
            VALUES (j_id, party_acc, v_customer_id, v_total);
        END IF;
    END IF;

    -- (3) Debit Inventory / (4) Credit COGS
    IF v_cost > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, debit)  VALUES (j_id, inv_acc, v_cost);
        INSERT INTO JournalLines(journal_id, account_id, credit) VALUES (j_id, cogs_acc, v_cost);
    END IF;
END; $$;

-- 3d) PURCHASE RETURN --------------------------------------------------------
CREATE OR REPLACE FUNCTION rebuild_purchase_return_journal(p_return_id bigint) RETURNS void
    LANGUAGE plpgsql AS $$
DECLARE
    j_id BIGINT;
    inv_acc BIGINT;
    party_acc BIGINT;
    cash_acc BIGINT;
    v_is_cash BOOLEAN := false;
    v_total NUMERIC(14,2);
    v_vendor_id BIGINT;
    v_date DATE;
BEGIN
    SELECT journal_id INTO j_id FROM PurchaseReturns WHERE purchase_return_id = p_return_id;
    IF j_id IS NOT NULL THEN
        DELETE FROM JournalEntries WHERE journal_id = j_id;
    END IF;

    SELECT vendor_id, total_amount, return_date
    INTO v_vendor_id, v_total, v_date
    FROM PurchaseReturns WHERE purchase_return_id = p_return_id;

    SELECT account_id INTO inv_acc  FROM ChartOfAccounts WHERE account_name='Inventory';
    SELECT account_id INTO cash_acc FROM ChartOfAccounts WHERE account_name='Cash';
    SELECT ap_account_id INTO party_acc FROM Parties WHERE party_id = v_vendor_id;
    SELECT COALESCE(is_cash,false) INTO v_is_cash FROM Parties WHERE party_id = v_vendor_id;

    INSERT INTO JournalEntries(entry_date, description)
    VALUES (v_date, 'Purchase Return ' || p_return_id)
    RETURNING journal_id INTO j_id;

    UPDATE PurchaseReturns SET journal_id = j_id WHERE purchase_return_id = p_return_id;

    -- (1) Debit Vendor AP  OR  Cash (cash purchase return -> cash refunded in, no party)
    IF v_total > 0 THEN
        IF v_is_cash THEN
            INSERT INTO JournalLines(journal_id, account_id, debit)
            VALUES (j_id, cash_acc, v_total);
        ELSE
            INSERT INTO JournalLines(journal_id, account_id, party_id, debit)
            VALUES (j_id, party_acc, v_vendor_id, v_total);
        END IF;
    END IF;

    -- (2) Credit Inventory
    IF v_total > 0 THEN
        INSERT INTO JournalLines(journal_id, account_id, credit)
        VALUES (j_id, inv_acc, v_total);
    END IF;
END; $$;

-- ----------------------------------------------------------------------------
-- Cash-aware party ledger (includes the invoice-description enrichment).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION detailed_ledger(p_party_name text, p_start_date date, p_end_date date)
 RETURNS TABLE(entry_date date, journal_id bigint, description text, party_name text, account_type text, debit numeric, credit numeric, running_balance numeric, created_by text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_is_cash boolean := false;
    v_cash_id bigint;
BEGIN
    SELECT pp.party_id, COALESCE(pp.is_cash,false) INTO v_cash_id, v_is_cash FROM Parties pp WHERE pp.party_name = p_party_name;

    IF v_is_cash THEN
        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM JournalLines jl
        JOIN JournalEntries je  ON jl.journal_id  = je.journal_id
        JOIN ChartOfAccounts a  ON jl.account_id  = a.account_id
        JOIN Parties p          ON p.party_name   = p_party_name
        WHERE a.account_name = 'Cash'
          AND je.entry_date BETWEEN p_start_date AND p_end_date
          AND je.journal_id IN (
              SELECT salesinvoices.journal_id FROM salesinvoices    WHERE customer_id = v_cash_id
              UNION ALL SELECT salesreturns.journal_id FROM salesreturns     WHERE customer_id = v_cash_id
              UNION ALL SELECT purchaseinvoices.journal_id FROM purchaseinvoices WHERE vendor_id  = v_cash_id
              UNION ALL SELECT purchasereturns.journal_id FROM purchasereturns  WHERE vendor_id  = v_cash_id
          )
    ),
    -- Map each journal_id to the user who created the source document
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )
    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        SUM(pl.amount) OVER (ORDER BY pl.entry_date, pl.journal_id
                             ROWS UNBOUNDED PRECEDING)                  AS running_balance,
        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by
    FROM party_ledger pl
    LEFT JOIN journal_author ja ON ja.journal_id = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    ELSE
        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM JournalLines jl
        JOIN JournalEntries je  ON jl.journal_id  = je.journal_id
        JOIN ChartOfAccounts a  ON jl.account_id  = a.account_id
        LEFT JOIN Parties p     ON jl.party_id    = p.party_id
        WHERE p.party_name = p_party_name
          AND je.entry_date BETWEEN p_start_date AND p_end_date
    ),
    -- Map each journal_id to the user who created the source document
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )
    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        SUM(pl.amount) OVER (ORDER BY pl.entry_date, pl.journal_id
                             ROWS UNBOUNDED PRECEDING)                  AS running_balance,
        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by
    FROM party_ledger pl
    LEFT JOIN journal_author ja ON ja.journal_id = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION detailed_ledger2(p_party_name text, p_start_date date, p_end_date date)
 RETURNS TABLE(entry_date date, journal_id bigint, description text, party_name text, account_type text, debit numeric, credit numeric, running_balance numeric, invoice_details jsonb, created_by text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_opening_balance NUMERIC;
    v_is_cash boolean := false;
    v_cash_id bigint;
BEGIN
    SELECT pp.party_id, COALESCE(pp.is_cash,false) INTO v_cash_id, v_is_cash FROM parties pp WHERE pp.party_name = p_party_name;

    IF v_is_cash THEN
    SELECT COALESCE(SUM(jl.debit - jl.credit), 0) INTO v_opening_balance
    FROM journallines jl JOIN journalentries je ON jl.journal_id = je.journal_id
    JOIN chartofaccounts a ON jl.account_id = a.account_id
    WHERE a.account_name = 'Cash' AND je.entry_date < p_start_date
      AND je.journal_id IN (SELECT salesinvoices.journal_id FROM salesinvoices WHERE customer_id = v_cash_id
          UNION ALL SELECT salesreturns.journal_id FROM salesreturns WHERE customer_id = v_cash_id
          UNION ALL SELECT purchaseinvoices.journal_id FROM purchaseinvoices WHERE vendor_id = v_cash_id
          UNION ALL SELECT purchasereturns.journal_id FROM purchasereturns WHERE vendor_id = v_cash_id);

        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM journallines jl
        JOIN journalentries je  ON jl.journal_id   = je.journal_id
        JOIN chartofaccounts a  ON jl.account_id   = a.account_id
        JOIN parties p          ON p.party_name    = p_party_name
        WHERE a.account_name = 'Cash'
          AND je.entry_date BETWEEN p_start_date AND p_end_date
          AND je.journal_id IN (
              SELECT salesinvoices.journal_id FROM salesinvoices    WHERE customer_id = v_cash_id
              UNION ALL SELECT salesreturns.journal_id FROM salesreturns     WHERE customer_id = v_cash_id
              UNION ALL SELECT purchaseinvoices.journal_id FROM purchaseinvoices WHERE vendor_id  = v_cash_id
              UNION ALL SELECT purchasereturns.journal_id FROM purchasereturns  WHERE vendor_id  = v_cash_id
          )
    ),

    journal_source AS (
        SELECT pi.journal_id, 'purchase'::TEXT        AS source_type, pi.purchase_invoice_id  AS source_id FROM purchaseinvoices pi  WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, 'purchase_return'::TEXT AS source_type, pr.purchase_return_id   AS source_id FROM purchasereturns pr   WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, 'sale'::TEXT            AS source_type, si.sales_invoice_id     AS source_id FROM salesinvoices si     WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, 'sale_return'::TEXT     AS source_type, sr.sales_return_id      AS source_id FROM salesreturns sr      WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id,  'receipt'::TEXT         AS source_type, r.receipt_id            AS source_id FROM receipts r           WHERE r.journal_id  IS NOT NULL
        UNION ALL
        SELECT py.journal_id, 'payment'::TEXT         AS source_type, py.payment_id           AS source_id FROM payments py          WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, 'contra'::TEXT          AS source_type, ce.contra_id            AS source_id FROM contra_entries ce    WHERE ce.journal_id IS NOT NULL
    ),

    -- Resolve username from the source document table
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )

    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        v_opening_balance + SUM(pl.amount) OVER (
            ORDER BY pl.entry_date, pl.journal_id
            ROWS UNBOUNDED PRECEDING
        )                                                               AS running_balance,

        -- invoice_details
        CASE js.source_type
            WHEN 'purchase' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Invoice' AS type, pi.purchase_invoice_id, pa.party_name AS vendor, pi.invoice_date, pi.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',pit.quantity,'unit_price',pit.unit_price,'line_total',pit.quantity*pit.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment)) FROM purchaseunits pu WHERE pu.purchase_item_id=pit.purchase_item_id)))
                         FROM purchaseitems pit JOIN items i ON i.item_id=pit.item_id WHERE pit.purchase_invoice_id=pi.purchase_invoice_id) AS items
                    FROM purchaseinvoices pi JOIN parties pa ON pa.party_id=pi.vendor_id WHERE pi.purchase_invoice_id=js.source_id
                ) d
            )
            WHEN 'purchase_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Return' AS type, pr.purchase_return_id, pa.party_name AS vendor, pr.return_date, pr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'unit_price',pri.unit_price,'serial_number',pri.serial_number))
                         FROM purchasereturnitems pri JOIN items i ON i.item_id=pri.item_id WHERE pri.purchase_return_id=pr.purchase_return_id) AS items
                    FROM purchasereturns pr JOIN parties pa ON pa.party_id=pr.vendor_id WHERE pr.purchase_return_id=js.source_id
                ) d
            )
            WHEN 'sale' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Invoice' AS type, si.sales_invoice_id, pa.party_name AS customer, si.invoice_date, si.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',sitm.quantity,'unit_price',sitm.unit_price,'line_total',sitm.quantity*sitm.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment,'sold_price',su.sold_price))
                                       FROM soldunits su JOIN purchaseunits pu ON su.unit_id=pu.unit_id WHERE su.sales_item_id=sitm.sales_item_id)))
                         FROM salesitems sitm JOIN items i ON i.item_id=sitm.item_id WHERE sitm.sales_invoice_id=si.sales_invoice_id) AS items
                    FROM salesinvoices si JOIN parties pa ON pa.party_id=si.customer_id WHERE si.sales_invoice_id=js.source_id
                ) d
            )
            WHEN 'sale_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Return' AS type, sr.sales_return_id, pa.party_name AS customer, sr.return_date, sr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'sold_price',sri.sold_price,'cost_price',sri.cost_price,'serial_number',sri.serial_number))
                         FROM salesreturnitems sri JOIN items i ON i.item_id=sri.item_id WHERE sri.sales_return_id=sr.sales_return_id) AS items
                    FROM salesreturns sr JOIN parties pa ON pa.party_id=sr.customer_id WHERE sr.sales_return_id=js.source_id
                ) d
            )
            WHEN 'receipt' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Receipt' AS type, r.receipt_id, pa.party_name AS party, r.receipt_date, r.amount, r.method, r.reference_no, r.notes, r.description
                    FROM receipts r JOIN parties pa ON pa.party_id=r.party_id WHERE r.receipt_id=js.source_id
                ) d
            )
            WHEN 'payment' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Payment' AS type, py.payment_id, pa.party_name AS party, py.payment_date, py.amount, py.method, py.reference_no, py.notes, py.description
                    FROM payments py JOIN parties pa ON pa.party_id=py.party_id WHERE py.payment_id=js.source_id
                ) d
            )
            WHEN 'contra' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Contra Entry' AS type, ce.contra_id, fp.party_name AS from_party, tp.party_name AS to_party,
                           ce.contra_date, ce.amount, ce.method, ce.reference_no, ce.description
                    FROM contra_entries ce
                    JOIN parties fp ON fp.party_id = ce.from_party_id
                    JOIN parties tp ON tp.party_id = ce.to_party_id
                    WHERE ce.contra_id = js.source_id
                ) d
            )
            ELSE NULL
        END                                                             AS invoice_details,

        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by

    FROM party_ledger pl
    LEFT JOIN journal_source js  ON js.journal_id  = pl.journal_id
    LEFT JOIN journal_author ja  ON ja.journal_id  = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    ELSE

    -- Opening balance: sum of (debit - credit) before p_start_date
    SELECT COALESCE(SUM(jl.debit - jl.credit), 0)
    INTO   v_opening_balance
    FROM   journallines jl
    JOIN   journalentries je ON jl.journal_id = je.journal_id
    JOIN   parties p         ON jl.party_id   = p.party_id
    WHERE  p.party_name = p_party_name
      AND  je.entry_date < p_start_date;

        RETURN QUERY
        WITH party_ledger AS (
        SELECT
            je.entry_date                   AS entry_date,
            je.journal_id                   AS journal_id,
            (je.description || COALESCE(' — ' || NULLIF((
                SELECT x.d FROM (
                    SELECT si.description AS d FROM salesinvoices si    WHERE si.journal_id = je.journal_id
                    UNION ALL SELECT pi.description FROM purchaseinvoices pi WHERE pi.journal_id = je.journal_id
                    UNION ALL SELECT sr.description FROM salesreturns sr     WHERE sr.journal_id = je.journal_id
                    UNION ALL SELECT pr.description FROM purchasereturns pr  WHERE pr.journal_id = je.journal_id
                ) x WHERE x.d IS NOT NULL AND btrim(x.d) <> '' LIMIT 1
            ), ''), ''))::TEXT            AS description,
            p.party_name::TEXT              AS party_name,
            a.account_name::TEXT            AS account_name,
            jl.debit                        AS debit,
            jl.credit                       AS credit,
            (jl.debit - jl.credit)          AS amount
        FROM journallines jl
        JOIN journalentries je  ON jl.journal_id   = je.journal_id
        JOIN chartofaccounts a  ON jl.account_id   = a.account_id
        LEFT JOIN parties p     ON jl.party_id     = p.party_id
        WHERE p.party_name = p_party_name
          AND je.entry_date BETWEEN p_start_date AND p_end_date
    ),

    journal_source AS (
        SELECT pi.journal_id, 'purchase'::TEXT        AS source_type, pi.purchase_invoice_id  AS source_id FROM purchaseinvoices pi  WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, 'purchase_return'::TEXT AS source_type, pr.purchase_return_id   AS source_id FROM purchasereturns pr   WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, 'sale'::TEXT            AS source_type, si.sales_invoice_id     AS source_id FROM salesinvoices si     WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, 'sale_return'::TEXT     AS source_type, sr.sales_return_id      AS source_id FROM salesreturns sr      WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id,  'receipt'::TEXT         AS source_type, r.receipt_id            AS source_id FROM receipts r           WHERE r.journal_id  IS NOT NULL
        UNION ALL
        SELECT py.journal_id, 'payment'::TEXT         AS source_type, py.payment_id           AS source_id FROM payments py          WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, 'contra'::TEXT          AS source_type, ce.contra_id            AS source_id FROM contra_entries ce    WHERE ce.journal_id IS NOT NULL
    ),

    -- Resolve username from the source document table
    journal_author AS (
        SELECT pi.journal_id, u.username::TEXT
        FROM purchaseinvoices pi LEFT JOIN auth_user u ON u.id = pi.created_by
        WHERE pi.journal_id IS NOT NULL
        UNION ALL
        SELECT pr.journal_id, u.username::TEXT
        FROM purchasereturns pr LEFT JOIN auth_user u ON u.id = pr.created_by
        WHERE pr.journal_id IS NOT NULL
        UNION ALL
        SELECT si.journal_id, u.username::TEXT
        FROM salesinvoices si LEFT JOIN auth_user u ON u.id = si.created_by
        WHERE si.journal_id IS NOT NULL
        UNION ALL
        SELECT sr.journal_id, u.username::TEXT
        FROM salesreturns sr LEFT JOIN auth_user u ON u.id = sr.created_by
        WHERE sr.journal_id IS NOT NULL
        UNION ALL
        SELECT r.journal_id, u.username::TEXT
        FROM receipts r LEFT JOIN auth_user u ON u.id = r.created_by
        WHERE r.journal_id IS NOT NULL
        UNION ALL
        SELECT py.journal_id, u.username::TEXT
        FROM payments py LEFT JOIN auth_user u ON u.id = py.created_by
        WHERE py.journal_id IS NOT NULL
        UNION ALL
        SELECT ce.journal_id, u.username::TEXT
        FROM contra_entries ce LEFT JOIN auth_user u ON u.id = ce.created_by
        WHERE ce.journal_id IS NOT NULL
    )

    SELECT
        pl.entry_date,
        pl.journal_id,
        pl.description,
        pl.party_name,
        pl.account_name                                                 AS account_type,
        pl.debit,
        pl.credit,
        v_opening_balance + SUM(pl.amount) OVER (
            ORDER BY pl.entry_date, pl.journal_id
            ROWS UNBOUNDED PRECEDING
        )                                                               AS running_balance,

        -- invoice_details
        CASE js.source_type
            WHEN 'purchase' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Invoice' AS type, pi.purchase_invoice_id, pa.party_name AS vendor, pi.invoice_date, pi.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',pit.quantity,'unit_price',pit.unit_price,'line_total',pit.quantity*pit.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment)) FROM purchaseunits pu WHERE pu.purchase_item_id=pit.purchase_item_id)))
                         FROM purchaseitems pit JOIN items i ON i.item_id=pit.item_id WHERE pit.purchase_invoice_id=pi.purchase_invoice_id) AS items
                    FROM purchaseinvoices pi JOIN parties pa ON pa.party_id=pi.vendor_id WHERE pi.purchase_invoice_id=js.source_id
                ) d
            )
            WHEN 'purchase_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Purchase Return' AS type, pr.purchase_return_id, pa.party_name AS vendor, pr.return_date, pr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'unit_price',pri.unit_price,'serial_number',pri.serial_number))
                         FROM purchasereturnitems pri JOIN items i ON i.item_id=pri.item_id WHERE pri.purchase_return_id=pr.purchase_return_id) AS items
                    FROM purchasereturns pr JOIN parties pa ON pa.party_id=pr.vendor_id WHERE pr.purchase_return_id=js.source_id
                ) d
            )
            WHEN 'sale' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Invoice' AS type, si.sales_invoice_id, pa.party_name AS customer, si.invoice_date, si.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'qty',sitm.quantity,'unit_price',sitm.unit_price,'line_total',sitm.quantity*sitm.unit_price,
                            'serials',(SELECT json_agg(json_build_object('serial',pu.serial_number,'comment',pu.serial_comment,'sold_price',su.sold_price))
                                       FROM soldunits su JOIN purchaseunits pu ON su.unit_id=pu.unit_id WHERE su.sales_item_id=sitm.sales_item_id)))
                         FROM salesitems sitm JOIN items i ON i.item_id=sitm.item_id WHERE sitm.sales_invoice_id=si.sales_invoice_id) AS items
                    FROM salesinvoices si JOIN parties pa ON pa.party_id=si.customer_id WHERE si.sales_invoice_id=js.source_id
                ) d
            )
            WHEN 'sale_return' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Sale Return' AS type, sr.sales_return_id, pa.party_name AS customer, sr.return_date, sr.total_amount,
                        (SELECT json_agg(json_build_object('item_name',i.item_name,'sold_price',sri.sold_price,'cost_price',sri.cost_price,'serial_number',sri.serial_number))
                         FROM salesreturnitems sri JOIN items i ON i.item_id=sri.item_id WHERE sri.sales_return_id=sr.sales_return_id) AS items
                    FROM salesreturns sr JOIN parties pa ON pa.party_id=sr.customer_id WHERE sr.sales_return_id=js.source_id
                ) d
            )
            WHEN 'receipt' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Receipt' AS type, r.receipt_id, pa.party_name AS party, r.receipt_date, r.amount, r.method, r.reference_no, r.notes, r.description
                    FROM receipts r JOIN parties pa ON pa.party_id=r.party_id WHERE r.receipt_id=js.source_id
                ) d
            )
            WHEN 'payment' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Payment' AS type, py.payment_id, pa.party_name AS party, py.payment_date, py.amount, py.method, py.reference_no, py.notes, py.description
                    FROM payments py JOIN parties pa ON pa.party_id=py.party_id WHERE py.payment_id=js.source_id
                ) d
            )
            WHEN 'contra' THEN (
                SELECT to_jsonb(d) FROM (
                    SELECT 'Contra Entry' AS type, ce.contra_id, fp.party_name AS from_party, tp.party_name AS to_party,
                           ce.contra_date, ce.amount, ce.method, ce.reference_no, ce.description
                    FROM contra_entries ce
                    JOIN parties fp ON fp.party_id = ce.from_party_id
                    JOIN parties tp ON tp.party_id = ce.to_party_id
                    WHERE ce.contra_id = js.source_id
                ) d
            )
            ELSE NULL
        END                                                             AS invoice_details,

        COALESCE(ja.username::TEXT, 'N/A')                              AS created_by

    FROM party_ledger pl
    LEFT JOIN journal_source js  ON js.journal_id  = pl.journal_id
    LEFT JOIN journal_author ja  ON ja.journal_id  = pl.journal_id
    ORDER BY pl.entry_date, pl.journal_id;
    END IF;
END;
$function$;

-- ----------------------------------------------------------------------------
-- Seed the sentinel cash parties eagerly (get-or-create; idempotent).
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    PERFORM get_cash_party_id('sale');
    PERFORM get_cash_party_id('purchase');
END;
$$;

-- ----------------------------------------------------------------------------
-- Backfill: rebuild the journals of cash-party documents that were posted
-- BEFORE the party was cash-flagged. Those journals carry party AR/AP lines
-- instead of Cash lines, so they are invisible to the cash-party ledger and
-- leave a residual (never-collectable) party balance. Only documents whose
-- journal still has a party-tagged line are rebuilt, so this is a no-op on
-- every subsequent run. The swap (party AR/AP line -> Cash line) is
-- balance-sheet neutral: the trial balance and P&L are unchanged.
-- ----------------------------------------------------------------------------
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT si.sales_invoice_id AS id
        FROM SalesInvoices si
        JOIN Parties p ON p.party_id = si.customer_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = si.journal_id
                        AND jl.party_id = si.customer_id)
    LOOP
        PERFORM rebuild_sales_journal(r.id);
    END LOOP;

    FOR r IN
        SELECT sr.sales_return_id AS id
        FROM SalesReturns sr
        JOIN Parties p ON p.party_id = sr.customer_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = sr.journal_id
                        AND jl.party_id = sr.customer_id)
    LOOP
        PERFORM rebuild_sales_return_journal(r.id);
    END LOOP;

    FOR r IN
        SELECT pi.purchase_invoice_id AS id
        FROM PurchaseInvoices pi
        JOIN Parties p ON p.party_id = pi.vendor_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = pi.journal_id
                        AND jl.party_id = pi.vendor_id)
    LOOP
        PERFORM rebuild_purchase_journal(r.id);
    END LOOP;

    FOR r IN
        SELECT pr.purchase_return_id AS id
        FROM PurchaseReturns pr
        JOIN Parties p ON p.party_id = pr.vendor_id
        WHERE COALESCE(p.is_cash, false)
          AND EXISTS (SELECT 1 FROM JournalLines jl
                      WHERE jl.journal_id = pr.journal_id
                        AND jl.party_id = pr.vendor_id)
    LOOP
        PERFORM rebuild_purchase_return_journal(r.id);
    END LOOP;
END;
$$;

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id BIGSERIAL PRIMARY KEY,
    document_type TEXT NOT NULL,
    document_id BIGINT NOT NULL,
    file_kind TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_by INTEGER NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_attachments_document_type_check CHECK (
        document_type IN ('sale', 'purchase', 'sale_return', 'purchase_return', 'payment', 'receipt', 'contra')
    ),
    CONSTRAINT document_attachments_file_kind_check CHECK (file_kind IN ('image', 'pdf')),
    CONSTRAINT document_attachments_file_size_check CHECK (file_size > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS document_attachments_one_per_kind
    ON document_attachments (document_type, document_id, file_kind);

CREATE INDEX IF NOT EXISTS document_attachments_document_idx
    ON document_attachments (document_type, document_id);

-- Bump tenant schema version.
UPDATE tenant_schema_version
SET version = GREATEST(version, 6),
    applied_at = CURRENT_TIMESTAMP
WHERE id = true;
