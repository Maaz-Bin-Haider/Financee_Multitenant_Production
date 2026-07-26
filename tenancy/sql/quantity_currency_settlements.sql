-- Phase 18 multi-currency and realized settlement foundation, v14.
DO $$
BEGIN
 IF to_regclass('tenant_schema_metadata') IS NULL OR NOT EXISTS(
  SELECT 1 FROM tenant_schema_metadata
   WHERE id=true AND family='quantity' AND version>=13
 ) THEN
  RAISE EXCEPTION 'Quantity currency rollout refused: family/version mismatch.';
 END IF;
END;
$$;

ALTER TABLE purchase_invoices
 ADD COLUMN IF NOT EXISTS transaction_currency_code char(3),
 ADD COLUMN IF NOT EXISTS exchange_rate numeric(20,10) NOT NULL DEFAULT 1,
 ADD COLUMN IF NOT EXISTS subtotal_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS line_discount_total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS invoice_discount_total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS tax_total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS settled_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS remaining_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS returned_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS returned_carrying_base numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS settled_carrying_base numeric(24,6) NOT NULL DEFAULT 0;
ALTER TABLE sale_invoices
 ADD COLUMN IF NOT EXISTS transaction_currency_code char(3),
 ADD COLUMN IF NOT EXISTS exchange_rate numeric(20,10) NOT NULL DEFAULT 1,
 ADD COLUMN IF NOT EXISTS subtotal_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS line_discount_total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS invoice_discount_total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS tax_total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS total_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS settled_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS remaining_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS returned_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS returned_carrying_base numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS settled_carrying_base numeric(24,6) NOT NULL DEFAULT 0;

UPDATE purchase_invoices SET
 transaction_currency_code=(SELECT base_currency_code
  FROM tenant_schema_metadata WHERE id=true),
 subtotal_foreign=subtotal_base,line_discount_total_foreign=line_discount_total_base,
 invoice_discount_total_foreign=invoice_discount_total_base,
 tax_total_foreign=tax_total_base,total_foreign=total_base,
 remaining_foreign=CASE WHEN purchase_type='credit' AND status='posted'
  THEN total_base ELSE 0 END
WHERE transaction_currency_code IS NULL;
UPDATE sale_invoices SET
 transaction_currency_code=(SELECT base_currency_code
  FROM tenant_schema_metadata WHERE id=true),
 subtotal_foreign=subtotal_base,line_discount_total_foreign=line_discount_total_base,
 invoice_discount_total_foreign=invoice_discount_total_base,
 tax_total_foreign=tax_total_base,total_foreign=total_base,
 remaining_foreign=CASE WHEN sale_type='credit' AND status='posted'
  THEN total_base ELSE 0 END
WHERE transaction_currency_code IS NULL;
ALTER TABLE purchase_invoices ALTER COLUMN transaction_currency_code SET NOT NULL;
ALTER TABLE sale_invoices ALTER COLUMN transaction_currency_code SET NOT NULL;

CREATE OR REPLACE FUNCTION quantity_default_document_currency()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.transaction_currency_code IS NULL THEN
  SELECT base_currency_code INTO NEW.transaction_currency_code
   FROM tenant_schema_metadata WHERE id=true;
 END IF;
 RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS purchase_invoice_currency_default ON purchase_invoices;
CREATE TRIGGER purchase_invoice_currency_default
BEFORE INSERT ON purchase_invoices FOR EACH ROW
EXECUTE FUNCTION quantity_default_document_currency();
DROP TRIGGER IF EXISTS sale_invoice_currency_default ON sale_invoices;
CREATE TRIGGER sale_invoice_currency_default
BEFORE INSERT ON sale_invoices FOR EACH ROW
EXECUTE FUNCTION quantity_default_document_currency();

