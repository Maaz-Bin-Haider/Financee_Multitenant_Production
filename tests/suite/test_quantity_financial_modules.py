#!/usr/bin/env python3
"""Phase 19 shared financial modules and universal close guards."""
import json,os,sys,time
from decimal import Decimal
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,ROOT);os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django;django.setup()
from django.contrib.auth import get_user_model
from django.db import DatabaseError,connection,transaction
from django.test import Client
from tenancy.models import Company,Currency,Membership,INVENTORY_MODE_QUANTITY
from tenancy.schema_verification import verify_company_schema
from tests.suite.test_quantity_purchases import setup_scope
from tests.suite.test_quantity_sales import purchase
TAG=f"{time.strftime('%H%M%S')}_{os.getpid()}";R=[]
def chk(n,o):R.append((n,bool(o)))
def js(v):return json.loads(v) if isinstance(v,str) else v
def q(s,sql,p=None):
 with connection.cursor() as c:
  c.execute(f"SET search_path TO {connection.ops.quote_name(s)}, public")
  try:c.execute(sql,p or []);return c.fetchall() if c.description else []
  finally:c.execute("SET search_path TO public")
def reject(s,sql,p=None):
 try:
  with transaction.atomic():q(s,sql,p)
  return False
 except DatabaseError:return True
def call(s,fn,data):return js(q(s,f"SELECT {fn}(%s::jsonb)",[json.dumps(data)])[0][0])
def sale(s,key,v,w,qty,price,when):
 return call(s,"quantity_create_sale",{"idempotency_key":key,"invoice_date":when,
  "customer_name":"Phase 12 Customer","sale_type":"credit","created_by_id":1,
  "items":[{"variant_id":v,"warehouse_id":w,"quantity":str(qty),"unit_price_base":str(price)}]})
def bal(s,code):return q(s,"SELECT COALESCE(sum(debit-credit),0) FROM journal_lines l JOIN chart_of_accounts c USING(account_id) WHERE account_code=%s",[code])[0][0]
def pbal(s,name):return Decimal(str(js(q(s,"SELECT get_party_balance_by_name(%s)",[name])[0][0])["balance"]))
def drop(c):
 if not c:return
 with connection.cursor() as x:x.execute(f"DROP SCHEMA IF EXISTS {connection.ops.quote_name(c.schema_name)} CASCADE");x.execute("SET search_path TO public")
 Company.objects.filter(pk=c.pk).delete()
