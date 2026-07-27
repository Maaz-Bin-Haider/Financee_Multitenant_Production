#!/usr/bin/env python3
"""Phase 16 reproducible physical counts and FIFO-valued adjustments."""
import json,os,sys,time
from datetime import date
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
from tests.suite.test_quantity_sale_returns import purchase,sale,account
TAG=f"{time.strftime('%H%M%S')}_{os.getpid()}";R=[]
def chk(n,o,d=""):R.append((n,bool(o),str(d)))
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
def payload(key,w,items,when="2026-07-10",cutoff=None):
 return {"idempotency_key":key,"count_date":when,"cutoff_date":cutoff or when,
  "warehouse_id":w,"created_by_id":1,"items":items}
def create(s,d):return js(q(s,"SELECT quantity_create_physical_count(%s::jsonb)",[json.dumps(d)])[0][0])
def approve(s,i):return js(q(s,"SELECT quantity_approve_physical_count(%s,1)",[i])[0][0])
def stock(s,v,w):return q(s,"SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",[v,w])[0][0]
def drop(c):
 if not c:return
 with connection.cursor() as x:x.execute(f"DROP SCHEMA IF EXISTS {connection.ops.quote_name(c.schema_name)} CASCADE");x.execute("SET search_path TO public")
 Company.objects.filter(pk=c.pk).delete()
def main():
 c1=c2=admin=viewer=None
 try:
  cur=Currency.objects.get(pk="PKR");c1=Company.objects.create(name=f"PH16 {TAG} A",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax");c2=Company.objects.create(name=f"PH16 {TAG} B",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax")
  s=c1.schema_name;sb=c2.schema_name;chk("fresh schema includes count version",q(s,"SELECT version FROM tenant_schema_metadata")[0][0]>=12);chk("schema verifies",verify_company_schema(c1,use_cache=False).ok)
  v,w=setup_scope(s,"COUNT","PCS");purchase(s,"p",v,w,5,100,"2026-07-01")
  exact=create(s,payload("exact",w,[{"variant_id":v,"counted_quantity":"5","reason":"Cycle count"}]));ep=approve(s,exact["count_id"])
  chk("exact count posts no movement or journal",ep["journal_id"] is None and stock(s,v,w)==5)
  before=(account(s,"1400"),account(s,"5900"));short=create(s,payload("short",w,[{"variant_id":v,"counted_quantity":"3","reason":"Damage"}]));sp=approve(s,short["count_id"])
  chk("shortage consumes FIFO",Decimal(str(sp["loss_total_base"]))==Decimal("200") and stock(s,v,w)==3)
  chk("shortage debits loss and credits Inventory",account(s,"5900")==before[1]+Decimal("200") and account(s,"1400")==before[0]-Decimal("200"))
  sv,sw=setup_scope(s,"SURPLUS","PCS");gain_before=(account(s,"1400"),account(s,"4900"));sur=create(s,payload("sur",sw,[{"variant_id":sv,"counted_quantity":"2","positive_unit_cost_base":"30","reason":"Found stock"}]));gp=approve(s,sur["count_id"])
  chk("surplus creates entered-cost FIFO layer",Decimal(str(gp["gain_total_base"]))==Decimal("60") and stock(s,sv,sw)==2)
  chk("surplus debits Inventory and credits gain",account(s,"1400")==gain_before[0]+Decimal("60") and account(s,"4900")==gain_before[1]-Decimal("60"))
  chk("repeated posting rejected",reject(s,"SELECT quantity_approve_physical_count(%s,1)",[sur["count_id"]]))
  rev=js(q(s,"SELECT quantity_reverse_physical_count(%s,CURRENT_DATE,1)",[sur["count_id"]])[0][0]);chk("untouched surplus reversal restores stock and accounting",rev["status"]=="success" and stock(s,sv,sw)==0 and account(s,"1400")==gain_before[0] and account(s,"4900")==gain_before[1])
  chk("repeat reversal rejected",reject(s,"SELECT quantity_reverse_physical_count(%s,CURRENT_DATE,1)",[sur["count_id"]]))
  chk("negative counted quantity rejected",reject(s,"SELECT quantity_create_physical_count(%s::jsonb)",[json.dumps(payload("neg",w,[{"variant_id":v,"counted_quantity":"-1","reason":"Bad"}]))]))
  nv,nw=setup_scope(s,"NOCOST","PCS")
  today=str(date.today())
  chk("surplus without valuation rejected",reject(s,"SELECT quantity_create_physical_count(%s::jsonb)",[json.dumps(payload("nocost",nw,[{"variant_id":nv,"counted_quantity":"1","reason":"Found"}],when=today))]))
  cv,cw=setup_scope(s,"CUTOFF","PCS");purchase(s,"cp",cv,cw,5,40,"2026-07-01");snap=create(s,payload("snap",cw,[{"variant_id":cv,"counted_quantity":"5","reason":"Cutoff"}],cutoff="2026-07-09"));sale(s,"after-cutoff",cv,cw,1,80,when="2026-07-10");approve(s,snap["count_id"])
  chk("movement after cutoff is preserved",stock(s,cv,cw)==4)
  bv,bw=setup_scope(sb,"ISO","PCS");purchase(sb,"bp",bv,bw,1,20,"2026-07-01");iso=create(sb,payload("iso",bw,[{"variant_id":bv,"counted_quantity":"1","reason":"Count"}]));chk("count numbering is tenant isolated",iso["document_number"]=="CNT-000001")
  c2.refresh_from_db();admin=get_user_model().objects.create_superuser(username=f"p16_{TAG}",email="p16@example.com",password="pass");Membership.objects.create(user=admin,company=c2);client=Client(SERVER_NAME="localhost");client.force_login(admin)
  page=client.get("/physical-counts/");chk("quantity count page works",page.status_code==200 and b"Physical Counts" in page.content)
  chk("count navigation and summary work",client.get("/physical-counts/navigate/",{"action":"current","current_id":iso["count_id"]}).status_code==200 and client.get("/physical-counts/summary/").status_code==200)
  viewer=get_user_model().objects.create_user(username=f"p16v_{TAG}",password="pass");Membership.objects.create(user=viewer,company=c1);vc=Client(SERVER_NAME="localhost");vc.force_login(viewer)
  chk("unapproved user cannot access protected count route",vc.get("/physical-counts/").status_code in(302,403))
 finally:
  if viewer:viewer.delete()
  if admin:admin.delete()
  drop(c2);drop(c1)
 passed=sum(o for _,o,_ in R)
 for n,o,d in R:print(f"{'PASS' if o else 'FAIL'}: {n}"+(f" — {d}" if d and not o else ""))
 print(f"\nQuantity counts/adjustments: {passed}/{len(R)} passed")
 if passed!=len(R):raise SystemExit(1)
if __name__=="__main__":main()
