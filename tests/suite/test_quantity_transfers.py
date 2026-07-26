#!/usr/bin/env python3
"""Phase 15 atomic FIFO-preserving warehouse transfers."""
import json,os,sys,time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,ROOT);os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django;django.setup()
from django.contrib.auth import get_user_model
from django.db import DatabaseError,close_old_connections,connection,transaction
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
def wh(s,code):
 return q(s,"SELECT quantity_create_warehouse(%s::jsonb)",[json.dumps({"warehouse_code":code,"warehouse_name":code,"user_id":1})])[0][0]
def payload(key,src,dst,items,when="2026-07-10"):
 return {"idempotency_key":key,"transfer_date":when,"source_warehouse_id":src,
  "destination_warehouse_id":dst,"created_by_id":1,"items":items}
def transfer(s,d):return js(q(s,"SELECT quantity_create_transfer(%s::jsonb)",[json.dumps(d)])[0][0])
def call(fn):
 close_old_connections()
 try:return("ok",fn())
 except DatabaseError as e:return("rejected",str(e))
 finally:close_old_connections()
def stock(s,v,w):return q(s,"SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",[v,w])[0][0]
def fifo(s,v,w):return q(s,"SELECT COALESCE(sum(remaining_quantity*unit_cost_base),0) FROM fifo_layers WHERE variant_id=%s AND warehouse_id=%s",[v,w])[0][0]
def drop(c):
 if not c:return
 with connection.cursor() as x:x.execute(f"DROP SCHEMA IF EXISTS {connection.ops.quote_name(c.schema_name)} CASCADE");x.execute("SET search_path TO public")
 Company.objects.filter(pk=c.pk).delete()
