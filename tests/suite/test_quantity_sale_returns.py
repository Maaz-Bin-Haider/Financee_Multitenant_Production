#!/usr/bin/env python3
"""Phase 13 quantity sale returns and exact FIFO-cost restoration."""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,ROOT); os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import Client
from tenancy.models import Company,Currency,Membership,INVENTORY_MODE_QUANTITY
from tenancy.schema_verification import verify_company_schema
from tests.suite.test_quantity_purchases import setup_scope

TAG=f"{time.strftime('%H%M%S')}_{os.getpid()}"; RESULTS=[]
def chk(n,ok,d=""): RESULTS.append((n,bool(ok),str(d)))
def q(s,sql,p=None):
    with connection.cursor() as c:
        c.execute(f"SET search_path TO {connection.ops.quote_name(s)}, public")
        try: c.execute(sql,p or []); return c.fetchall() if c.description else []
        finally: c.execute("SET search_path TO public")
def js(v): return json.loads(v) if isinstance(v,str) else v
def reject(s,sql,p=None):
    try:
        with transaction.atomic(): q(s,sql,p)
        return False
    except DatabaseError: return True
def purchase(s,key,v,w,qty,cost,when):
    return js(q(s,"SELECT quantity_create_purchase(%s::jsonb)",[json.dumps({
      "idempotency_key":key,"invoice_date":when,"vendor_name":"Vendor",
      "purchase_type":"credit","created_by_id":1,"items":[{
       "variant_id":v,"warehouse_id":w,"quantity":str(qty),"unit_cost_base":str(cost)}]})])[0][0])
def sale(s,key,v,w,qty,price,customer="Customer",when="2026-07-10"):
    return js(q(s,"SELECT quantity_create_sale(%s::jsonb)",[json.dumps({
      "idempotency_key":key,"invoice_date":when,"customer_name":customer,
      "sale_type":"credit","created_by_id":1,"items":[{
       "variant_id":v,"warehouse_id":w,"quantity":str(qty),"unit_price_base":str(price)}]})])[0][0])
def ret_payload(key,line,customer="Customer",**extra):
    d={"idempotency_key":key,"return_date":"2026-07-12","customer_name":customer,
       "created_by_id":1,"items":[line]}; d.update(extra); return d
def create_return(s,d): return js(q(s,"SELECT quantity_create_sale_return(%s::jsonb)",[json.dumps(d)])[0][0])
def account(s,code): return q(s,"""SELECT COALESCE(sum(jl.debit-jl.credit),0)
 FROM journal_lines jl JOIN chart_of_accounts c ON c.account_id=jl.account_id
 WHERE c.account_code=%s""",[code])[0][0]
