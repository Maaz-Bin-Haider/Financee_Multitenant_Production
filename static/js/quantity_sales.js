(function () {
  "use strict";
  const cfg = window.QSAL || { urls: {} };
  const container = document.getElementById("sale-lines");
  if (!container) return;
  let items = [], warehouses = [];
  const taxCodes = JSON.parse((document.getElementById("quantity-tax-codes") || {}).textContent || "[]");
  const taxable = cfg.taxEnvironment === "tax";
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
      const c = Number(row.querySelector(".unit-price").value || 0);
      qty += q; value += q * c;
    });
    document.getElementById("total-quantity").textContent = fmt(qty);
    document.getElementById("total-price").textContent = fmt(value);
  }
  function addLine(data) {
    data = data || {};
    const row = document.createElement("div");
    row.className = "item-row";
    row.style.gridTemplateColumns = taxable ? "1.8fr 1.2fr 85px 105px 110px 90px 120px 130px 90px" : "1.8fr 1.2fr 85px 105px 110px 90px 90px";
    row.innerHTML = `
      <select class="sale-input variant"><option value="">Select SKU</option>${items.map((x) => `<option value="${x.variant_id}" ${String(x.variant_id) === String(data.variant_id) ? "selected" : ""}>${esc(x.sku)} — ${esc(x.product_name)} (${esc(x.unit_code)})</option>`).join("")}</select>
      <select class="sale-input warehouse"><option value="">Select warehouse</option>${warehouses.map((x) => `<option value="${x.warehouse_id}" ${String(x.warehouse_id) === String(data.warehouse_id) ? "selected" : ""}>${esc(x.warehouse_code)} — ${esc(x.warehouse_name)}</option>`).join("")}</select>
      <input class="sale-input quantity" type="number" min="0" step="0.001" value="${esc(data.quantity || "")}">
      <input class="sale-input unit-price" type="number" min="0" step="0.000001" value="${esc(data.unit_price_base || "")}">
      <select class="sale-input discount-type"><option value="none">None</option><option value="percent">%</option><option value="fixed">Fixed</option></select>
      <input class="sale-input discount-value" type="number" min="0" step="0.01" value="${esc(data.line_discount_value || data.discount_value || "0")}">
      ${taxable ? `<select class="sale-input tax-classification"><option value="taxable">Taxable</option><option value="zero_rated">Zero-rated</option><option value="exempt">Exempt</option></select><div><select class="sale-input tax-code"><option value="">Tax code</option>${taxCodes.map((x) => `<option value="${x.tax_code_id}">${esc(x.code)} (${esc(x.rate_percent)}%)</option>`).join("")}</select><input class="sale-input exemption-reference" placeholder="Exemption ref" value="${esc(data.exemption_reference || "")}"></div>` : ""}
      <button type="button" class="custom-btn remove"><i class="fa-solid fa-trash"></i> Remove</button>`;
    row.querySelector(".discount-type").value = data.line_discount_type || data.discount_type || "none";
    if (taxable) {
      row.querySelector(".tax-classification").value = data.tax_classification || "taxable";
      row.querySelector(".tax-code").value = data.tax_code_id || "";
    }
    row.querySelector(".remove").addEventListener("click", () => { row.remove(); total(); });
    row.querySelectorAll("input").forEach((el) => el.addEventListener("input", total));
    container.appendChild(row); total();
  }
  const lines = () => [...container.querySelectorAll(".item-row")].map((row) => ({
    variant_id: row.querySelector(".variant").value,
    warehouse_id: row.querySelector(".warehouse").value,
    quantity: row.querySelector(".quantity").value,
    unit_price_base: row.querySelector(".unit-price").value,
    discount_type: row.querySelector(".discount-type").value,
    discount_value: row.querySelector(".discount-value").value,
    tax_classification: taxable ? row.querySelector(".tax-classification").value : "none",
    tax_code_id: taxable ? (row.querySelector(".tax-code").value || null) : null,
    exemption_reference: taxable ? row.querySelector(".exemption-reference").value : ""
  }));
  const payload = (action = "submit") => ({
    action, sale_id: document.getElementById("sale-id").value || null,
    invoice_date: document.getElementById("invoice-date").value,
    customer_name: document.getElementById("customer-name").value,
    sale_type: document.getElementById("sale-type").value,
    payment_account_code: document.getElementById("payment-account").value,
    description: document.getElementById("description").value,
    tax_mode: document.getElementById("tax-mode").value,
    invoice_discount_type: document.getElementById("invoice-discount-type").value,
    invoice_discount_value: document.getElementById("invoice-discount-value").value,
    transaction_currency_code: document.getElementById("transaction-currency").value,
    exchange_rate: document.getElementById("exchange-rate").value || null,
    idempotency_key: crypto.randomUUID(), items: lines()
  });
  function reset() {
    document.getElementById("sale-id").value = "";
    document.getElementById("document-number").textContent = "New";
    document.getElementById("customer-name").value = "";
    document.getElementById("description").value = "";
    document.getElementById("invoice-discount-type").value = "none";
    document.getElementById("invoice-discount-value").value = "0";
    document.getElementById("transaction-currency").value = cfg.currency;
    document.getElementById("exchange-rate").value = "";
    document.getElementById("exchange-rate").disabled = true;
    container.innerHTML = ""; addLine();
    if (window.DocumentAttachments) DocumentAttachments.reset();
  }
  function display(doc) {
    document.getElementById("sale-id").value = doc.sale_invoice_id;
    document.getElementById("document-number").textContent = `${doc.document_number} (${doc.status})`;
    document.getElementById("invoice-date").value = doc.invoice_date;
    document.getElementById("customer-name").value = doc.customer_name;
    document.getElementById("sale-type").value = doc.sale_type;
    document.getElementById("payment-account").value = doc.payment_account_code || "1000";
    document.getElementById("payment-account").disabled = doc.sale_type !== "cash";
    document.getElementById("description").value = doc.description || "";
    document.getElementById("tax-mode").value = doc.tax_mode || "exclusive";
    document.getElementById("invoice-discount-type").value = doc.invoice_discount_type || "none";
    document.getElementById("invoice-discount-value").value = doc.invoice_discount_value || "0";
    document.getElementById("total-tax").textContent = fmt(doc.tax_total_base);
    document.getElementById("transaction-currency").value = doc.transaction_currency_code || cfg.currency;
    document.getElementById("exchange-rate").value = doc.exchange_rate || "";
    document.getElementById("exchange-rate").disabled = (doc.transaction_currency_code || cfg.currency) === cfg.currency;
    const balance = document.getElementById("foreign-balance");
    if (balance) balance.textContent = `${doc.remaining_foreign || 0} ${doc.transaction_currency_code || cfg.currency} remains unsettled.`;
    container.innerHTML = ""; (doc.lines || []).forEach(addLine); total();
    if (window.DocumentAttachments) DocumentAttachments.load(doc.sale_invoice_id);
  }
  async function navigate(action) {
    const id = document.getElementById("sale-id").value;
    const { ok, data } = await fetchJSON(`${cfg.urls.navigate}?action=${action}&current_id=${encodeURIComponent(id)}`);
    if (ok) display(data); else notify("warning", data.message || "No sale found.");
  }
  async function summary() {
    const { ok, data } = await fetchJSON(cfg.urls.summary);
    const body = document.getElementById("summary-body");
    body.innerHTML = ok && data.documents.length ? data.documents.map((d) => `<tr data-id="${d.sale_invoice_id}"><td>${esc(d.document_number)}</td><td>${esc(d.invoice_date)}</td><td>${esc(d.customer_name)}</td><td>${esc(d.sale_type)}</td><td>${esc(d.status)}</td><td class="num">${fmt(d.total_base)}</td></tr>`).join("") : '<tr><td colspan="6" class="os-empty">No sales.</td></tr>';
    body.querySelectorAll("tr[data-id]").forEach((row) => row.addEventListener("click", async () => {
      const { ok: found, data: doc } = await fetchJSON(`${cfg.urls.navigate}?action=current&current_id=${row.dataset.id}`);
      if (found) display(doc);
    }));
  }
  document.getElementById("sale-type").addEventListener("change", (e) => {
    document.getElementById("payment-account").disabled = e.target.value !== "cash";
  });
  document.getElementById("transaction-currency").addEventListener("change", (e) => {
    const domestic = e.target.value === cfg.currency;
    document.getElementById("exchange-rate").disabled = domestic;
    if (domestic) document.getElementById("exchange-rate").value = "";
  });
  document.getElementById("add-line")?.addEventListener("click", () => addLine());
  document.getElementById("previous").addEventListener("click", () => navigate("previous"));
  document.getElementById("next").addEventListener("click", () => navigate("next"));
  document.getElementById("refresh-summary").addEventListener("click", summary);
  document.getElementById("preview")?.addEventListener("click", event => QuantityUI.run(event.currentTarget, async () => {
    const { ok, data } = await fetchJSON(cfg.urls.sale, {
      method: "POST", headers: {"Content-Type":"application/json","X-CSRFToken":csrf()},
      body: JSON.stringify(payload("preview"))
    });
    if (!ok) return notify("error", data.message || "Calculation failed.");
    document.getElementById("total-tax").textContent = fmt(data.calculation.tax_total_base);
    document.getElementById("total-price").textContent = fmt(data.calculation.total_base);
    notify("success", "Totals verified by the accounting engine.");
  }));
  document.getElementById("save")?.addEventListener("click", event => QuantityUI.run(event.currentTarget, async () => {
    const requestPayload = payload();
    const options = window.DocumentAttachments
      ? DocumentAttachments.requestOptions(requestPayload, csrf())
      : { method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(requestPayload) };
    const { ok, data } = await fetchJSON(cfg.urls.sale, options);
    if (!ok) return notify("error", data.message || "Sale failed.");
    notify("success", `Sale ${data.document_number} saved.`);
    document.getElementById("sale-id").value = data.sale_invoice_id;
    await summary(); await navigate("current");
  }));
  document.getElementById("settle")?.addEventListener("click", async () => {
    const id = document.getElementById("sale-id").value;
    if (!id) return notify("warning", "Select a foreign credit sale.");
    const payload = { action: "settle", sale_invoice_id: Number(id),
      settlement_date: document.getElementById("settlement-date").value,
      foreign_amount: document.getElementById("settlement-amount").value,
      settlement_rate: document.getElementById("settlement-rate").value,
      receipt_account_code: document.getElementById("settlement-account").value,
      idempotency_key: crypto.randomUUID() };
    const { ok, data } = await fetchJSON(cfg.urls.sale, { method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(payload) });
    if (!ok) return notify("error", data.message || "Settlement failed.");
    notify("success", `Receipt ${data.document_number} posted.`); await navigate("current");
  });
  document.getElementById("reverse")?.addEventListener("click", async () => {
    const id = document.getElementById("sale-id").value;
    if (!id || !window.confirm("Reverse this sale and restore its FIFO stock?")) return;
    const { ok, data } = await fetchJSON(cfg.urls.sale, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ action: "reverse", sale_id: Number(id) })
    });
    if (!ok) return notify("error", data.message || "Reversal failed.");
    notify("success", "Sale reversed."); await summary(); await navigate("current");
  });
  Promise.all([fetchJSON(cfg.urls.catalog), fetchJSON(cfg.urls.warehouses)])
    .then(([a, b]) => { items = a.data.items || []; warehouses = b.data.warehouses || []; reset(); });
  if (window.DocumentAttachments) {
    DocumentAttachments.init("sale", () => document.getElementById("sale-id").value || "");
  }
  summary();
})();
