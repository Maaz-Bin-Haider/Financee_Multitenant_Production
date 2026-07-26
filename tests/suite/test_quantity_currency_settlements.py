#!/usr/bin/env python3
"""Phase 18 foreign-document snapshot foundation checks."""
import json, os, sys, time
from decimal import Decimal
ROOT=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,ROOT);os.environ.setdefault("DJANGO_SETTINGS_MODULE","financee.settings")
import django;django.setup()
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from tenancy.models import Company,Currency,Membership,INVENTORY_MODE_QUANTITY
from tenancy.schema_verification import verify_company_schema
from tests.suite.test_quantity_purchases import setup_scope
from tests.suite.test_quantity_sale_returns import account
TAG=f"{time.strftime('%H%M%S')}_{os.getpid()}";R=[]
def chk(n,o):R.append((n,bool(o)))
def js(v):return json.loads(v) if isinstance(v,str) else v
def q(s,sql,p=None):
 with connection.cursor() as c:
  c.execute(f"SET search_path TO {connection.ops.quote_name(s)}, public")
  try:c.execute(sql,p or []);return c.fetchall() if c.description else []
  finally:c.execute("SET search_path TO public")
def drop(c):
 if not c:return
 with connection.cursor() as x:x.execute(f"DROP SCHEMA IF EXISTS {connection.ops.quote_name(c.schema_name)} CASCADE");x.execute("SET search_path TO public")
 Company.objects.filter(pk=c.pk).delete()
