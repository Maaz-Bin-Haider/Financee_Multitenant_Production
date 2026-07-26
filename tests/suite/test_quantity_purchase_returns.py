#!/usr/bin/env python3
"""Phase 14 source-eligible, original-cost quantity purchase returns."""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,ROOT);os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.db import DatabaseError,close_old_connections,connection,transaction
from django.test import Client
from tenancy.models import Company,Currency,Membership,INVENTORY_MODE_QUANTITY
from tenancy.schema_verification import verify_company_schema
from tests.suite.test_quantity_purchases import setup_scope
from tests.suite.test_quantity_sale_returns import purchase,sale,account

TAG=f"{time.strftime('%H%M%S')}_{os.getpid()}";R=[]
def chk(n,ok,d=""):R.append((n,bool(ok),str(d)))
def q(s,sql,p=None):
 with connection.cursor() as c:
  c.execute(f"SET search_path TO {connection.ops.quote_name(s)}, public")
  try:c.execute(sql,p or []);return c.fetchall() if c.description else []
  finally:c.execute("SET search_path TO public")
def js(v):return json.loads(v) if isinstance(v,str) else v
def reject(s,sql,p=None):
 try:
  with transaction.atomic():q(s,sql,p)
  return False
 except DatabaseError:return True
def payload(key,line,vendor="Vendor",when="2026-07-12"):
 return {"idempotency_key":key,"return_date":when,"vendor_name":vendor,
  "created_by_id":1,"items":[line]}
def ret(s,d):return js(q(s,"SELECT quantity_create_purchase_return(%s::jsonb)",[json.dumps(d)])[0][0])
def concurrent(s,d):
 close_old_connections()
 try:return("ok",ret(s,d))
 except DatabaseError as e:return("rejected",str(e))
 finally:close_old_connections()
def concurrent_call(fn):
 close_old_connections()
 try:return("ok",fn())
 except DatabaseError as e:return("rejected",str(e))
 finally:close_old_connections()
def drop(c):
 if not c:return
 with connection.cursor() as x:
  x.execute(f"DROP SCHEMA IF EXISTS {connection.ops.quote_name(c.schema_name)} CASCADE")
  x.execute("SET search_path TO public")
 Company.objects.filter(pk=c.pk).delete()