def main():
 c1=c2=user=None
 try:
  cur=Currency.objects.get(pk="PKR");c1=Company.objects.create(name=f"PH15 {TAG} A",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax");c2=Company.objects.create(name=f"PH15 {TAG} B",inventory_mode=INVENTORY_MODE_QUANTITY,base_currency=cur,tax_environment="non_tax")
  s=c1.schema_name;sb=c2.schema_name;chk("fresh schema includes transfer version",q(s,"SELECT version FROM tenant_schema_metadata")[0][0]>=11);chk("schema verifies",verify_company_schema(c1,use_cache=False).ok)
  v,w1=setup_scope(s,"TRF","PCS");w2=wh(s,"DEST");purchase(s,"p1",v,w1,2,100,"2026-07-01");purchase(s,"p2",v,w1,3,120,"2026-07-02")
  gl=(account(s,"1000"),account(s,"1200"),account(s,"2000"),account(s,"4000"),account(s,"5000"),account(s,"1400"));value=fifo(s,v,w1)+fifo(s,v,w2)
  t=transfer(s,payload("t1",w1,w2,[{"variant_id":v,"quantity":"4"}]))
  chk("multi-layer transfer posts",Decimal(str(t["total_value_base"]))==Decimal("440"));chk("source and destination quantities reconcile",stock(s,v,w1)==1 and stock(s,v,w2)==4)
  chk("company FIFO value is unchanged",fifo(s,v,w1)+fifo(s,v,w2)==value);chk("transfer creates no accounting effect",gl==(account(s,"1000"),account(s,"1200"),account(s,"2000"),account(s,"4000"),account(s,"5000"),account(s,"1400")))
  chk("destination retains cost segments",q(s,"SELECT quantity,unit_cost_base FROM warehouse_transfer_cost_segments ORDER BY segment_order")==[(Decimal("2"),Decimal("100.000000")),(Decimal("2"),Decimal("120.000000"))])
  chk("same warehouse rejected",reject(s,"SELECT quantity_create_transfer(%s::jsonb)",[json.dumps(payload("same",w1,w1,[{"variant_id":v,"quantity":"1"}]))]));chk("unavailable quantity rejected",reject(s,"SELECT quantity_create_transfer(%s::jsonb)",[json.dumps(payload("excess",w1,w2,[{"variant_id":v,"quantity":"2"}]))]));chk("backdated negative transfer rejected",reject(s,"SELECT quantity_create_transfer(%s::jsonb)",[json.dumps(payload("back",w1,w2,[{"variant_id":v,"quantity":"1"}],when="2026-06-30"))]))
  rev=js(q(s,"SELECT quantity_reverse_transfer(%s,CURRENT_DATE,1)",[t["transfer_id"]])[0][0]);chk("guarded reversal restores both warehouses",rev["status"]=="success" and stock(s,v,w1)==5 and stock(s,v,w2)==0);chk("repeat reversal rejected",reject(s,"SELECT quantity_reverse_transfer(%s,CURRENT_DATE,1)",[t["transfer_id"]]))
  v2,_unused=setup_scope(s,"TRF2","PCS");purchase(s,"p3",v2,w1,2,30,"2026-07-03")
  multi=transfer(s,payload("multi",w1,w2,[{"variant_id":v,"quantity":"1"},{"variant_id":v2,"quantity":"2"}],when="2026-07-15"))
  chk("multi-SKU transfer is atomic",multi["status"]=="success" and stock(s,v,w2)==1 and stock(s,v2,w2)==2)
  updated=js(q(s,"SELECT quantity_update_transfer(%s,%s::jsonb)",[multi["transfer_id"],json.dumps(payload("multi-update",w1,w2,[{"variant_id":v,"quantity":"1"},{"variant_id":v2,"quantity":"1"}],when="2026-07-16"))])[0][0])
  chk("guarded correction reverses and replaces transfer",updated.get("replaced_transfer_id")==multi["transfer_id"] and stock(s,v,w2)==1 and stock(s,v2,w2)==1)
  rv,rw1=setup_scope(s,"RACE","PCS");rw2=wh(s,"RACEDEST");purchase(s,"rp",rv,rw1,1,50,"2026-07-01")
  with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(call,[lambda:transfer(s,payload("race-t",rw1,rw2,[{"variant_id":rv,"quantity":"1"}])),lambda:sale(s,"race-s",rv,rw1,1,90)]))
  chk("concurrent sale and transfer permit one consumer",sorted(x[0] for x in out)==["ok","rejected"],out)
  bv,bw1=setup_scope(sb,"ISO","PCS");bw2=wh(sb,"ISODEST");purchase(sb,"bp",bv,bw1,1,20,"2026-07-01");iso=transfer(sb,payload("iso",bw1,bw2,[{"variant_id":bv,"quantity":"1"}]));chk("numbering is tenant isolated",iso["document_number"]=="TRF-000001")
  chk("transfer detail and navigation functions work",js(q(sb,"SELECT quantity_transfer_navigate('current',%s)",[iso["transfer_id"]])[0][0])["transfer_id"]==iso["transfer_id"])
  c2.refresh_from_db();user=get_user_model().objects.create_superuser(username=f"p15_{TAG}",email="p15@example.com",password="pass");Membership.objects.create(user=user,company=c2);client=Client(SERVER_NAME="localhost");client.force_login(user)
  page=client.get("/transfers/");chk("quantity transfer page works",page.status_code==200 and b"Warehouse Transfers" in page.content,(page.status_code,page.content[:160]))
  nav=client.get("/transfers/navigate/",{"action":"current","current_id":iso["transfer_id"]});summ=client.get("/transfers/summary/")
  chk("navigation and summary work",nav.status_code==200 and summ.status_code==200,(nav.status_code,nav.content[:160],summ.status_code,summ.content[:160]))
 finally:
  if user:user.delete()
  drop(c2);drop(c1)
 passed=sum(o for _,o,_ in R)
 for n,o,d in R:print(f"{'PASS' if o else 'FAIL'}: {n}"+(f" — {d}" if d and not o else ""))
 print(f"\nQuantity transfers: {passed}/{len(R)} passed")
 if passed!=len(R):raise SystemExit(1)
if __name__=="__main__":main()
