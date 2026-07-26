-- Phase 22: quantity reports, reconciliation, exports, and dashboards.
DO $$
BEGIN
 IF to_regclass('tenant_schema_metadata') IS NULL OR NOT EXISTS(
  SELECT 1 FROM tenant_schema_metadata
  WHERE id=true AND family='quantity' AND version>=20
 ) THEN
  RAISE EXCEPTION 'Quantity reports rollout refused: family/version mismatch.';
 END IF;
END $$;

CREATE OR REPLACE FUNCTION quantity_report_filters(p_filters jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE f jsonb:=COALESCE(p_filters,'{}'::jsonb);
BEGIN
 IF jsonb_typeof(f)<>'object' THEN RAISE EXCEPTION 'Report filters must be an object.'; END IF;
 IF f?'from' AND (f->>'from') !~ '^\d{4}-\d{2}-\d{2}$' THEN RAISE EXCEPTION 'Invalid from date.'; END IF;
 IF f?'to' AND (f->>'to') !~ '^\d{4}-\d{2}-\d{2}$' THEN RAISE EXCEPTION 'Invalid to date.'; END IF;
 IF f?'from' AND f?'to' AND (f->>'from')::date>(f->>'to')::date THEN
  RAISE EXCEPTION 'From date cannot be after to date.';
 END IF;
 IF f?'warehouse_id' AND (f->>'warehouse_id') !~ '^\d+$' THEN RAISE EXCEPTION 'Invalid warehouse.'; END IF;
 IF f?'variant_id' AND (f->>'variant_id') !~ '^\d+$' THEN RAISE EXCEPTION 'Invalid variant.'; END IF;
 IF f?'limit' AND ((f->>'limit') !~ '^\d+$' OR (f->>'limit')::int NOT BETWEEN 1 AND 5000)
 THEN RAISE EXCEPTION 'Invalid limit.'; END IF;
 RETURN f;
END $$;

CREATE OR REPLACE FUNCTION quantity_run_report(p_key text,p_filters jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
DECLARE
 f jsonb:=quantity_report_filters(p_filters);
 d1 date:=COALESCE(NULLIF(f->>'from','')::date,'1900-01-01');
 d2 date:=COALESCE(NULLIF(f->>'to','')::date,'9999-12-31');
 wh bigint:=NULLIF(f->>'warehouse_id','')::bigint;
 var bigint:=NULLIF(f->>'variant_id','')::bigint;
 sku_filter text:=NULLIF(f->>'sku','');
 customer_filter text:=NULLIF(f->>'customer','');
 vendor_filter text:=NULLIF(f->>'vendor','');
 tax_filter text:=NULLIF(f->>'tax_code','');
 currency_filter text:=NULLIF(upper(f->>'currency'),'');
 threshold numeric:=COALESCE(NULLIF(f->>'threshold','')::numeric,5);
 age_days int:=COALESCE(NULLIF(f->>'days','')::int,30);
 row_limit int:=COALESCE(NULLIF(f->>'limit','')::int,1000);
 rows jsonb:='[]'::jsonb; cols jsonb:='[]'::jsonb; totals jsonb:='{}'::jsonb;
BEGIN
 IF p_key='trial_balance' THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.account_code),'[]') INTO rows FROM(
   SELECT c.account_code,c.account_name,c.account_type,
    round(COALESCE(sum(l.debit) FILTER(WHERE j.journal_id IS NOT NULL),0),4) debit,
    round(COALESCE(sum(l.credit) FILTER(WHERE j.journal_id IS NOT NULL),0),4) credit,
    round(CASE c.normal_balance WHEN 'Debit' THEN
     COALESCE(sum(l.debit-l.credit) FILTER(WHERE j.journal_id IS NOT NULL),0)
     ELSE COALESCE(sum(l.credit-l.debit) FILTER(WHERE j.journal_id IS NOT NULL),0) END,4) balance
   FROM chart_of_accounts c LEFT JOIN journal_lines l ON l.account_id=c.account_id
   LEFT JOIN journal_entries j ON j.journal_id=l.journal_id AND j.entry_date BETWEEN d1 AND d2
   GROUP BY c.account_id ORDER BY c.account_code)q;
  cols:='[{"key":"account_code","label":"Code"},{"key":"account_name","label":"Account"},{"key":"account_type","label":"Type"},{"key":"debit","label":"Debit"},{"key":"credit","label":"Credit"},{"key":"balance","label":"Balance"}]';
  SELECT jsonb_build_object('debit',COALESCE(sum((x->>'debit')::numeric),0),
   'credit',COALESCE(sum((x->>'credit')::numeric),0)) INTO totals FROM jsonb_array_elements(rows)x;
 ELSIF p_key IN('party_ledger','cash_ledger') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.entry_date,q.journal_id,q.line_id),'[]') INTO rows FROM(
   SELECT j.entry_date,j.journal_id,l.line_id,COALESCE(p.party_name,'') party,
    COALESCE(l.description,j.description) description,l.debit,l.credit,
    sum(l.debit-l.credit) OVER(ORDER BY j.entry_date,j.journal_id,l.line_id) balance
   FROM journal_lines l JOIN journal_entries j USING(journal_id)
   JOIN chart_of_accounts c USING(account_id) LEFT JOIN parties p USING(party_id)
   WHERE j.entry_date BETWEEN d1 AND d2
    AND (p_key<>'cash_ledger' OR c.account_code IN('1000','1100'))
    AND (customer_filter IS NULL OR p.party_name ILIKE '%'||customer_filter||'%')
   ORDER BY j.entry_date,j.journal_id,l.line_id LIMIT row_limit)q;
  cols:='[{"key":"entry_date","label":"Date"},{"key":"journal_id","label":"Journal"},{"key":"party","label":"Party"},{"key":"description","label":"Description"},{"key":"debit","label":"Debit"},{"key":"credit","label":"Credit"},{"key":"balance","label":"Balance"}]';
 ELSIF p_key IN('accounts_receivable','accounts_payable') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.party_name),'[]') INTO rows FROM(
   SELECT p.party_name,p.party_type,
    round(CASE WHEN p_key='accounts_receivable' THEN COALESCE(sum(l.debit-l.credit),0)
      ELSE COALESCE(sum(l.credit-l.debit),0) END,4) balance
   FROM parties p LEFT JOIN journal_lines l ON l.party_id=p.party_id
   LEFT JOIN journal_entries j ON j.journal_id=l.journal_id AND j.entry_date<=d2
   LEFT JOIN chart_of_accounts c ON c.account_id=l.account_id
   WHERE (p_key='accounts_receivable' AND c.account_code='1200')
      OR (p_key='accounts_payable' AND c.account_code='2000')
   GROUP BY p.party_id HAVING CASE WHEN p_key='accounts_receivable'
    THEN COALESCE(sum(l.debit-l.credit),0) ELSE COALESCE(sum(l.credit-l.debit),0) END<>0)q;
  cols:='[{"key":"party_name","label":"Party"},{"key":"party_type","label":"Type"},{"key":"balance","label":"Balance"}]';
 ELSIF p_key IN('monthly_position','monthly_income','expense_report') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.period,q.account_code),'[]') INTO rows FROM(
   SELECT to_char(j.entry_date,'YYYY-MM') period,c.account_code,c.account_name,c.account_type,
    round(sum(l.debit-l.credit),4) debit_less_credit
   FROM journal_entries j JOIN journal_lines l USING(journal_id)
   JOIN chart_of_accounts c USING(account_id)
   WHERE j.entry_date BETWEEN d1 AND d2 AND (
    p_key='monthly_position' OR
    p_key='monthly_income' AND c.account_type IN('Revenue','Expense') OR
    p_key='expense_report' AND c.account_type='Expense')
   GROUP BY 1,c.account_id)q;
  cols:='[{"key":"period","label":"Period"},{"key":"account_code","label":"Code"},{"key":"account_name","label":"Account"},{"key":"account_type","label":"Type"},{"key":"debit_less_credit","label":"Net"}]';
 ELSIF p_key IN('stock_summary','stock_valuation','low_stock','stock_aging',
  'fast_moving','slow_moving','inventory_integrity') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.sku,q.warehouse_code),'[]') INTO rows FROM(
   SELECT v.variant_id,v.sku,p.product_name,w.warehouse_code,w.warehouse_name,
    b.on_hand_quantity,
    COALESCE((SELECT sum(sm.quantity_in-sm.quantity_out) FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
       AND sm.movement_date<d1),0) opening_quantity,
    COALESCE((SELECT sum(sm.quantity_in) FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
       AND sm.movement_date BETWEEN d1 AND d2),0) quantity_in,
    COALESCE((SELECT sum(sm.quantity_out) FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
       AND sm.movement_date BETWEEN d1 AND d2),0) quantity_out,
    COALESCE((SELECT sum(sm.quantity_in-sm.quantity_out) FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
       AND sm.movement_date<=d2),0) closing_quantity,
    round(COALESCE((SELECT sum(fl.remaining_quantity*fl.unit_cost_base)
      FROM fifo_layers fl WHERE fl.variant_id=v.variant_id AND fl.warehouse_id=w.warehouse_id),0),4) stock_value,
    v.reorder_level,
    (SELECT max(sm.movement_date) FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id) last_movement_date,
    COALESCE((SELECT sum(sm.quantity_out) FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
       AND sm.movement_date>=CURRENT_DATE-age_days),0) moved_out
   FROM stock_balances b JOIN product_variants v USING(variant_id)
   JOIN products p USING(product_id) JOIN warehouses w USING(warehouse_id)
   WHERE (wh IS NULL OR w.warehouse_id=wh) AND (var IS NULL OR v.variant_id=var)
    AND (sku_filter IS NULL OR v.sku ILIKE '%'||sku_filter||'%')
    AND (p_key<>'low_stock' OR b.on_hand_quantity<=GREATEST(v.reorder_level,threshold))
    AND (p_key<>'stock_aging' OR NOT EXISTS(SELECT 1 FROM stock_movements sm
      WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
       AND sm.movement_date>CURRENT_DATE-age_days))
    AND (p_key<>'inventory_integrity' OR b.on_hand_quantity<0 OR
      abs(b.on_hand_quantity-COALESCE((SELECT sum(sm.quantity_in-sm.quantity_out)
       FROM stock_movements sm WHERE sm.variant_id=v.variant_id
        AND sm.warehouse_id=w.warehouse_id),0))>0.0005)
   ORDER BY CASE WHEN p_key='fast_moving' THEN -(COALESCE((SELECT sum(sm.quantity_out)
     FROM stock_movements sm WHERE sm.variant_id=v.variant_id AND
     sm.warehouse_id=w.warehouse_id AND sm.movement_date>=CURRENT_DATE-age_days),0))
     ELSE COALESCE((SELECT sum(sm.quantity_out) FROM stock_movements sm
     WHERE sm.variant_id=v.variant_id AND sm.warehouse_id=w.warehouse_id
     AND sm.movement_date>=CURRENT_DATE-age_days),0) END LIMIT row_limit)q;
  cols:='[{"key":"sku","label":"SKU"},{"key":"product_name","label":"Product"},{"key":"warehouse_code","label":"Warehouse"},{"key":"opening_quantity","label":"Opening"},{"key":"quantity_in","label":"In"},{"key":"quantity_out","label":"Out"},{"key":"closing_quantity","label":"Closing"},{"key":"on_hand_quantity","label":"Current On Hand"},{"key":"stock_value","label":"FIFO Value"},{"key":"reorder_level","label":"Reorder Level"},{"key":"last_movement_date","label":"Last Movement"},{"key":"moved_out","label":"Moved Out"}]';
  SELECT jsonb_build_object('quantity',COALESCE(sum((x->>'on_hand_quantity')::numeric),0),
   'value',COALESCE(sum((x->>'stock_value')::numeric),0)) INTO totals FROM jsonb_array_elements(rows)x;
 ELSIF p_key IN('stock_movement','item_history','last_purchase','last_sale') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.movement_date,q.effective_sequence),'[]') INTO rows FROM(
   SELECT sm.movement_date,sm.effective_sequence,v.sku,p.product_name,w.warehouse_code,
    sm.movement_type,sm.document_number,sm.quantity_in,sm.quantity_out,
    sm.unit_cost_base,sm.total_cost_base,sm.description
   FROM stock_movements sm JOIN product_variants v USING(variant_id)
   JOIN products p USING(product_id) JOIN warehouses w USING(warehouse_id)
   WHERE sm.movement_date BETWEEN d1 AND d2 AND (wh IS NULL OR sm.warehouse_id=wh)
    AND (var IS NULL OR sm.variant_id=var)
    AND (sku_filter IS NULL OR v.sku ILIKE '%'||sku_filter||'%')
    AND (p_key<>'last_purchase' OR sm.movement_type='purchase')
    AND (p_key<>'last_sale' OR sm.movement_type='sale')
   ORDER BY sm.movement_date DESC,sm.effective_sequence DESC LIMIT row_limit)q;
  cols:='[{"key":"movement_date","label":"Date"},{"key":"sku","label":"SKU"},{"key":"product_name","label":"Product"},{"key":"warehouse_code","label":"Warehouse"},{"key":"movement_type","label":"Movement"},{"key":"document_number","label":"Document"},{"key":"quantity_in","label":"In"},{"key":"quantity_out","label":"Out"},{"key":"unit_cost_base","label":"Unit Cost"},{"key":"total_cost_base","label":"Value"}]';
 ELSIF p_key IN('inventory_reconciliation','valuation_reconciliation') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.sku,q.warehouse_code),'[]') INTO rows FROM(
   SELECT v.sku,w.warehouse_code,b.on_hand_quantity,
    COALESCE(sum(sm.quantity_in-sm.quantity_out),0) movement_quantity,
    b.on_hand_quantity-COALESCE(sum(sm.quantity_in-sm.quantity_out),0) quantity_variance,
    round(COALESCE((SELECT sum(fl.remaining_quantity*fl.unit_cost_base) FROM fifo_layers fl
     WHERE fl.variant_id=b.variant_id AND fl.warehouse_id=b.warehouse_id),0),4) fifo_value
   FROM stock_balances b JOIN product_variants v USING(variant_id)
   JOIN warehouses w USING(warehouse_id) LEFT JOIN stock_movements sm
    ON sm.variant_id=b.variant_id AND sm.warehouse_id=b.warehouse_id
   WHERE (wh IS NULL OR b.warehouse_id=wh) AND (var IS NULL OR b.variant_id=var)
   GROUP BY b.variant_id,b.warehouse_id,v.sku,w.warehouse_code,b.on_hand_quantity)q;
  cols:='[{"key":"sku","label":"SKU"},{"key":"warehouse_code","label":"Warehouse"},{"key":"on_hand_quantity","label":"Balance Qty"},{"key":"movement_quantity","label":"Movement Qty"},{"key":"quantity_variance","label":"Variance"},{"key":"fifo_value","label":"FIFO Value"}]';
  SELECT jsonb_build_object('quantity_variance',COALESCE(sum((x->>'quantity_variance')::numeric),0),
   'fifo_value',COALESCE(sum((x->>'fifo_value')::numeric),0),
   'inventory_ledger_value',COALESCE((SELECT sum(CASE c.normal_balance WHEN 'Debit'
    THEN l.debit-l.credit ELSE l.credit-l.debit END) FROM journal_lines l
    JOIN chart_of_accounts c USING(account_id) WHERE c.account_code='1400'),0))
   INTO totals FROM jsonb_array_elements(rows)x;
 ELSIF p_key IN('daily_sales','sales_trend') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.sale_date),'[]') INTO rows FROM(
   SELECT s.invoice_date sale_date,count(DISTINCT s.sale_invoice_id)invoice_count,
    round(sum(sl.quantity),3)quantity,round(sum(sl.line_total_base),4)gross,
    round(sum(sl.tax_base),4)tax,round(sum(sl.cogs_base),4)cogs,
    round(sum(sl.line_total_base-sl.tax_base-sl.cogs_base),4)gross_profit
   FROM sale_invoices s JOIN sale_lines sl USING(sale_invoice_id)
   WHERE s.status='posted'AND s.invoice_date BETWEEN d1 AND d2
    AND(customer_filter IS NULL OR s.customer_name ILIKE '%'||customer_filter||'%')
    AND(currency_filter IS NULL OR s.transaction_currency_code=currency_filter)
    AND(var IS NULL OR sl.variant_id=var)AND(tax_filter IS NULL OR sl.tax_code_snapshot=tax_filter)
   GROUP BY s.invoice_date LIMIT row_limit)q;
  cols:='[{"key":"sale_date","label":"Date"},{"key":"invoice_count","label":"Invoices"},{"key":"quantity","label":"Quantity"},{"key":"gross","label":"Gross"},{"key":"tax","label":"Tax"},{"key":"cogs","label":"COGS"},{"key":"gross_profit","label":"Gross Profit"}]';
 ELSIF p_key IN('sales_by_customer','customer_profitability') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.revenue DESC),'[]') INTO rows FROM(
   SELECT s.customer_name,count(DISTINCT s.sale_invoice_id)invoice_count,
    round(sum(sl.quantity),3)quantity,round(sum(sl.line_total_base),4)revenue,
    round(sum(sl.cogs_base),4)cogs,round(sum(sl.line_total_base-sl.cogs_base),4)gross_profit,
    round(CASE WHEN sum(sl.line_total_base)=0 THEN 0 ELSE
     sum(sl.line_total_base-sl.cogs_base)*100/sum(sl.line_total_base)END,2)margin_percent
   FROM sale_invoices s JOIN sale_lines sl USING(sale_invoice_id)
   WHERE s.status='posted'AND s.invoice_date BETWEEN d1 AND d2
    AND(customer_filter IS NULL OR s.customer_name ILIKE '%'||customer_filter||'%')
    AND(currency_filter IS NULL OR s.transaction_currency_code=currency_filter)
   GROUP BY s.customer_name LIMIT row_limit)q;
  cols:='[{"key":"customer_name","label":"Customer"},{"key":"invoice_count","label":"Invoices"},{"key":"quantity","label":"Quantity"},{"key":"revenue","label":"Revenue"},{"key":"cogs","label":"COGS"},{"key":"gross_profit","label":"Gross Profit"},{"key":"margin_percent","label":"Margin %"}]';
 ELSIF p_key IN('sales_summary','invoice_register','sale_wise') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.invoice_date,q.document_number),'[]') INTO rows FROM(
   SELECT s.invoice_date,s.document_number,s.customer_name,s.transaction_currency_code currency,
    round(sum(sl.quantity),3) quantity,s.subtotal_base gross,s.invoice_discount_total_base discount,
    s.tax_total_base tax,s.total_base net,round(sum(sl.cogs_base),4) cogs,
    round(s.total_base-s.tax_total_base-sum(sl.cogs_base),4) gross_profit
   FROM sale_invoices s JOIN sale_lines sl USING(sale_invoice_id)
   WHERE s.status='posted' AND s.invoice_date BETWEEN d1 AND d2
    AND (customer_filter IS NULL OR s.customer_name ILIKE '%'||customer_filter||'%')
    AND (currency_filter IS NULL OR s.transaction_currency_code=currency_filter)
    AND (var IS NULL OR sl.variant_id=var)
    AND (tax_filter IS NULL OR sl.tax_code_snapshot=tax_filter)
   GROUP BY s.sale_invoice_id ORDER BY s.invoice_date,s.document_number LIMIT row_limit)q;
  cols:='[{"key":"invoice_date","label":"Date"},{"key":"document_number","label":"Invoice"},{"key":"customer_name","label":"Customer"},{"key":"currency","label":"Currency"},{"key":"quantity","label":"Quantity"},{"key":"gross","label":"Gross"},{"key":"discount","label":"Discount"},{"key":"tax","label":"Tax"},{"key":"net","label":"Net"},{"key":"cogs","label":"COGS"},{"key":"gross_profit","label":"Gross Profit"}]';
  SELECT jsonb_build_object('net',COALESCE(sum((x->>'net')::numeric),0),
   'cogs',COALESCE(sum((x->>'cogs')::numeric),0),
   'gross_profit',COALESCE(sum((x->>'gross_profit')::numeric),0)) INTO totals
   FROM jsonb_array_elements(rows)x;
 ELSIF p_key IN('product_profitability','sales_by_product','margin_analysis') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.sku),'[]') INTO rows FROM(
   SELECT v.sku,p.product_name,round(sum(sl.quantity),3) quantity,
    round(sum(sl.line_total_base),4) revenue,round(sum(sl.cogs_base),4)cogs,
    round(sum(sl.line_total_base-sl.cogs_base),4)gross_profit,
    round(CASE WHEN sum(sl.line_total_base)=0 THEN 0 ELSE
     sum(sl.line_total_base-sl.cogs_base)*100/sum(sl.line_total_base) END,2) margin_percent
   FROM sale_lines sl JOIN sale_invoices s USING(sale_invoice_id)
   JOIN product_variants v USING(variant_id) JOIN products p USING(product_id)
   WHERE s.status='posted' AND s.invoice_date BETWEEN d1 AND d2
    AND (var IS NULL OR sl.variant_id=var) AND (sku_filter IS NULL OR v.sku ILIKE '%'||sku_filter||'%')
    AND (tax_filter IS NULL OR sl.tax_code_snapshot=tax_filter)
   GROUP BY v.variant_id,p.product_name LIMIT row_limit)q;
  cols:='[{"key":"sku","label":"SKU"},{"key":"product_name","label":"Product"},{"key":"quantity","label":"Quantity"},{"key":"revenue","label":"Revenue"},{"key":"cogs","label":"COGS"},{"key":"gross_profit","label":"Gross Profit"},{"key":"margin_percent","label":"Margin %"}]';
 ELSIF p_key IN('sale_return_analysis','return_rate') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.return_date,q.document_number),'[]') INTO rows FROM(
   SELECT r.return_date,r.document_number,r.customer_name,round(sum(rl.quantity),3)quantity,
    r.revenue_total_base revenue_return,r.cogs_total_base cogs_return,r.tax_reversal_base tax_return
   FROM sale_return_invoices r JOIN sale_return_lines rl USING(sale_return_id)
   WHERE r.status='posted' AND r.return_date BETWEEN d1 AND d2
    AND(customer_filter IS NULL OR r.customer_name ILIKE '%'||customer_filter||'%')
    AND(var IS NULL OR rl.variant_id=var) GROUP BY r.sale_return_id LIMIT row_limit)q;
  cols:='[{"key":"return_date","label":"Date"},{"key":"document_number","label":"Return"},{"key":"customer_name","label":"Customer"},{"key":"quantity","label":"Quantity"},{"key":"revenue_return","label":"Revenue Return"},{"key":"cogs_return","label":"COGS Return"},{"key":"tax_return","label":"Tax Return"}]';
 ELSIF p_key='purchases_by_vendor' THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.net DESC),'[]') INTO rows FROM(
   SELECT i.vendor_name,count(DISTINCT i.purchase_invoice_id)invoice_count,
    round(sum(l.quantity),3)quantity,round(sum(l.line_total_base),4)gross,
    round(sum(l.tax_base),4)tax,round(sum(l.line_total_base+l.tax_base),4)net
   FROM purchase_invoices i JOIN purchase_lines l USING(purchase_invoice_id)
   WHERE i.status='posted'AND i.invoice_date BETWEEN d1 AND d2
    AND(vendor_filter IS NULL OR i.vendor_name ILIKE '%'||vendor_filter||'%')
    AND(currency_filter IS NULL OR i.transaction_currency_code=currency_filter)
   GROUP BY i.vendor_name LIMIT row_limit)q;
  cols:='[{"key":"vendor_name","label":"Vendor"},{"key":"invoice_count","label":"Invoices"},{"key":"quantity","label":"Quantity"},{"key":"gross","label":"Gross"},{"key":"tax","label":"Tax"},{"key":"net","label":"Net"}]';
 ELSIF p_key='purchase_register' THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.invoice_date,q.document_number),'[]') INTO rows FROM(
   SELECT i.invoice_date,i.document_number,i.vendor_name,i.transaction_currency_code currency,
    round(sum(l.quantity),3)quantity,i.subtotal_base gross,i.invoice_discount_total_base discount,
    i.tax_total_base tax,i.total_base net
   FROM purchase_invoices i JOIN purchase_lines l USING(purchase_invoice_id)
   WHERE i.status='posted' AND i.invoice_date BETWEEN d1 AND d2
    AND(vendor_filter IS NULL OR i.vendor_name ILIKE '%'||vendor_filter||'%')
    AND(currency_filter IS NULL OR i.transaction_currency_code=currency_filter)
    AND(var IS NULL OR l.variant_id=var) AND(tax_filter IS NULL OR l.tax_code_snapshot=tax_filter)
   GROUP BY i.purchase_invoice_id LIMIT row_limit)q;
  cols:='[{"key":"invoice_date","label":"Date"},{"key":"document_number","label":"Purchase"},{"key":"vendor_name","label":"Vendor"},{"key":"currency","label":"Currency"},{"key":"quantity","label":"Quantity"},{"key":"gross","label":"Gross"},{"key":"discount","label":"Discount"},{"key":"tax","label":"Tax"},{"key":"net","label":"Net"}]';
 ELSIF p_key IN('purchases_by_product','purchase_price_variance') THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.sku,q.invoice_date),'[]') INTO rows FROM(
   SELECT i.invoice_date,i.document_number,i.vendor_name,v.sku,p.product_name,l.quantity,
    l.unit_cost_base,lag(l.unit_cost_base)OVER(PARTITION BY l.variant_id ORDER BY i.invoice_date,i.purchase_invoice_id) previous_cost,
    l.unit_cost_base-lag(l.unit_cost_base)OVER(PARTITION BY l.variant_id ORDER BY i.invoice_date,i.purchase_invoice_id) cost_variance
   FROM purchase_lines l JOIN purchase_invoices i USING(purchase_invoice_id)
   JOIN product_variants v USING(variant_id)JOIN products p USING(product_id)
   WHERE i.status='posted' AND i.invoice_date BETWEEN d1 AND d2
    AND(vendor_filter IS NULL OR i.vendor_name ILIKE '%'||vendor_filter||'%')
    AND(var IS NULL OR l.variant_id=var)AND(sku_filter IS NULL OR v.sku ILIKE '%'||sku_filter||'%')
   LIMIT row_limit)q;
  cols:='[{"key":"invoice_date","label":"Date"},{"key":"document_number","label":"Purchase"},{"key":"vendor_name","label":"Vendor"},{"key":"sku","label":"SKU"},{"key":"product_name","label":"Product"},{"key":"quantity","label":"Quantity"},{"key":"unit_cost_base","label":"Unit Cost"},{"key":"previous_cost","label":"Previous Cost"},{"key":"cost_variance","label":"Variance"}]';
 ELSIF p_key='purchase_return_analysis' THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.return_date,q.document_number),'[]') INTO rows FROM(
   SELECT r.return_date,r.document_number,r.vendor_name,round(sum(l.quantity),3)quantity,
    r.total_base total,r.tax_reversal_base tax_return FROM purchase_return_invoices r
   JOIN purchase_return_lines l USING(purchase_return_id)
   WHERE r.status='posted'AND r.return_date BETWEEN d1 AND d2
    AND(vendor_filter IS NULL OR r.vendor_name ILIKE '%'||vendor_filter||'%')
   GROUP BY r.purchase_return_id LIMIT row_limit)q;
  cols:='[{"key":"return_date","label":"Date"},{"key":"document_number","label":"Return"},{"key":"vendor_name","label":"Vendor"},{"key":"quantity","label":"Quantity"},{"key":"total","label":"Total"},{"key":"tax_return","label":"Tax Return"}]';
 ELSIF p_key='transfer_report' THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.transfer_date,q.document_number),'[]') INTO rows FROM(
   SELECT t.transfer_date,t.document_number,sw.warehouse_code source_warehouse,
    dw.warehouse_code destination_warehouse,t.status,t.total_quantity,t.total_value_base
   FROM warehouse_transfers t JOIN warehouses sw ON sw.warehouse_id=t.source_warehouse_id
   JOIN warehouses dw ON dw.warehouse_id=t.destination_warehouse_id
   WHERE t.transfer_date BETWEEN d1 AND d2 AND(wh IS NULL OR wh IN(t.source_warehouse_id,t.destination_warehouse_id))
   LIMIT row_limit)q;
  cols:='[{"key":"transfer_date","label":"Date"},{"key":"document_number","label":"Transfer"},{"key":"source_warehouse","label":"From"},{"key":"destination_warehouse","label":"To"},{"key":"status","label":"Status"},{"key":"total_quantity","label":"Quantity"},{"key":"total_value_base","label":"Value"}]';
 ELSIF p_key='count_adjustment' THEN
  SELECT COALESCE(jsonb_agg(to_jsonb(q) ORDER BY q.document_date,q.document_number),'[]') INTO rows FROM(
   SELECT c.count_date document_date,c.document_number,w.warehouse_code,c.status,
    COALESCE(sum(l.counted_quantity-l.system_quantity),0) quantity_variance
   FROM physical_counts c JOIN warehouses w USING(warehouse_id)
   JOIN physical_count_lines l USING(count_id)
   WHERE c.count_date BETWEEN d1 AND d2 AND(wh IS NULL OR c.warehouse_id=wh)
   GROUP BY c.count_id,w.warehouse_code LIMIT row_limit)q;
  cols:='[{"key":"document_date","label":"Date"},{"key":"document_number","label":"Count"},{"key":"warehouse_code","label":"Warehouse"},{"key":"status","label":"Status"},{"key":"quantity_variance","label":"Variance"}]';
 ELSE RAISE EXCEPTION 'Unknown quantity report: %',p_key USING ERRCODE='invalid_parameter_value';
 END IF;
 RETURN jsonb_build_object('columns',cols,'rows',rows,'totals',totals,'filters',f);