def concurrent(s,d):
    close_old_connections()
    try: return ("ok",create_return(s,d))
    except DatabaseError as e: return ("rejected",str(e))
    finally: close_old_connections()
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
  c1=Company.objects.create(name=f"PH13 {TAG} A",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax")
  c2=Company.objects.create(name=f"PH13 {TAG} B",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax")
  s=c1.schema_name; sb=c2.schema_name
  chk("fresh schema reaches return version",q(s,"SELECT version FROM tenant_schema_metadata")[0][0]==9)
  chk("fresh return schema verifies",verify_company_schema(c1,use_cache=False).ok)
  v,w=setup_scope(s,"RET","PCS")
  purchase(s,"p1",v,w,3,100,"2026-07-01");purchase(s,"p2",v,w,5,120,"2026-07-02")
  sold=sale(s,"s1",v,w,8,200); line=q(s,"SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",[sold["sale_invoice_id"]])[0][0]
  before=(account(s,"1200"),account(s,"4000"),account(s,"5000"),account(s,"1400"))
  r1=create_return(s,ret_payload("r1",{"source_sale_line_id":line,"destination_warehouse_id":w,"quantity":"2"}))
  chk("partial return posts",r1["status"]=="success" and Decimal(str(r1["cogs_total_base"]))==Decimal("200"))
  r2=create_return(s,ret_payload("r2",{"source_sale_line_id":line,"destination_warehouse_id":w,"quantity":"3"}))
  chk("repeated partial crosses exact original FIFO layers",Decimal(str(r2["cogs_total_base"]))==Decimal("340"))
  chk("restorations retain original allocations",q(s,"""SELECT cr.unit_cost_base,cr.quantity FROM sale_return_cost_restorations cr
   JOIN sale_return_lines l USING(sale_return_line_id) WHERE l.sale_return_id=%s ORDER BY restoration_order""",[r2["sale_return_id"]])==[(Decimal("100.000000"),Decimal("1")),(Decimal("120.000000"),Decimal("2"))])
  chk("return accounting reverses revenue AR and COGS",account(s,"1200")==before[0]-Decimal("1000") and account(s,"4000")==before[1]+Decimal("1000") and account(s,"5000")==before[2]-Decimal("540"))
  chk("return restores Inventory exactly",account(s,"1400")==before[3]+Decimal("540"))
  chk("wrong customer rejected",reject(s,"SELECT quantity_create_sale_return(%s::jsonb)",[json.dumps(ret_payload("wrong",{"source_sale_line_id":line,"quantity":"1"},customer="Other"))]))
  chk("excess cumulative return rejected",reject(s,"SELECT quantity_create_sale_return(%s::jsonb)",[json.dumps(ret_payload("too-many",{"source_sale_line_id":line,"quantity":"4"}))]))
  full=create_return(s,ret_payload("full",{"source_sale_line_id":line,"quantity":"3"}))
  remaining_sources=js(q(s,"SELECT quantity_sale_return_sources('Customer')")[0][0])
  chk("full cumulative return accepted",
      Decimal(str(full["cogs_total_base"]))==Decimal("360"),
      (full,remaining_sources))
  chk("fully returned source is no longer eligible",remaining_sources==[],
      remaining_sources)
  chk("source sale edit blocked after return",reject(s,"SELECT quantity_update_sale(%s,%s::jsonb)",[sold["sale_invoice_id"],json.dumps({"invoice_date":"2026-07-10","customer_name":"Customer","sale_type":"credit","created_by_id":1,"items":[{"variant_id":v,"warehouse_id":w,"quantity":"8","unit_price_base":"210"}]})]))
  chk("source sale reversal blocked after return",reject(s,"SELECT quantity_reverse_sale(%s,%s,1)",[sold["sale_invoice_id"],date(2026,7,15)]))
  rv,wv=setup_scope(s,"REVRET","PCS");purchase(s,"pr",rv,wv,2,50,"2026-07-01");sv=sale(s,"sr",rv,wv,2,90)
  lv=q(s,"SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",[sv["sale_invoice_id"]])[0][0]
  rr=create_return(s,ret_payload("rr",{"source_sale_line_id":lv,"quantity":"2"}))
  reversed_doc=js(q(s,"SELECT quantity_reverse_sale_return(%s,%s,1)",[rr["sale_return_id"],date(2026,7,14)])[0][0])
  chk("return reversal removes return effect",reversed_doc["status"]=="success" and q(s,"SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",[rv,wv])[0][0]==0)
  chk("repeat return reversal rejected",reject(s,"SELECT quantity_reverse_sale_return(%s,%s,1)",[rr["sale_return_id"],date(2026,7,15)]))
  consumed=create_return(s,ret_payload("consumed",{"source_sale_line_id":lv,"quantity":"1"}))
  sale(s,"resold",rv,wv,1,95,when="2026-07-13")
  chk("returned stock can be resold",q(s,"SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",[rv,wv])[0][0]==0)
  chk("consumed return cannot be reversed",reject(s,"SELECT quantity_reverse_sale_return(%s,%s,1)",[consumed["sale_return_id"],date(2026,7,16)]))
  cv,cw=setup_scope(s,"CONRET","PCS");purchase(s,"pc",cv,cw,1,40,"2026-07-01");cs=sale(s,"sc",cv,cw,1,80)
  cl=q(s,"SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",[cs["sale_invoice_id"]])[0][0]
  with ThreadPoolExecutor(max_workers=2) as pool:
   outcomes=list(pool.map(lambda d:concurrent(s,d),[ret_payload("ca",{"source_sale_line_id":cl,"quantity":"1"}),ret_payload("cb",{"source_sale_line_id":cl,"quantity":"1"})]))
  chk("concurrent final return permits exactly one",sorted(x[0] for x in outcomes)==["ok","rejected"])
  vb,wb=setup_scope(sb,"ISO","PCS");purchase(sb,"p",vb,wb,1,30,"2026-07-01");ss=sale(sb,"s",vb,wb,1,60)
  lb=q(sb,"SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",[ss["sale_invoice_id"]])[0][0]
  iso=create_return(sb,ret_payload("r1",{"source_sale_line_id":lb,"quantity":"1"}))
  chk("return numbering and keys are tenant isolated",iso["document_number"]=="SR-000001")
  user=get_user_model().objects.create_superuser(username=f"p13_{TAG}",email="p13@example.com",password="pass")
  Membership.objects.create(user=user,company=c2);client=Client(SERVER_NAME="localhost");client.force_login(user)
  page=client.get("/saleReturn/create-sale-return/")
  chk("quantity return page has no serial UI",page.status_code==200 and b"Quantity Sale Returns" in page.content and b"Serial Number" not in page.content)
  chk("return sources HTTP works",client.get("/saleReturn/quantity-sources/").status_code==200)
  chk("return navigation and summary HTTP work",client.get("/saleReturn/get-sale-return/",{"action":"current","current_id":iso["sale_return_id"]}).status_code==200 and client.get("/saleReturn/get-sale-return-summary/").status_code==200)
  chk("serial lookup denied for quantity return",client.get("/saleReturn/lookup/X/").status_code==404)
 finally:
  if user:user.delete()
  drop(c2);drop(c1)
 passed=sum(ok for _,ok,_ in RESULTS)
 for n,ok,d in RESULTS:print(f"{'PASS' if ok else 'FAIL'}: {n}"+(f" — {d}" if d and not ok else ""))
 print(f"\nQuantity sale returns: {passed}/{len(RESULTS)} passed")
 if passed!=len(RESULTS):raise SystemExit(1)
if __name__=="__main__":main()
