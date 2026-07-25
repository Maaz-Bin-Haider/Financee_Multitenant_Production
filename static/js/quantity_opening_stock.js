(function () {
  "use strict";
  const cfg = window.QOS || { urls: {} };
  const lines = document.getElementById("quantity-lines");
  if (!lines) return;
  let catalog = [];
  let warehouses = [];

  const esc = (value) => String(value == null ? "" : value).replace(
    /[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
  const csrf = () => (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
  const json = async (url, options) => {
    const response = await fetch(url, options);
    return { ok: response.ok, data: await response.json().catch(() => ({})) };
  };
  const notify = (kind, message) => {
    if (window.Alerts && Alerts[kind]) Alerts[kind](message);
    else window.alert(message);
  };
  const fmt = (value) => Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 6
  });

  function recalculate() {
    let quantity = 0;
    let cost = 0;
    [...lines.querySelectorAll(".item-row")].forEach((row) => {
      const qty = Number(row.querySelector(".quantity").value || 0);
      const unitCost = Number(row.querySelector(".unit-cost").value || 0);
      quantity += qty;
      cost += qty * unitCost;
    });
    document.getElementById("total-lines").textContent = lines.children.length;
    document.getElementById("total-quantity").textContent = fmt(quantity);
    document.getElementById("total-cost").textContent = fmt(cost);
  }

  function addLine() {
    const row = document.createElement("div");
    row.className = "item-row";
    row.style.gridTemplateColumns = "2fr 1.4fr 100px 120px 110px";
    row.innerHTML = `
      <select class="sale-input variant" aria-label="SKU">
        <option value="">Select SKU</option>
        ${catalog.map((item) => `<option value="${item.variant_id}">${esc(item.sku)} — ${esc(item.product_name)} (${esc(item.unit_code)})</option>`).join("")}
      </select>
      <select class="sale-input warehouse" aria-label="Warehouse">
        <option value="">Select warehouse</option>
        ${warehouses.map((item) => `<option value="${item.warehouse_id}">${esc(item.warehouse_code)} — ${esc(item.warehouse_name)}</option>`).join("")}
      </select>
      <input class="sale-input quantity" type="number" min="0" step="0.001" placeholder="0">
      <input class="sale-input unit-cost" type="number" min="0" step="0.000001" placeholder="0.00">
      <button type="button" class="custom-btn remove-line"><i class="fa-solid fa-trash"></i> Remove</button>`;
    row.querySelector(".remove-line").addEventListener("click", () => {
      row.remove();
      recalculate();
    });
    row.querySelectorAll("input").forEach((input) => input.addEventListener("input", recalculate));
    lines.appendChild(row);
    recalculate();
  }

  function collectLines() {
    return [...lines.querySelectorAll(".item-row")].map((row) => ({
      variant_id: row.querySelector(".variant").value,
      warehouse_id: row.querySelector(".warehouse").value,
      quantity: row.querySelector(".quantity").value,
      unit_cost_base: row.querySelector(".unit-cost").value
    }));
  }

  async function loadDocuments() {
    const { ok, data } = await json(cfg.urls.list);
    const body = document.getElementById("loads-body");
    if (!ok || !Array.isArray(data)) {
      body.innerHTML = '<tr><td colspan="7" class="os-empty">Unable to load documents.</td></tr>';
      return;
    }
    body.innerHTML = data.length ? data.map((doc) => `
      <tr>
        <td>${esc(doc.document_number)}</td><td>${esc(doc.opening_date)}</td>
        <td>${esc(doc.status)}</td><td class="num">${doc.line_count}</td>
        <td class="num">${fmt(doc.total_quantity)}</td><td class="num">${fmt(doc.total_cost_base)}</td>
        <td><button class="os-icon-btn view-doc" data-id="${doc.opening_stock_id}" title="Details"><i class="fa-solid fa-eye"></i></button>
        ${cfg.canDelete && doc.status === "posted" ? `<button class="os-icon-btn reverse-doc" data-id="${doc.opening_stock_id}" title="Reverse"><i class="fa-solid fa-rotate-left"></i></button>` : ""}</td>
      </tr>`).join("") : '<tr><td colspan="7" class="os-empty">No opening stock posted.</td></tr>';
    body.querySelectorAll(".view-doc").forEach((button) => button.addEventListener("click", () => showDetails(button.dataset.id)));
    body.querySelectorAll(".reverse-doc").forEach((button) => button.addEventListener("click", () => reverseDocument(button.dataset.id)));
  }

  async function showDetails(id) {
    const { ok, data } = await json(cfg.urls.details + "?id=" + encodeURIComponent(id));
    if (!ok) return notify("error", data.error || "Unable to load details.");
    document.getElementById("details-title").textContent = data.document_number;
    document.getElementById("details-body").innerHTML = `
      <p><strong>Date:</strong> ${esc(data.opening_date)} &nbsp; <strong>Status:</strong> ${esc(data.status)}</p>
      <table class="os-table"><thead><tr><th>SKU</th><th>Warehouse</th><th class="num">Qty</th><th class="num">Cost</th><th class="num">Value</th></tr></thead>
      <tbody>${(data.lines || []).map((line) => `<tr><td>${esc(line.sku)} — ${esc(line.product_name)}</td><td>${esc(line.warehouse_code)}</td><td class="num">${fmt(line.quantity)} ${esc(line.unit_code)}</td><td class="num">${fmt(line.unit_cost_base)}</td><td class="num">${fmt(line.line_total_base)}</td></tr>`).join("")}</tbody></table>`;
    document.getElementById("details-modal").style.display = "flex";
  }

  async function reverseDocument(id) {
    if (!window.confirm("Reverse this opening-stock document? This is allowed only while its original FIFO quantity remains unused.")) return;
    const { ok, data } = await json(cfg.urls.reverse, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ id: Number(id) })
    });
    if (!ok) return notify("error", data.message || "Reversal failed.");
    notify("success", "Opening stock reversed.");
    await Promise.all([loadDocuments(), loadStatus()]);
  }

  async function loadStatus() {
    const { ok, data } = await json(cfg.urls.status);
    if (!ok) return;
    document.getElementById("obe-banner").style.display = "flex";
    document.getElementById("obe-amount").textContent = `${cfg.currency} ${fmt(data.obe_equity_amount)}`;
    const button = document.getElementById("reclass-btn");
    if (button) button.style.display = data.needs_reclass ? "" : "none";
  }

  document.getElementById("add-line-btn")?.addEventListener("click", addLine);
  document.getElementById("refresh-btn").addEventListener("click", loadDocuments);
  document.getElementById("details-close").addEventListener("click", () => {
    document.getElementById("details-modal").style.display = "none";
  });
  document.getElementById("save-btn")?.addEventListener("click", async () => {
    const payload = {
      as_of_date: document.getElementById("as_of_date").value,
      description: document.getElementById("description").value,
      items: collectLines()
    };
    const { ok, data } = await json(cfg.urls.create, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(payload)
    });
    if (!ok) return notify("error", data.message || "Opening stock was not posted.");
    notify("success", `Opening stock ${data.document_number} posted.`);
    lines.innerHTML = "";
    addLine();
    await Promise.all([loadDocuments(), loadStatus()]);
  });
  document.getElementById("reclass-btn")?.addEventListener("click", async () => {
    const { ok, data } = await json(cfg.urls.reclassify, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: "{}"
    });
    if (!ok) return notify("error", data.message || "Reclassification failed.");
    notify("success", data.status === "noop" ? "Opening Balance is already zero." : "Opening Balance moved to Capital.");
    await loadStatus();
  });

  Promise.all([
    json(cfg.urls.catalog),
    json(cfg.urls.warehouses)
  ]).then(([itemResult, warehouseResult]) => {
    catalog = itemResult.data.items || [];
    warehouses = warehouseResult.data.warehouses || [];
    addLine();
  });
  loadDocuments();
  loadStatus();
})();
