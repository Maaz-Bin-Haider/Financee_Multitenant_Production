(function () {
  "use strict";
  const cfg = window.QSRET || { urls: {} };
  const box = document.getElementById("return-lines");
  if (!box) return;
  let sources = [], warehouses = [];
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const csrf = () => (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
  async function get(url, options) {
    const r = await fetch(url, options); return {ok:r.ok,data:await r.json().catch(() => ({}))};
  }
  function addLine(data) {
    data = data || {};
    const row = document.createElement("div"); row.className = "item-row";
    row.style.gridTemplateColumns = "2.2fr 1.4fr 120px 100px";
    row.innerHTML = `<select class="sale-input source"><option value="">Select sold line</option>${sources.map(x=>`<option value="${x.source_sale_line_id}" ${String(x.source_sale_line_id)===String(data.source_sale_line_id)?"selected":""}>${esc(x.document_number)} — ${esc(x.sku)} — available ${esc(x.returnable_quantity)}</option>`).join("")}</select>
    <select class="sale-input warehouse">${warehouses.map(x=>`<option value="${x.warehouse_id}" ${String(x.warehouse_id)===String(data.destination_warehouse_id)?"selected":""}>${esc(x.warehouse_code)} — ${esc(x.warehouse_name)}</option>`).join("")}</select>
    <input class="sale-input quantity" type="number" min="0" step="0.001" value="${esc(data.quantity||"")}">
    <button type="button" class="custom-btn remove">Remove</button>`;
    row.querySelector(".source").addEventListener("change", e => {
      const src=sources.find(x=>String(x.source_sale_line_id)===e.target.value);
      if(src){row.querySelector(".warehouse").value=src.source_warehouse_id; if(!document.getElementById("customer-name").value) document.getElementById("customer-name").value=src.customer_name;}
    });
    row.querySelector(".remove").onclick=()=>row.remove(); box.appendChild(row);
  }
  const lines=()=>[...box.querySelectorAll(".item-row")].map(r=>({
    source_sale_line_id:r.querySelector(".source").value,
    destination_warehouse_id:r.querySelector(".warehouse").value,
    quantity:r.querySelector(".quantity").value
  }));
  function display(d){
    document.getElementById("return-id").value=d.sale_return_id;
    document.getElementById("document-number").textContent=`${d.document_number} (${d.status})`;
    document.getElementById("return-date").value=d.return_date;
    document.getElementById("customer-name").value=d.customer_name;
    document.getElementById("description").value=d.description||"";
    box.innerHTML=""; (d.lines||[]).forEach(addLine);
    if(window.DocumentAttachments)DocumentAttachments.load(d.sale_return_id);
  }
  async function navigate(action){
    const id=document.getElementById("return-id").value;
    const r=await get(`${cfg.urls.navigate}?action=${action}&current_id=${encodeURIComponent(id)}`);
    if(r.ok) display(r.data);
  }
  async function summary(){
    const r=await get(cfg.urls.summary), body=document.getElementById("summary-body");
    body.innerHTML=r.ok&&(r.data.documents||[]).length?r.data.documents.map(d=>`<tr data-id="${d.sale_return_id}"><td>${esc(d.document_number)}</td><td>${esc(d.return_date)}</td><td>${esc(d.customer_name)}</td><td>${esc(d.status)}</td><td>${esc(d.revenue_total_base)}</td><td>${esc(d.cogs_total_base)}</td></tr>`).join(""):'<tr><td colspan="6">No returns.</td></tr>';
    body.querySelectorAll("tr[data-id]").forEach(row=>row.onclick=async()=>{const x=await get(`${cfg.urls.navigate}?action=current&current_id=${row.dataset.id}`);if(x.ok)display(x.data);});
  }
  document.getElementById("add-line")?.addEventListener("click",()=>addLine());
  document.getElementById("previous").onclick=()=>navigate("previous");
  document.getElementById("next").onclick=()=>navigate("next");
  document.getElementById("refresh-summary").onclick=summary;
  document.getElementById("save")?.addEventListener("click",async()=>{
    const payload={action:"submit",sale_return_id:document.getElementById("return-id").value||null,
      return_date:document.getElementById("return-date").value,customer_name:document.getElementById("customer-name").value,
      description:document.getElementById("description").value,idempotency_key:crypto.randomUUID(),items:lines()};
    const options=window.DocumentAttachments?DocumentAttachments.requestOptions(payload,csrf()):{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},body:JSON.stringify(payload)};
    const r=await get(cfg.urls.create,options);
    if(!r.ok)return alert(r.data.message||"Return failed."); document.getElementById("return-id").value=r.data.sale_return_id; await summary(); await navigate("current");
  });
  document.getElementById("reverse")?.addEventListener("click",async()=>{
    const id=document.getElementById("return-id").value;if(!id)return;
    const r=await get(cfg.urls.create,{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":csrf()},body:JSON.stringify({action:"reverse",sale_return_id:Number(id)})});
    if(!r.ok)return alert(r.data.message||"Reversal failed.");await summary();await navigate("current");
  });
  Promise.all([get(cfg.urls.sources),get(cfg.urls.warehouses)]).then(([a,b])=>{sources=a.data.sources||[];warehouses=b.data.warehouses||[];addLine();});
  if(window.DocumentAttachments)DocumentAttachments.init("sale_return",()=>document.getElementById("return-id").value||"");
  summary();
})();