END $$;

CREATE OR REPLACE FUNCTION quantity_dashboard(p_key text,p_filters jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
DECLARE r jsonb; f jsonb:=COALESCE(p_filters,'{}'); lim int:=COALESCE(NULLIF(f->>'limit','')::int,10);
BEGIN
 IF p_key='sales_today' THEN
  r:=quantity_run_report('sales_summary',jsonb_build_object('from',CURRENT_DATE,'to',CURRENT_DATE));
  RETURN jsonb_build_object('revenue',COALESCE(r->'totals'->'net','0'),'gross_profit',
   COALESCE(r->'totals'->'gross_profit','0'),'invoice_count',jsonb_array_length(r->'rows'));
 ELSIF p_key='sales_chart' THEN
  r:=quantity_run_report('daily_sales',f); RETURN r->'rows';
 ELSIF p_key='stock_kpi' THEN
  r:=quantity_run_report('stock_summary','{}'); RETURN jsonb_build_object(
   'total_quantity',COALESCE(r->'totals'->'quantity','0'),'stock_value',
   COALESCE(r->'totals'->'value','0'),'variant_warehouses',jsonb_array_length(r->'rows'));
 ELSIF p_key='low_stock' THEN RETURN quantity_run_report('low_stock',f)->'rows';
 ELSIF p_key='fast_moving' THEN RETURN quantity_run_report('fast_moving',f||jsonb_build_object('limit',lim))->'rows';
 ELSIF p_key='stale_stock' THEN RETURN quantity_run_report('stock_aging',f)->'rows';
 ELSIF p_key='top_customers' THEN RETURN quantity_run_report('customer_profitability',f||jsonb_build_object('limit',lim))->'rows';
 ELSIF p_key='top_vendors' THEN RETURN quantity_run_report('purchases_by_vendor',f||jsonb_build_object('limit',lim))->'rows';
 ELSIF p_key='receivables_aging' THEN RETURN quantity_run_report('accounts_receivable',f)->'rows';
 ELSIF p_key='recent_transactions' THEN RETURN quantity_run_report('stock_movement',jsonb_build_object('limit',lim))->'rows';
 ELSIF p_key='expense_kpi' THEN RETURN quantity_run_report('expense_report',f)->'rows';
 ELSIF p_key IN('expense_categories','expense_descriptions') THEN
  RETURN quantity_run_report('expense_report',f||jsonb_build_object('limit',lim))->'rows';
 ELSIF p_key='alerts' THEN
  RETURN jsonb_build_array(
   jsonb_build_object('type','low_stock','count',jsonb_array_length(quantity_run_report('low_stock','{}')->'rows')),
   jsonb_build_object('type','inventory_integrity','count',jsonb_array_length(quantity_run_report('inventory_integrity','{}')->'rows')));
 END IF;
 RAISE EXCEPTION 'Unknown quantity dashboard: %',p_key USING ERRCODE='invalid_parameter_value';
END $$;

INSERT INTO quantity_seed_registry(seed_key,seed_version,payload)
VALUES('quantity.reports_dashboards',22,'{"reports":40,"exports":["csv","excel-compatible"],"dashboard":true}')
ON CONFLICT(seed_key) DO UPDATE SET seed_version=GREATEST(quantity_seed_registry.seed_version,EXCLUDED.seed_version),
 payload=EXCLUDED.payload,applied_at=CURRENT_TIMESTAMP;
UPDATE tenant_schema_metadata SET version=22,applied_at=CURRENT_TIMESTAMP
WHERE id=true AND family='quantity';