def main():
 c=user=None
 try:
  c=Company.objects.create(name=f"PH19 {TAG}",inventory_mode=INVENTORY_MODE_QUANTITY,
   base_currency=Currency.objects.get(pk="PKR"),tax_environment="non_tax");s=c.schema_name
  chk("fresh schema reaches financial version",q(s,"SELECT version FROM tenant_schema_metadata")[0][0]==15)
  chk("financial schema verifies",verify_company_schema(c,use_cache=False).ok)
  call(s,"add_party_from_json",{"party_name":"CUSTOMER","party_type":"Customer","opening_balance":"1000","balance_type":"Debit","created_by_id":1})
  call(s,"add_party_from_json",{"party_name":"VENDOR","party_type":"Vendor","opening_balance":"800","balance_type":"Credit","created_by_id":1})
  call(s,"add_party_from_json",{"party_name":"BOTH","party_type":"Both","created_by_id":1})
  call(s,"add_party_from_json",{"party_name":"EXPENSE","party_type":"Expense","created_by_id":1})
  chk("party types and expense account integrate",q(s,"SELECT count(*) FROM parties")[0][0]==4 and q(s,"SELECT count(*) FROM chart_of_accounts WHERE account_name='EXPENSE' AND account_type='Expense'")[0][0]==1)
  chk("opening party balances reconcile",pbal(s,"CUSTOMER")==1000 and pbal(s,"VENDOR")==-800)
  pay=call(s,"make_payment",{"party_name":"VENDOR","amount":"300","method":"Cash","payment_date":"2026-06-20","created_by_id":1})
  rec=call(s,"make_receipt",{"party_name":"CUSTOMER","amount":"400","method":"Bank","receipt_date":"2026-06-20","created_by_id":1})
  con=call(s,"make_contra",{"from_party_name":"CUSTOMER","to_party_name":"BOTH","amount":"50","contra_date":"2026-06-20","created_by_id":1})
  chk("payment receipt contra post and reconcile",pay["status"]=="success" and rec["status"]=="success" and con["status"]=="success" and pbal(s,"VENDOR")==-500 and pbal(s,"CUSTOMER")==550 and pbal(s,"BOTH")==50)
  chk("cash and bank paths reconcile",bal(s,"1000")==Decimal("-300") and bal(s,"1100")==Decimal("400"))
  call(s,"set_opening_cash_from_json",{"amount":"5000","created_by_id":1})
  eq=call(s,"add_owner_equity_txn",{"direction":"injection","amount":"2000","txn_date":"2026-06-21","created_by_id":1})
  wd=call(s,"add_owner_equity_txn",{"direction":"withdrawal","amount":"500","txn_date":"2026-06-22","created_by_id":1})
  chk("opening cash and owner equity reconcile",eq["status"]=="success" and wd["status"]=="success" and bal(s,"1000")==Decimal("6200"))
  chk("financial navigation and listings work",js(q(s,"SELECT get_payment_details(%s)",[pay["payment_id"]])[0][0])["party_name"]=="VENDOR" and isinstance(js(q(s,"SELECT get_owner_equity_json(20)")[0][0])["transactions"],list))
  v,w=setup_scope(s,"CLOSE","PCS");purchase(s,"base-p",v,w,10,100,"2026-06-01")
  sold=sale(s,"base-s",v,w,2,150,when="2026-06-02")
  pl=q(s,"SELECT purchase_line_id FROM purchase_lines ORDER BY purchase_line_id LIMIT 1")[0][0]
  sl=q(s,"SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",[sold["sale_invoice_id"]])[0][0]
  w2=js(q(s,"SELECT quantity_create_warehouse(%s::jsonb)",[json.dumps({"warehouse_code":"DST","warehouse_name":"Destination","user_id":1})])[0][0])
  cnt=js(q(s,"SELECT quantity_create_physical_count(%s::jsonb)",[json.dumps({"idempotency_key":"preclose-count","count_date":"2026-07-10","cutoff_date":"2026-07-10","warehouse_id":w,"created_by_id":1,"items":[{"variant_id":v,"counted_quantity":"8","reason":"Close test"}]})])[0][0])
  preview=js(q(s,"SELECT preview_period_close(2026,7)")[0][0]);closed=call(s,"close_period_from_json",{"year":2026,"month":7,"created_by_id":1})
  chk("month preview and close work",preview["is_closed"] is False and closed["status"]=="success")
  probes=[
   ("purchase", "SELECT quantity_create_purchase(%s::jsonb)",[json.dumps({"idempotency_key":"closed-p","invoice_date":"2026-07-20","vendor_name":"V","purchase_type":"credit","created_by_id":1,"items":[{"variant_id":v,"warehouse_id":w,"quantity":"1","unit_cost_base":"1"}]})]),
   ("sale","SELECT quantity_create_sale(%s::jsonb)",[json.dumps({"idempotency_key":"closed-s","invoice_date":"2026-07-20","customer_name":"C","sale_type":"credit","created_by_id":1,"items":[{"variant_id":v,"warehouse_id":w,"quantity":"1","unit_price_base":"1"}]})]),
   ("purchase return","SELECT quantity_create_purchase_return(%s::jsonb)",[json.dumps({"idempotency_key":"closed-pr","return_date":"2026-07-20","vendor_name":"Phase 12 Vendor","created_by_id":1,"items":[{"source_purchase_line_id":pl,"quantity":"1"}]})]),
   ("sale return","SELECT quantity_create_sale_return(%s::jsonb)",[json.dumps({"idempotency_key":"closed-sr","return_date":"2026-07-20","customer_name":"Phase 12 Customer","created_by_id":1,"items":[{"source_sale_line_id":sl,"destination_warehouse_id":w,"quantity":"1"}]})]),
   ("transfer","SELECT quantity_create_transfer(%s::jsonb)",[json.dumps({"idempotency_key":"closed-t","transfer_date":"2026-07-20","source_warehouse_id":w,"destination_warehouse_id":w2,"created_by_id":1,"items":[{"variant_id":v,"quantity":"1"}]})]),
   ("count","SELECT quantity_create_physical_count(%s::jsonb)",[json.dumps({"idempotency_key":"closed-count","count_date":"2026-07-20","cutoff_date":"2026-07-20","warehouse_id":w,"created_by_id":1,"items":[{"variant_id":v,"counted_quantity":"8","reason":"Closed"}]})]),
   ("adjustment approval","SELECT quantity_approve_physical_count(%s,1)",[cnt["count_id"]]),
   ("payment","SELECT make_payment(%s::jsonb)",[json.dumps({"party_name":"VENDOR","amount":"1","payment_date":"2026-07-20"})]),
   ("receipt","SELECT make_receipt(%s::jsonb)",[json.dumps({"party_name":"CUSTOMER","amount":"1","receipt_date":"2026-07-20"})]),
   ("contra","SELECT make_contra(%s::jsonb)",[json.dumps({"from_party_name":"CUSTOMER","to_party_name":"BOTH","amount":"1","contra_date":"2026-07-20"})]),
   ("opening stock","SELECT quantity_create_opening_stock(%s::jsonb)",[json.dumps({"as_of_date":"2026-07-20","created_by_id":1,"items":[{"variant_id":v,"warehouse_id":w2,"quantity":"1","unit_cost_base":"1"}]})]),
   ("opening cash","SELECT set_opening_cash_from_json(%s::jsonb)",[json.dumps({"amount":"5100","created_by_id":1})]),
   ("owner equity","SELECT add_owner_equity_txn(%s::jsonb)",[json.dumps({"direction":"injection","amount":"1","txn_date":"2026-07-20"})]),
   ("edit","SELECT quantity_update_sale(%s,%s::jsonb)",[sold["sale_invoice_id"],json.dumps({"invoice_date":"2026-07-20","customer_name":"Phase 12 Customer","sale_type":"credit","created_by_id":1,"items":[{"variant_id":v,"warehouse_id":w,"quantity":"2","unit_price_base":"150"}]})]),
   ("delete","SELECT quantity_reverse_sale(%s,%s,1)",[sold["sale_invoice_id"],"2026-07-20"]),
  ]
  for name,sql,args in probes:chk(f"closed period blocks {name}",reject(s,sql,args))
  chk("closed-period failures leave trial balance balanced",q(s,"SELECT sum(debit)-sum(credit) FROM journal_lines")[0][0]==0)
  reopened=js(q(s,"SELECT reverse_period_close(2026,7)")[0][0]);chk("period reversal reopens mutations",reopened["status"]=="success" and call(s,"make_receipt",{"party_name":"CUSTOMER","amount":"1","receipt_date":"2026-07-20"})["status"]=="success")
  user=get_user_model().objects.create_superuser(username=f"p19_{TAG}",email="p19@example.com",password="pass")
  Membership.objects.create(user=user,company=c);client=Client(SERVER_NAME="localhost");client.force_login(user)
  pages=["/parties/parties-dash/","/payments/payment/","/receipts/receipt/","/contra/contra/","/set-opening/","/owner-equity/","/month-close/"]
  chk("shared financial UI is enabled for quantity company",all(client.get(x).status_code==200 for x in pages))
 finally:
  if user:user.delete()
  drop(c)
 passed=sum(x[1] for x in R)
 for n,o in R:print(f"{'PASS' if o else 'FAIL'}: {n}")
 print(f"\nQuantity financial modules: {passed}/{len(R)} passed")
 if passed!=len(R):raise SystemExit(1)
if __name__=="__main__":main()