ALTER TABLE purchase_lines
 ADD COLUMN IF NOT EXISTS unit_cost_foreign numeric(20,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS gross_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS line_discount_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS invoice_discount_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS taxable_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS tax_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS line_total_foreign numeric(24,6) NOT NULL DEFAULT 0;
ALTER TABLE sale_lines
 ADD COLUMN IF NOT EXISTS unit_price_foreign numeric(20,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS gross_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS line_discount_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS invoice_discount_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS taxable_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS tax_foreign numeric(24,6) NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS line_total_foreign numeric(24,6) NOT NULL DEFAULT 0;

SELECT set_config('financee.purchase_engine','allowed',true);
UPDATE purchase_lines SET unit_cost_foreign=unit_cost_base,gross_foreign=gross_base,
 line_discount_foreign=line_discount_base,
 invoice_discount_foreign=invoice_discount_base,taxable_foreign=taxable_base,
 tax_foreign=tax_base,line_total_foreign=line_total_base
WHERE unit_cost_foreign=0 AND unit_cost_base<>0;
SELECT set_config('financee.purchase_engine','',true);
SELECT set_config('financee.sale_engine','allowed',true);
UPDATE sale_lines SET unit_price_foreign=unit_price_base,gross_foreign=gross_base,
 line_discount_foreign=line_discount_base,
 invoice_discount_foreign=invoice_discount_base,taxable_foreign=taxable_base,
 tax_foreign=tax_base,line_total_foreign=line_total_base
WHERE unit_price_foreign=0 AND unit_price_base<>0;
SELECT set_config('financee.sale_engine','',true);

CREATE TABLE IF NOT EXISTS foreign_payments(
 payment_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 document_number varchar(32) NOT NULL UNIQUE,
 payment_date date NOT NULL,
 vendor_name varchar(200) NOT NULL,
 transaction_currency_code char(3) NOT NULL,
 settlement_rate numeric(20,10) NOT NULL,
 foreign_amount numeric(24,6) NOT NULL,
 base_cash_amount numeric(24,6) NOT NULL,
 payment_account_code varchar(20) NOT NULL,
 journal_id bigint NOT NULL UNIQUE REFERENCES journal_entries(journal_id),
 reversal_journal_id bigint UNIQUE REFERENCES journal_entries(journal_id),
 status varchar(10) NOT NULL DEFAULT 'posted',
 idempotency_key varchar(100) NOT NULL UNIQUE,
 created_by integer,created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT foreign_payment_values CHECK(settlement_rate>0 AND foreign_amount>0
  AND base_cash_amount>0 AND payment_account_code IN('1000','1100')),
 CONSTRAINT foreign_payment_status CHECK(status IN('posted','reversed'))
);
CREATE TABLE IF NOT EXISTS payment_allocations(
 allocation_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 payment_id bigint NOT NULL REFERENCES foreign_payments(payment_id),
 purchase_invoice_id bigint NOT NULL REFERENCES purchase_invoices(purchase_invoice_id),
 allocation_order integer NOT NULL,
 foreign_amount numeric(24,6) NOT NULL,
 invoice_carrying_base numeric(24,6) NOT NULL,
 settlement_base numeric(24,6) NOT NULL,
 realized_gain_base numeric(24,6) NOT NULL DEFAULT 0,
 realized_loss_base numeric(24,6) NOT NULL DEFAULT 0,
 CONSTRAINT payment_allocation_values CHECK(foreign_amount>0
  AND invoice_carrying_base>=0 AND settlement_base>0
  AND realized_gain_base>=0 AND realized_loss_base>=0
  AND NOT(realized_gain_base>0 AND realized_loss_base>0)),
 UNIQUE(payment_id,allocation_order),UNIQUE(payment_id,purchase_invoice_id)
);
CREATE TABLE IF NOT EXISTS foreign_receipts(
 receipt_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 document_number varchar(32) NOT NULL UNIQUE,
 receipt_date date NOT NULL,
 customer_name varchar(200) NOT NULL,
 transaction_currency_code char(3) NOT NULL,
 settlement_rate numeric(20,10) NOT NULL,
 foreign_amount numeric(24,6) NOT NULL,
 base_cash_amount numeric(24,6) NOT NULL,
 receipt_account_code varchar(20) NOT NULL,
 journal_id bigint NOT NULL UNIQUE REFERENCES journal_entries(journal_id),
 reversal_journal_id bigint UNIQUE REFERENCES journal_entries(journal_id),
 status varchar(10) NOT NULL DEFAULT 'posted',
 idempotency_key varchar(100) NOT NULL UNIQUE,
 created_by integer,created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT foreign_receipt_values CHECK(settlement_rate>0 AND foreign_amount>0
  AND base_cash_amount>0 AND receipt_account_code IN('1000','1100')),
 CONSTRAINT foreign_receipt_status CHECK(status IN('posted','reversed'))
);
CREATE TABLE IF NOT EXISTS receipt_allocations(
 allocation_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 receipt_id bigint NOT NULL REFERENCES foreign_receipts(receipt_id),
 sale_invoice_id bigint NOT NULL REFERENCES sale_invoices(sale_invoice_id),
 allocation_order integer NOT NULL,
 foreign_amount numeric(24,6) NOT NULL,
 invoice_carrying_base numeric(24,6) NOT NULL,
 settlement_base numeric(24,6) NOT NULL,
 realized_gain_base numeric(24,6) NOT NULL DEFAULT 0,
 realized_loss_base numeric(24,6) NOT NULL DEFAULT 0,
 CONSTRAINT receipt_allocation_values CHECK(foreign_amount>0
  AND invoice_carrying_base>=0 AND settlement_base>0
  AND realized_gain_base>=0 AND realized_loss_base>=0
  AND NOT(realized_gain_base>0 AND realized_loss_base>0)),
 UNIQUE(receipt_id,allocation_order),UNIQUE(receipt_id,sale_invoice_id)
);

CREATE OR REPLACE FUNCTION quantity_finalize_currency_document(
 p_kind text,p_document_id bigint,p_foreign jsonb,p_currency char(3),
 p_rate numeric,p_user integer
) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE base_code char(3);x jsonb;n integer:=0;is_credit boolean;
BEGIN
 SELECT base_currency_code INTO base_code FROM tenant_schema_metadata WHERE id=true;
 IF p_currency IS NULL OR p_currency!~'^[A-Z]{3}$' OR p_rate IS NULL OR p_rate<=0
  OR (p_currency=base_code AND p_rate<>1) THEN
  RAISE EXCEPTION 'Transaction currency or exchange rate is invalid.'
   USING ERRCODE='check_violation';
 END IF;
 IF p_kind='purchase' THEN
  SELECT purchase_type='credit' INTO is_credit FROM purchase_invoices
   WHERE purchase_invoice_id=p_document_id FOR UPDATE;
  PERFORM set_config('financee.purchase_engine','allowed',true);
  UPDATE purchase_invoices SET transaction_currency_code=p_currency,
   exchange_rate=p_rate,subtotal_foreign=(p_foreign->>'subtotal_base')::numeric,
   line_discount_total_foreign=(p_foreign->>'line_discount_total_base')::numeric,
   invoice_discount_total_foreign=(p_foreign->>'invoice_discount_total_base')::numeric,
   tax_total_foreign=(p_foreign->>'tax_total_base')::numeric,
   total_foreign=(p_foreign->>'total_base')::numeric,
   remaining_foreign=CASE WHEN is_credit THEN (p_foreign->>'total_base')::numeric ELSE 0 END
   WHERE purchase_invoice_id=p_document_id;
  FOR x IN SELECT value FROM jsonb_array_elements(p_foreign->'lines') LOOP
   n:=n+1;
   UPDATE purchase_lines SET
    unit_cost_foreign=round((x->>'gross_base')::numeric/quantity,6),
    gross_foreign=(x->>'gross_base')::numeric,
    line_discount_foreign=(x->>'line_discount_base')::numeric,
    invoice_discount_foreign=(x->>'invoice_discount_base')::numeric,
    taxable_foreign=(x->>'taxable_base')::numeric,
    tax_foreign=(x->>'tax_base')::numeric,
    line_total_foreign=(x->>'line_total_base')::numeric
    WHERE purchase_invoice_id=p_document_id AND line_number=n;
  END LOOP;
  PERFORM set_config('financee.purchase_engine','',true);
 ELSIF p_kind='sale' THEN
  SELECT sale_type='credit' INTO is_credit FROM sale_invoices
   WHERE sale_invoice_id=p_document_id FOR UPDATE;
  PERFORM set_config('financee.sale_engine','allowed',true);
  UPDATE sale_invoices SET transaction_currency_code=p_currency,
   exchange_rate=p_rate,subtotal_foreign=(p_foreign->>'subtotal_base')::numeric,
   line_discount_total_foreign=(p_foreign->>'line_discount_total_base')::numeric,
   invoice_discount_total_foreign=(p_foreign->>'invoice_discount_total_base')::numeric,
   tax_total_foreign=(p_foreign->>'tax_total_base')::numeric,
   total_foreign=(p_foreign->>'total_base')::numeric,
   remaining_foreign=CASE WHEN is_credit THEN (p_foreign->>'total_base')::numeric ELSE 0 END
   WHERE sale_invoice_id=p_document_id;
  FOR x IN SELECT value FROM jsonb_array_elements(p_foreign->'lines') LOOP
   n:=n+1;
   UPDATE sale_lines SET
    unit_price_foreign=round((x->>'gross_base')::numeric/quantity,6),
    gross_foreign=(x->>'gross_base')::numeric,
    line_discount_foreign=(x->>'line_discount_base')::numeric,
    invoice_discount_foreign=(x->>'invoice_discount_base')::numeric,
    taxable_foreign=(x->>'taxable_base')::numeric,
    tax_foreign=(x->>'tax_base')::numeric,
    line_total_foreign=(x->>'line_total_base')::numeric
    WHERE sale_invoice_id=p_document_id AND line_number=n;
  END LOOP;
  PERFORM set_config('financee.sale_engine','',true);
 ELSE RAISE EXCEPTION 'Invalid currency document kind.'
  USING ERRCODE='check_violation'; END IF;
 RETURN jsonb_build_object('transaction_currency_code',p_currency,
  'exchange_rate',p_rate,'total_foreign',p_foreign->'total_base',
  'total_base',CASE WHEN p_kind='purchase' THEN
   (SELECT total_base FROM purchase_invoices WHERE purchase_invoice_id=p_document_id)
   ELSE (SELECT total_base FROM sale_invoices WHERE sale_invoice_id=p_document_id) END);
END;
$$;

CREATE OR REPLACE FUNCTION quantity_settle_foreign_purchase(data jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE inv purchase_invoices%ROWTYPE;pid bigint;num text;d date;amt numeric;
 rate numeric;cash numeric;carry numeric;diff numeric;j bigint;acct varchar;
 key text;usr integer;lines jsonb;
BEGIN
 BEGIN
  SELECT * INTO inv FROM purchase_invoices
   WHERE purchase_invoice_id=(data->>'purchase_invoice_id')::bigint FOR UPDATE;
  d:=(data->>'settlement_date')::date;amt:=(data->>'foreign_amount')::numeric;
  rate:=(data->>'settlement_rate')::numeric;
  usr:=NULLIF(data->>'created_by_id','')::integer;
 EXCEPTION WHEN others THEN RAISE EXCEPTION 'Foreign payment values are invalid.'
  USING ERRCODE='check_violation'; END;
 key:=btrim(COALESCE(data->>'idempotency_key',''));
 acct:=COALESCE(NULLIF(data->>'payment_account_code',''),'1100');
 IF NOT FOUND OR inv.status<>'posted' OR inv.purchase_type<>'credit'
  OR inv.transaction_currency_code=(SELECT base_currency_code FROM tenant_schema_metadata WHERE id=true)
  OR d<inv.invoice_date OR amt<=0 OR rate<=0 OR amt>inv.remaining_foreign
  OR key='' OR acct NOT IN('1000','1100') THEN
  RAISE EXCEPTION 'Foreign payment is not eligible.' USING ERRCODE='check_violation';
 END IF;
 SELECT payment_id INTO pid FROM foreign_payments WHERE idempotency_key=key;
 IF FOUND THEN RETURN jsonb_build_object('payment_id',pid,'idempotent',true); END IF;
 cash:=round(amt*rate,2);
 carry:=CASE WHEN amt=inv.remaining_foreign THEN
  inv.total_base-inv.returned_carrying_base-inv.settled_carrying_base
  ELSE round(inv.total_base*amt/inv.total_foreign,2) END;
 diff:=cash-carry;pid:=nextval('foreign_payments_payment_id_seq');
 num:=quantity_next_document_number('payment');
 lines:=jsonb_build_array(jsonb_build_object('account_code','2000','debit',carry,
   'credit',0,'description','Foreign payable released'),
   jsonb_build_object('account_code',acct,'debit',0,'credit',cash,
   'description','Foreign payment'));
 IF diff<>0 THEN lines:=lines||jsonb_build_array(jsonb_build_object(
   'account_code',CASE WHEN diff>0 THEN '1990' ELSE '4910' END,
   'debit',CASE WHEN diff>0 THEN diff ELSE 0 END,
   'credit',CASE WHEN diff<0 THEN -diff ELSE 0 END,'description','Realized FX')); END IF;
 j:=quantity_post_journal(d,'Foreign payment '||num,'foreign_payment',pid,num,usr,
  lines);
 INSERT INTO foreign_payments(payment_id,document_number,payment_date,vendor_name,
  transaction_currency_code,settlement_rate,foreign_amount,base_cash_amount,
  payment_account_code,journal_id,idempotency_key,created_by)
 VALUES(pid,num,d,inv.vendor_name,inv.transaction_currency_code,rate,amt,cash,
  acct,j,key,usr);
 INSERT INTO payment_allocations(payment_id,purchase_invoice_id,allocation_order,
  foreign_amount,invoice_carrying_base,settlement_base,realized_gain_base,
  realized_loss_base) VALUES(pid,inv.purchase_invoice_id,1,amt,carry,cash,
  GREATEST(-diff,0),GREATEST(diff,0));
 PERFORM set_config('financee.purchase_engine','allowed',true);
 UPDATE purchase_invoices SET settled_foreign=settled_foreign+amt,
  remaining_foreign=remaining_foreign-amt,
  settled_carrying_base=settled_carrying_base+carry
  WHERE purchase_invoice_id=inv.purchase_invoice_id;
 PERFORM set_config('financee.purchase_engine','',true);
 RETURN jsonb_build_object('payment_id',pid,'document_number',num,'idempotent',false,
  'foreign_amount',amt,'settlement_base',cash,'carrying_base',carry,
  'realized_gain_base',GREATEST(-diff,0),'realized_loss_base',GREATEST(diff,0),
  'remaining_foreign',inv.remaining_foreign-amt,'journal_id',j);
END;
$$;

CREATE OR REPLACE FUNCTION quantity_settle_foreign_sale(data jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE inv sale_invoices%ROWTYPE;rid bigint;num text;d date;amt numeric;
 rate numeric;cash numeric;carry numeric;diff numeric;j bigint;acct varchar;
 key text;usr integer;lines jsonb;
BEGIN
 BEGIN
  SELECT * INTO inv FROM sale_invoices
   WHERE sale_invoice_id=(data->>'sale_invoice_id')::bigint FOR UPDATE;
  d:=(data->>'settlement_date')::date;amt:=(data->>'foreign_amount')::numeric;
  rate:=(data->>'settlement_rate')::numeric;
  usr:=NULLIF(data->>'created_by_id','')::integer;
 EXCEPTION WHEN others THEN RAISE EXCEPTION 'Foreign receipt values are invalid.'
  USING ERRCODE='check_violation'; END;
 key:=btrim(COALESCE(data->>'idempotency_key',''));
 acct:=COALESCE(NULLIF(data->>'receipt_account_code',''),'1100');
 IF NOT FOUND OR inv.status<>'posted' OR inv.sale_type<>'credit'
  OR inv.transaction_currency_code=(SELECT base_currency_code FROM tenant_schema_metadata WHERE id=true)
  OR d<inv.invoice_date OR amt<=0 OR rate<=0 OR amt>inv.remaining_foreign
  OR key='' OR acct NOT IN('1000','1100') THEN
  RAISE EXCEPTION 'Foreign receipt is not eligible.' USING ERRCODE='check_violation';
 END IF;
 SELECT receipt_id INTO rid FROM foreign_receipts WHERE idempotency_key=key;
 IF FOUND THEN RETURN jsonb_build_object('receipt_id',rid,'idempotent',true); END IF;
 cash:=round(amt*rate,2);
 carry:=CASE WHEN amt=inv.remaining_foreign THEN
  inv.total_base-inv.returned_carrying_base-inv.settled_carrying_base
  ELSE round(inv.total_base*amt/inv.total_foreign,2) END;
 diff:=cash-carry;rid:=nextval('foreign_receipts_receipt_id_seq');
 num:=quantity_next_document_number('receipt');
 lines:=jsonb_build_array(jsonb_build_object('account_code',acct,'debit',cash,
   'credit',0,'description','Foreign receipt'),
   jsonb_build_object('account_code','1200','debit',0,'credit',carry,
   'description','Foreign receivable released'));
 IF diff<>0 THEN lines:=lines||jsonb_build_array(jsonb_build_object(
   'account_code',CASE WHEN diff>0 THEN '4910' ELSE '1990' END,
   'debit',CASE WHEN diff<0 THEN -diff ELSE 0 END,
   'credit',CASE WHEN diff>0 THEN diff ELSE 0 END,'description','Realized FX')); END IF;
 j:=quantity_post_journal(d,'Foreign receipt '||num,'foreign_receipt',rid,num,usr,
  lines);
 INSERT INTO foreign_receipts(receipt_id,document_number,receipt_date,customer_name,
  transaction_currency_code,settlement_rate,foreign_amount,base_cash_amount,
  receipt_account_code,journal_id,idempotency_key,created_by)
 VALUES(rid,num,d,inv.customer_name,inv.transaction_currency_code,rate,amt,cash,
  acct,j,key,usr);
 INSERT INTO receipt_allocations(receipt_id,sale_invoice_id,allocation_order,
  foreign_amount,invoice_carrying_base,settlement_base,realized_gain_base,
  realized_loss_base) VALUES(rid,inv.sale_invoice_id,1,amt,carry,cash,
  GREATEST(diff,0),GREATEST(-diff,0));
 PERFORM set_config('financee.sale_engine','allowed',true);
 UPDATE sale_invoices SET settled_foreign=settled_foreign+amt,
  remaining_foreign=remaining_foreign-amt,
  settled_carrying_base=settled_carrying_base+carry
  WHERE sale_invoice_id=inv.sale_invoice_id;
 PERFORM set_config('financee.sale_engine','',true);
 RETURN jsonb_build_object('receipt_id',rid,'document_number',num,'idempotent',false,
  'foreign_amount',amt,'settlement_base',cash,'carrying_base',carry,
  'realized_gain_base',GREATEST(diff,0),'realized_loss_base',GREATEST(-diff,0),
  'remaining_foreign',inv.remaining_foreign-amt,'journal_id',j);
END;
$$;

-- Returns are valued at the immutable invoice rate. They can reduce only the
-- unsettled portion; already-realized settlements are never rewritten.
CREATE OR REPLACE FUNCTION quantity_apply_foreign_return(
 p_kind text,p_return_id bigint,p_reverse boolean DEFAULT false
) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE invoice_id bigint;invoice_max bigint;rate numeric;base_value numeric;foreign_value numeric;
 current_returned numeric;settled numeric;total_foreign_value numeric;
 currency_code char(3);base_code char(3);
BEGIN
 SELECT base_currency_code INTO base_code FROM tenant_schema_metadata WHERE id=true;
 IF p_kind='purchase_return' THEN
  SELECT min(pl.purchase_invoice_id),max(pl.purchase_invoice_id),
         r.total_base
   INTO invoice_id,invoice_max,base_value
   FROM purchase_return_invoices r
   JOIN purchase_return_lines rl USING(purchase_return_id)
   JOIN purchase_lines pl ON pl.purchase_line_id=rl.source_purchase_line_id
   WHERE r.purchase_return_id=p_return_id
   GROUP BY r.total_base;
  IF invoice_id IS NULL OR invoice_id<>invoice_max THEN RAISE EXCEPTION 'Purchase return must reference one source invoice.'
   USING ERRCODE='check_violation'; END IF;
  SELECT exchange_rate,transaction_currency_code,returned_foreign,
         settled_foreign,total_foreign
   INTO rate,currency_code,current_returned,settled,total_foreign_value
   FROM purchase_invoices WHERE purchase_invoice_id=invoice_id FOR UPDATE;
  IF currency_code=base_code THEN RETURN jsonb_build_object('foreign_return',false); END IF;
  foreign_value:=round(base_value/rate,6);
  IF NOT p_reverse AND settled+current_returned+foreign_value>total_foreign_value THEN
   RAISE EXCEPTION 'Return exceeds the unsettled foreign invoice balance.'
    USING ERRCODE='check_violation';
  END IF;
  PERFORM set_config('financee.purchase_engine','allowed',true);
  UPDATE purchase_invoices SET
   returned_foreign=returned_foreign+CASE WHEN p_reverse THEN -foreign_value ELSE foreign_value END,
   returned_carrying_base=returned_carrying_base+CASE WHEN p_reverse THEN -base_value ELSE base_value END,
   remaining_foreign=remaining_foreign+CASE WHEN p_reverse THEN foreign_value ELSE -foreign_value END
   WHERE purchase_invoice_id=invoice_id;
  PERFORM set_config('financee.purchase_engine','',true);
 ELSIF p_kind='sale_return' THEN
  SELECT min(sl.sale_invoice_id),max(sl.sale_invoice_id),
         r.revenue_total_base
   INTO invoice_id,invoice_max,base_value
   FROM sale_return_invoices r
   JOIN sale_return_lines rl USING(sale_return_id)
   JOIN sale_lines sl ON sl.sale_line_id=rl.source_sale_line_id
   WHERE r.sale_return_id=p_return_id
   GROUP BY r.revenue_total_base;
  IF invoice_id IS NULL OR invoice_id<>invoice_max THEN RAISE EXCEPTION 'Sale return must reference one source invoice.'
   USING ERRCODE='check_violation'; END IF;
  SELECT exchange_rate,transaction_currency_code,returned_foreign,
         settled_foreign,total_foreign
   INTO rate,currency_code,current_returned,settled,total_foreign_value
   FROM sale_invoices WHERE sale_invoice_id=invoice_id FOR UPDATE;
  IF currency_code=base_code THEN RETURN jsonb_build_object('foreign_return',false); END IF;
  foreign_value:=round(base_value/rate,6);
  IF NOT p_reverse AND settled+current_returned+foreign_value>total_foreign_value THEN
   RAISE EXCEPTION 'Return exceeds the unsettled foreign invoice balance.'
    USING ERRCODE='check_violation';
  END IF;
  PERFORM set_config('financee.sale_engine','allowed',true);
  UPDATE sale_invoices SET
   returned_foreign=returned_foreign+CASE WHEN p_reverse THEN -foreign_value ELSE foreign_value END,
   returned_carrying_base=returned_carrying_base+CASE WHEN p_reverse THEN -base_value ELSE base_value END,
   remaining_foreign=remaining_foreign+CASE WHEN p_reverse THEN foreign_value ELSE -foreign_value END
   WHERE sale_invoice_id=invoice_id;
  PERFORM set_config('financee.sale_engine','',true);
 ELSE RAISE EXCEPTION 'Invalid foreign return kind.' USING ERRCODE='check_violation';
 END IF;
 RETURN jsonb_build_object('foreign_return',true,'foreign_return_amount',foreign_value,
  'source_invoice_id',invoice_id,'reversed',p_reverse);
END;
$$;

CREATE OR REPLACE FUNCTION quantity_currency_report(p_from date DEFAULT NULL,p_to date DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
  'realized_gain_base',COALESCE((SELECT sum(realized_gain_base) FROM (
    SELECT pa.realized_gain_base,fp.payment_date d FROM payment_allocations pa JOIN foreign_payments fp USING(payment_id) WHERE fp.status='posted'
    UNION ALL SELECT ra.realized_gain_base,fr.receipt_date FROM receipt_allocations ra JOIN foreign_receipts fr USING(receipt_id) WHERE fr.status='posted') x
    WHERE (p_from IS NULL OR d>=p_from) AND (p_to IS NULL OR d<=p_to)),0),
  'realized_loss_base',COALESCE((SELECT sum(realized_loss_base) FROM (
    SELECT pa.realized_loss_base,fp.payment_date d FROM payment_allocations pa JOIN foreign_payments fp USING(payment_id) WHERE fp.status='posted'
    UNION ALL SELECT ra.realized_loss_base,fr.receipt_date FROM receipt_allocations ra JOIN foreign_receipts fr USING(receipt_id) WHERE fr.status='posted') x
    WHERE (p_from IS NULL OR d>=p_from) AND (p_to IS NULL OR d<=p_to)),0),
  'open_purchase_foreign',COALESCE((SELECT jsonb_agg(jsonb_build_object(
    'purchase_invoice_id',purchase_invoice_id,'document_number',document_number,
    'currency',transaction_currency_code,'remaining_foreign',remaining_foreign,
    'carrying_base',total_base-returned_carrying_base-settled_carrying_base))
    FROM purchase_invoices WHERE status='posted' AND remaining_foreign>0
    AND transaction_currency_code<>(SELECT base_currency_code FROM tenant_schema_metadata WHERE id=true)),'[]'::jsonb),
  'open_sale_foreign',COALESCE((SELECT jsonb_agg(jsonb_build_object(
    'sale_invoice_id',sale_invoice_id,'document_number',document_number,
    'currency',transaction_currency_code,'remaining_foreign',remaining_foreign,
    'carrying_base',total_base-returned_carrying_base-settled_carrying_base))
    FROM sale_invoices WHERE status='posted' AND remaining_foreign>0
    AND transaction_currency_code<>(SELECT base_currency_code FROM tenant_schema_metadata WHERE id=true)),'[]'::jsonb)
 );
$$;

DO $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM document_sequences WHERE document_type='payment') THEN
  INSERT INTO document_sequences(document_type,prefix) VALUES('payment','PAY');
 END IF;
 IF NOT EXISTS(SELECT 1 FROM document_sequences WHERE document_type='receipt') THEN
  INSERT INTO document_sequences(document_type,prefix) VALUES('receipt','REC');
 END IF;
END;
$$;

INSERT INTO quantity_seed_registry(seed_key,seed_version,payload)
VALUES('quantity.currency_settlements',1,
 '{"phase":18,"schema_version":14,"unrealized_revaluation":false}'::jsonb)
ON CONFLICT(seed_key) DO UPDATE SET
 seed_version=GREATEST(quantity_seed_registry.seed_version,EXCLUDED.seed_version),
 payload=EXCLUDED.payload,applied_at=CURRENT_TIMESTAMP;
UPDATE tenant_schema_metadata SET version=GREATEST(version,14),
 applied_at=CURRENT_TIMESTAMP WHERE id=true AND family='quantity';