def main():
 company=user=None
 try:
  company=Company.objects.create(name=f"PH18 {TAG}",inventory_mode=INVENTORY_MODE_QUANTITY,
   base_currency=Currency.objects.get(pk="PKR"),tax_environment="non_tax")
  s=company.schema_name;chk("fresh schema includes currency version",q(s,"SELECT version FROM tenant_schema_metadata")[0][0]>=14);chk("schema verifies",verify_company_schema(company,use_cache=False).ok)
  tables={x[0] for x in q(s,"SELECT tablename FROM pg_tables WHERE schemaname=current_schema()")}
  chk("settlement allocation entities exist",{"foreign_payments","payment_allocations","foreign_receipts","receipt_allocations"}<=tables)
  v,w=setup_scope(s,"FX","PCS");user=get_user_model().objects.create_superuser(username=f"p18_{TAG}",email="p18@example.com",password="pass");Membership.objects.create(user=user,company=company);client=Client(SERVER_NAME="localhost");client.force_login(user)
  pur=client.post("/purchase/purchasing/",data=json.dumps({"action":"submit","idempotency_key":f"p-{TAG}","invoice_date":"2026-07-20","vendor_name":"Foreign Vendor","purchase_type":"credit","transaction_currency_code":"USD","exchange_rate":"280","items":[{"variant_id":v,"warehouse_id":w,"quantity":"10","unit_cost_base":"10","tax_classification":"none"}]}),content_type="application/json")
  chk("foreign purchase posts",pur.status_code==200)
  pid=pur.json().get("purchase_invoice_id");prow=q(s,"SELECT transaction_currency_code,exchange_rate,total_foreign,total_base,remaining_foreign FROM purchase_invoices WHERE purchase_invoice_id=%s",[pid])[0]
  chk("foreign purchase snapshots reconcile",prow==("USD",Decimal("280"),Decimal("100"),Decimal("28000"),Decimal("100")) and account(s,"1400")==Decimal("28000") and account(s,"2000")==Decimal("-28000"))
  sal=client.post("/sale/sales/",data=json.dumps({"action":"submit","idempotency_key":f"s-{TAG}","invoice_date":"2026-07-21","customer_name":"Foreign Customer","sale_type":"credit","transaction_currency_code":"USD","exchange_rate":"300","items":[{"variant_id":v,"warehouse_id":w,"quantity":"2","unit_price_base":"20","tax_classification":"none"}]}),content_type="application/json")
  sid=sal.json().get("sale_invoice_id");srow=q(s,"SELECT transaction_currency_code,exchange_rate,total_foreign,total_base,remaining_foreign FROM sale_invoices WHERE sale_invoice_id=%s",[sid])[0]
  chk("foreign sale snapshots reconcile",sal.status_code==200 and srow==("USD",Decimal("300"),Decimal("40"),Decimal("12000"),Decimal("40")) and account(s,"4000")==Decimal("-12000"))
  pay1=js(q(s,"SELECT quantity_settle_foreign_purchase(%s::jsonb)",[json.dumps({"purchase_invoice_id":pid,"settlement_date":"2026-07-22","foreign_amount":"40","settlement_rate":"285","payment_account_code":"1100","idempotency_key":f"pay1-{TAG}","created_by_id":user.pk})])[0][0])
  chk("partial supplier settlement posts realized loss",Decimal(str(pay1["carrying_base"]))==Decimal("11200") and Decimal(str(pay1["settlement_base"]))==Decimal("11400") and Decimal(str(pay1["realized_loss_base"]))==Decimal("200") and Decimal(str(pay1["remaining_foreign"]))==Decimal("60"))
  pay2=js(q(s,"SELECT quantity_settle_foreign_purchase(%s::jsonb)",[json.dumps({"purchase_invoice_id":pid,"settlement_date":"2026-07-23","foreign_amount":"60","settlement_rate":"275","payment_account_code":"1100","idempotency_key":f"pay2-{TAG}","created_by_id":user.pk})])[0][0])
  chk("final supplier settlement posts gain and clears AP",Decimal(str(pay2["realized_gain_base"]))==Decimal("300") and Decimal(str(pay2["remaining_foreign"]))==0 and account(s,"2000")==0)
  rec1=js(q(s,"SELECT quantity_settle_foreign_sale(%s::jsonb)",[json.dumps({"sale_invoice_id":sid,"settlement_date":"2026-07-22","foreign_amount":"20","settlement_rate":"310","receipt_account_code":"1100","idempotency_key":f"rec1-{TAG}","created_by_id":user.pk})])[0][0])
  chk("partial customer settlement posts realized gain",Decimal(str(rec1["carrying_base"]))==Decimal("6000") and Decimal(str(rec1["realized_gain_base"]))==Decimal("200") and Decimal(str(rec1["remaining_foreign"]))==Decimal("20"))
  rec2=js(q(s,"SELECT quantity_settle_foreign_sale(%s::jsonb)",[json.dumps({"sale_invoice_id":sid,"settlement_date":"2026-07-23","foreign_amount":"20","settlement_rate":"290","receipt_account_code":"1100","idempotency_key":f"rec2-{TAG}","created_by_id":user.pk})])[0][0])
  chk("final customer settlement posts loss and clears AR",Decimal(str(rec2["realized_loss_base"]))==Decimal("200") and Decimal(str(rec2["remaining_foreign"]))==0 and account(s,"1200")==0)
  chk("realized gain/loss control accounts reconcile",account(s,"4910")==Decimal("-500") and account(s,"1990")==Decimal("400"))
  report=js(q(s,"SELECT quantity_currency_report(NULL,NULL)")[0][0])
  chk("realized gain/loss report reconciles",Decimal(str(report["realized_gain_base"]))==Decimal("500") and Decimal(str(report["realized_loss_base"]))==Decimal("400") and report["open_purchase_foreign"]==[] and report["open_sale_foreign"]==[])
  chk("historical invoice snapshots remain unchanged",q(s,"SELECT exchange_rate,total_foreign,total_base FROM purchase_invoices WHERE purchase_invoice_id=%s",[pid])[0]==(Decimal("280"),Decimal("100"),Decimal("28000")))
  pv,pw=setup_scope(s,"FXRET","PCS")
  p2=client.post("/purchase/purchasing/",data=json.dumps({"action":"submit","idempotency_key":f"pr-p-{TAG}","invoice_date":"2026-07-20","vendor_name":"Return Vendor","purchase_type":"credit","transaction_currency_code":"USD","exchange_rate":"280","items":[{"variant_id":pv,"warehouse_id":pw,"quantity":"4","unit_cost_base":"10","tax_classification":"none"}]}),content_type="application/json").json()
  p2id=p2["purchase_invoice_id"];pl=q(s,"SELECT purchase_line_id FROM purchase_lines WHERE purchase_invoice_id=%s",[p2id])[0][0]
  pr=client.post("/purchaseReturn/create-purchase-return/",data=json.dumps({"action":"submit","idempotency_key":f"pr-{TAG}","return_date":"2026-07-21","vendor_name":"Return Vendor","items":[{"source_purchase_line_id":pl,"quantity":"1"}]}),content_type="application/json")
  chk("foreign purchase return before settlement reduces open balance",pr.status_code==200 and q(s,"SELECT returned_foreign,remaining_foreign FROM purchase_invoices WHERE purchase_invoice_id=%s",[p2id])[0]==(Decimal("10"),Decimal("30")))
  http_pay=client.post("/purchase/purchasing/",data=json.dumps({"action":"settle","purchase_invoice_id":p2id,"settlement_date":"2026-07-22","foreign_amount":"20","settlement_rate":"280","payment_account_code":"1000","idempotency_key":f"http-pay-{TAG}"}),content_type="application/json")
  chk("supplier settlement HTTP and cash path work",http_pay.status_code==200 and q(s,"SELECT remaining_foreign FROM purchase_invoices WHERE purchase_invoice_id=%s",[p2id])[0][0]==Decimal("10"))
  excess_pr=client.post("/purchaseReturn/create-purchase-return/",data=json.dumps({"action":"submit","idempotency_key":f"pr-excess-{TAG}","return_date":"2026-07-23","vendor_name":"Return Vendor","items":[{"source_purchase_line_id":pl,"quantity":"2"}]}),content_type="application/json")
  chk("return after settlement cannot consume realized balance",excess_pr.status_code==400)
  sv,sw=setup_scope(s,"FXSRET","PCS")
  client.post("/purchase/purchasing/",data=json.dumps({"action":"submit","idempotency_key":f"sr-stock-{TAG}","invoice_date":"2026-07-20","vendor_name":"Stock","purchase_type":"cash","items":[{"variant_id":sv,"warehouse_id":sw,"quantity":"4","unit_cost_base":"5","tax_classification":"none"}]}),content_type="application/json")
  s2=client.post("/sale/sales/",data=json.dumps({"action":"submit","idempotency_key":f"sr-s-{TAG}","invoice_date":"2026-07-21","customer_name":"Return Customer","sale_type":"credit","transaction_currency_code":"USD","exchange_rate":"300","items":[{"variant_id":sv,"warehouse_id":sw,"quantity":"4","unit_price_base":"10","tax_classification":"none"}]}),content_type="application/json").json()
  s2id=s2["sale_invoice_id"];sl=q(s,"SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",[s2id])[0][0]
  sr=client.post("/saleReturn/create-sale-return/",data=json.dumps({"action":"submit","idempotency_key":f"sr-{TAG}","return_date":"2026-07-22","customer_name":"Return Customer","items":[{"source_sale_line_id":sl,"destination_warehouse_id":sw,"quantity":"1"}]}),content_type="application/json")
  chk("foreign sale return before settlement reduces open balance",sr.status_code==200 and q(s,"SELECT returned_foreign,remaining_foreign FROM sale_invoices WHERE sale_invoice_id=%s",[s2id])[0]==(Decimal("10"),Decimal("30")))
  http_rec=client.post("/sale/sales/",data=json.dumps({"action":"settle","sale_invoice_id":s2id,"settlement_date":"2026-07-23","foreign_amount":"30","settlement_rate":"300","receipt_account_code":"1000","idempotency_key":f"http-rec-{TAG}"}),content_type="application/json")
  chk("customer settlement HTTP and cash path work",http_rec.status_code==200 and q(s,"SELECT remaining_foreign FROM sale_invoices WHERE sale_invoice_id=%s",[s2id])[0][0]==0)
  blocked_sr=client.post("/saleReturn/create-sale-return/",data=json.dumps({"action":"submit","idempotency_key":f"sr-excess-{TAG}","return_date":"2026-07-24","customer_name":"Return Customer","items":[{"source_sale_line_id":sl,"destination_warehouse_id":sw,"quantity":"1"}]}),content_type="application/json")
  chk("fully settled foreign sale rejects later return",blocked_sr.status_code==400)
  chk("currency administration UI renders",client.get("/purchase/purchasing/").status_code==200 and b"Foreign Supplier Settlement" in client.get("/purchase/purchasing/").content and b"Foreign Customer Settlement" in client.get("/sale/sales/").content)
  over=client.post("/sale/sales/",data=json.dumps({"action":"settle","sale_invoice_id":s2id,"settlement_date":"2026-07-24","foreign_amount":"1","settlement_rate":"300","idempotency_key":f"over-{TAG}"}),content_type="application/json")
  chk("settlement overpayment is rejected",over.status_code==400)
  bad=client.post("/sale/sales/",data=json.dumps({"action":"submit","invoice_date":"2026-07-22","customer_name":"Bad Rate","sale_type":"credit","transaction_currency_code":"USD","exchange_rate":"0","items":[{"variant_id":v,"warehouse_id":w,"quantity":"1","unit_price_base":"1","tax_classification":"none"}]}),content_type="application/json")
  chk("zero foreign rate rejected",bad.status_code==400)
  domestic=client.post("/sale/sales/",data=json.dumps({"action":"submit","invoice_date":"2026-07-22","customer_name":"Domestic","sale_type":"credit","transaction_currency_code":"PKR","exchange_rate":"2","items":[{"variant_id":v,"warehouse_id":w,"quantity":"1","unit_price_base":"1","tax_classification":"none"}]}),content_type="application/json")
  chk("domestic explicit conversion rejected",domestic.status_code==400)
 finally:
  if user:user.delete()
  drop(company)
 passed=sum(o for _,o in R)
 for n,o in R:print(f"{'PASS' if o else 'FAIL'}: {n}")
 print(f"\nQuantity currency foundation: {passed}/{len(R)} passed")
 if passed!=len(R):raise SystemExit(1)
if __name__=="__main__":main()