def main():
 c1=c2=user=None
 try:
  cur=Currency.objects.get(pk="PKR")
  c1=Company.objects.create(name=f"PH14 {TAG} A",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax")
  c2=Company.objects.create(name=f"PH14 {TAG} B",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax")
  s=c1.schema_name;sb=c2.schema_name
  chk("fresh schema includes purchase-return version",q(s,"SELECT version FROM tenant_schema_metadata")[0][0]>=10)
  chk("fresh purchase-return schema verifies",verify_company_schema(c1,use_cache=False).ok)
  v,w=setup_scope(s,"PRET","PCS");p=purchase(s,"p1",v,w,5,100,"2026-07-01")
  line=q(s,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[p["purchase_invoice_id"]])[0][0]
  before=(account(s,"2000"),account(s,"1400"))
  r1=ret(s,payload("r1",{"source_purchase_line_id":line,"quantity":"2"}))
  chk("partial return posts at original cost",Decimal(str(r1["total_base"]))==Decimal("200"))
  chk("credit return debits AP and credits Inventory",account(s,"2000")==before[0]+Decimal("200") and account(s,"1400")==before[1]-Decimal("200"))
  cash_v,cash_w=setup_scope(s,"CASHPR","PCS")
  cash_purchase=js(q(s,"SELECT quantity_create_purchase(%s::jsonb)",[json.dumps({
   "idempotency_key":"cash-purchase","invoice_date":"2026-07-01",
   "vendor_name":"Cash Vendor","purchase_type":"cash","payment_account_code":"1000",
   "created_by_id":1,"items":[{"variant_id":cash_v,"warehouse_id":cash_w,
   "quantity":"1","unit_cost_base":"55"}]})])[0][0])
  cash_line=q(s,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[cash_purchase["purchase_invoice_id"]])[0][0]
  cash_before=account(s,"1000")
  ret(s,payload("cash-return",{"source_purchase_line_id":cash_line,"quantity":"1"},vendor="Cash Vendor"))
  chk("cash return restores original Cash account",account(s,"1000")==cash_before+Decimal("55"))
  r2=ret(s,payload("r2",{"source_purchase_line_id":line,"quantity":"3"}))
  chk("repeated partial can complete source",Decimal(str(r2["total_base"]))==Decimal("300"))
  chk("double return rejected",reject(s,"SELECT quantity_create_purchase_return(%s::jsonb)",[json.dumps(payload("excess",{"source_purchase_line_id":line,"quantity":"1"}))]))
  chk("wrong vendor rejected",reject(s,"SELECT quantity_create_purchase_return(%s::jsonb)",[json.dumps(payload("wrong",{"source_purchase_line_id":line,"quantity":"1"},vendor="Other"))]))
  chk("backdated before purchase rejected",reject(s,"SELECT quantity_create_purchase_return(%s::jsonb)",[json.dumps(payload("back",{"source_purchase_line_id":line,"quantity":"1"},when="2026-06-30"))]))
  rv,rw=setup_scope(s,"SOLD","PCS");pp=purchase(s,"p2",rv,rw,3,70,"2026-07-01")
  pl=q(s,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[pp["purchase_invoice_id"]])[0][0]
  sale(s,"sold",rv,rw,2,120)
  chk("sold source quantity cannot be returned",reject(s,"SELECT quantity_create_purchase_return(%s::jsonb)",[json.dumps(payload("sold-ret",{"source_purchase_line_id":pl,"quantity":"2"}))]))
  rr=ret(s,payload("one",{"source_purchase_line_id":pl,"quantity":"1"}))
  chk("remaining eligible source can be returned",Decimal(str(rr["total_base"]))==Decimal("70"))
  reversed_doc=js(q(s,"SELECT quantity_reverse_purchase_return(%s,%s,1)",[rr["purchase_return_id"],date(2026,7,14)])[0][0])
  chk("return reversal restores stock",reversed_doc["status"]=="success" and q(s,"SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",[rv,rw])[0][0]==1)
  chk("repeat reversal rejected",reject(s,"SELECT quantity_reverse_purchase_return(%s,%s,1)",[rr["purchase_return_id"],date(2026,7,15)]))
  replacement=js(q(s,"SELECT quantity_update_purchase_return(%s,%s::jsonb)",[ret(s,payload("edit-source",{"source_purchase_line_id":pl,"quantity":"1"},when="2026-07-15"))["purchase_return_id"],json.dumps(payload("edit-replacement",{"source_purchase_line_id":pl,"quantity":"1"},when="2026-07-16"))])[0][0])
  chk("guarded update reverses and replaces",replacement.get("replaced_purchase_return_id") is not None)
  cv,cw=setup_scope(s,"CONPR","PCS");cp=purchase(s,"pc",cv,cw,1,40,"2026-07-01")
  cl=q(s,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[cp["purchase_invoice_id"]])[0][0]
  with ThreadPoolExecutor(max_workers=2) as pool:
   outcomes=list(pool.map(lambda d:concurrent(s,d),[payload("ca",{"source_purchase_line_id":cl,"quantity":"1"}),payload("cb",{"source_purchase_line_id":cl,"quantity":"1"})]))
  chk("concurrent final return permits exactly one",sorted(x[0] for x in outcomes)==["ok","rejected"],outcomes)
  sv,sw=setup_scope(s,"RACESALE","PCS");sp=purchase(s,"race-p",sv,sw,1,45,"2026-07-01")
  sl=q(s,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[sp["purchase_invoice_id"]])[0][0]
  with ThreadPoolExecutor(max_workers=2) as pool:
   race=list(pool.map(concurrent_call,[
    lambda:ret(s,payload("race-return",{"source_purchase_line_id":sl,"quantity":"1"})),
    lambda:sale(s,"race-sale",sv,sw,1,80)
   ]))
  chk("concurrent purchase return and sale permit one consumer",sorted(x[0] for x in race)==["ok","rejected"],race)
  bv,bw=setup_scope(sb,"ISO","PCS");bp=purchase(sb,"p",bv,bw,1,30,"2026-07-01")
  bl=q(sb,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[bp["purchase_invoice_id"]])[0][0]
  iso=ret(sb,payload("r",{"source_purchase_line_id":bl,"quantity":"1"}))
  chk("tenant numbering is isolated",iso["document_number"]=="PR-000001")
  c2.refresh_from_db()
  chk("HTTP tenant is provisioned",c2.provisioning_state=="ready",c2.provisioning_state)
  user=get_user_model().objects.create_superuser(username=f"p14_{TAG}",email="p14@example.com",password="pass")
  Membership.objects.create(user=user,company=c2);client=Client(SERVER_NAME="localhost");client.force_login(user)
  page=client.get("/purchaseReturn/create-purchase-return/")
  chk("quantity page has no serial UI",page.status_code==200 and b"Quantity Purchase Returns" in page.content and b"Serial Number" not in page.content,(page.status_code,getattr(page,"content",b"")[:120]))
  source_response=client.get("/purchaseReturn/quantity-sources/")
  chk("sources HTTP works",source_response.status_code==200,(source_response.status_code,source_response.content[:200]))
  nav=client.get("/purchaseReturn/get-purchase-return/",{"action":"current","current_id":iso["purchase_return_id"]});summ=client.get("/purchaseReturn/get-purchase-return-summary/")
  chk("navigation and summary HTTP work",nav.status_code==200 and summ.status_code==200,(nav.status_code,nav.content[:120],summ.status_code,summ.content[:120]))
  lookup=client.get("/purchaseReturn/lookup/X/")
  chk("serial lookup denied",lookup.status_code==404,(lookup.status_code,lookup.content[:120]))
 finally:
  if user:user.delete()
  drop(c2);drop(c1)
 passed=sum(ok for _,ok,_ in R)
 for n,ok,d in R:print(f"{'PASS' if ok else 'FAIL'}: {n}"+(f" — {d}" if d and not ok else ""))
 print(f"\nQuantity purchase returns: {passed}/{len(R)} passed")
 if passed!=len(R):raise SystemExit(1)
if __name__=="__main__":main()
