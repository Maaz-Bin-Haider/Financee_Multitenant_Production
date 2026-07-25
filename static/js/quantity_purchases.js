(function () {
  "use strict";
  const cfg = window.QPUR || { urls: {} };
  const container = document.getElementById("purchase-lines");
  if (!container) return;
  let items = [], warehouses = [];
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
  const csrf = () => (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
  const fmt = (v) => Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  const notify = (kind, message) => window.Alerts && Alerts[kind] ? Alerts[kind](message) : window.alert(message);
  async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    return { ok: response.ok, data: await response.json().catch(() => ({})) };
  }
  function total() {
    let qty = 0, value = 0;
    container.querySelectorAll(".item-row").forEach((row) => {
      const q = Number(row.querySelector(".quantity").value || 0);
      const c = Number(row.querySelector(".unit-cost").value || 0);
      qty += q; value += q * c;
    });
    document.getElementById("total-quantity").textContent = fmt(qty);
    document.getElementById("total-cost").textContent = fmt(value);
  }
  function addLine(data) {
    data = data || {};
    const row = document.createElement("div");
    row.className = "item-row";
    row.style.gridTemplateColumns = "2fr 1.4fr 100px 120px 110px";
    row.innerHTML = `
      <select class="sale-input variant"><option value="">Select SKU</option>${items.map((x) => `<option value="${x.variant_id}" ${String(x.variant_id) === String(data.variant_id) ? "selected" : ""}>${esc(x.sku)} — ${esc(x.product_name)} (${esc(x.unit_code)})</option>`).join("")}</select>
      <select class="sale-input warehouse"><option value="">Select warehouse</option>${warehouses.map((x) => `<option value="${x.warehouse_id}" ${String(x.warehouse_id) === String(data.warehouse_id) ? "selected" : ""}>${esc(x.warehouse_code)} — ${esc(x.warehouse_name)}</option>`).join("")}</select>
      <input class="sale-input quantity" type="number" min="0" step="0.001" value="${esc(data.quantity || "")}">
      <input class="sale-input unit-cost" type="number" min="0" step="0.000001" value="${esc(data.unit_cost_base || "")}">
      <button type="button" class="custom-btn remove"><i class="fa-solid fa-trash"></i> Remove</button>`;
    row.querySelector(".remove").addEventListener("click", () => { row.remove(); total(); });
    row.querySelectorAll("input").forEach((el) => el.addEventListener("input", total));
    container.appendChild(row); total();
  }
  const lines = () => [...container.querySelectorAll(".item-row")].map((row) => ({
    variant_id: row.querySelector(".variant").value,
    warehouse_id: row.querySelector(".warehouse").value,
    quantity: row.querySelector(".quantity").value,
    unit_cost_base: row.querySelector(".unit-cost").value
  }));
  function reset() {
    document.getElementById("purchase-id").value = "";
    document.getElementById("document-number").textContent = "New";
    document.getElementById("vendor-name").value = "";
    document.getElementById("description").value = "";
    container.innerHTML = ""; addLine();
  }
  function display(doc) {
    document.getElementById("purchase-id").value = doc.purchase_invoice_id;
    document.getElementById("document-number").textContent = `${doc.document_number} (${doc.status})`;
    document.getElementById("invoice-date").value = doc.invoice_date;
    document.getElementById("vendor-name").value = doc.vendor_name;
    document.getElementById("purchase-type").value = doc.purchase_type;
    document.getElementById("payment-account").value = doc.payment_account_code || "1000";
    document.getElementById("payment-account").disabled = doc.purchase_type !== "cash";
    document.getElementById("description").value = doc.description || "";
    container.innerHTML = ""; (doc.lines || []).forEach(addLine); total();
  }
  async function navigate(action) {
    const id = document.getElementById("purchase-id").value;
    const { ok, data } = await fetchJSON(`${cfg.urls.navigate}?action=${action}&current_id=${encodeURIComponent(id)}`);
    if (ok) display(data); else notify("warning", data.message || "No purchase found.");
  }
  async function summary() {
    const { ok, data } = await fetchJSON(cfg.urls.summary);
    const body = document.getElementById("summary-body");
    body.innerHTML = ok && data.documents.length ? data.documents.map((d) => `<tr data-id="${d.purchase_invoice_id}"><td>${esc(d.document_number)}</td><td>${esc(d.invoice_date)}</td><td>${esc(d.vendor_name)}</td><td>${esc(d.purchase_type)}</td><td>${esc(d.status)}</td><td class="num">${fmt(d.total_base)}</td></tr>`).join("") : '<tr><td colspan="6" class="os-empty">No purchases.</td></tr>';
    body.querySelectorAll("tr[data-id]").forEach((row) => row.addEventListener("click", async () => {
      const { ok: found, data: doc } = await fetchJSON(`${cfg.urls.navigate}?action=current&current_id=${row.dataset.id}`);
      if (found) display(doc);
    }));
  }
  document.getElementById("purchase-type").addEventListener("change", (e) => {
    document.getElementById("payment-account").disabled = e.target.value !== "cash";
  });
  document.getElementById("add-line")?.addEventListener("click", () => addLine());
  document.getElementById("previous").addEventListener("click", () => navigate("previous"));
  document.getElementById("next").addEventListener("click", () => navigate("next"));
  document.getElementById("refresh-summary").addEventListener("click", summary);
  document.getElementById("save")?.addEventListener("click", async () => {
    const payload = {
      action: "submit", purchase_id: document.getElementById("purchase-id").value || null,
      invoice_date: document.getElementById("invoice-date").value,
      vendor_name: document.getElementById("vendor-name").value,
      purchase_type: document.getElementById("purchase-type").value,
      payment_account_code: document.getElementById("payment-account").value,
      description: document.getElementById("description").value,
      idempotency_key: crypto.randomUUID(), items: lines()
    };
    const { ok, data } = await fetchJSON(cfg.urls.purchase, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(payload)
    });
    if (!ok) return notify("error", data.message || "Purchase failed.");
    notify("success", `Purchase ${data.document_number} saved.`);
    document.getElementById("purchase-id").value = data.purchase_invoice_id;
    await summary(); await navigate("current");
  });
  document.getElementById("reverse")?.addEventListener("click", async () => {
    const id = document.getElementById("purchase-id").value;
    if (!id || !window.confirm("Reverse this purchase? Consumed stock blocks reversal.")) return;
    const { ok, data } = await fetchJSON(cfg.urls.purchase, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ action: "reverse", purchase_id: Number(id) })
    });
    if (!ok) return notify("error", data.message || "Reversal failed.");
    notify("success", "Purchase reversed."); await summary(); await navigate("current");
  });
  Promise.all([fetchJSON(cfg.urls.catalog), fetchJSON(cfg.urls.warehouses)])
    .then(([a, b]) => { items = a.data.items || []; warehouses = b.data.warehouses || []; reset(); });
  summary();
})();
