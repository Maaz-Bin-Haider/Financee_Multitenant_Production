(function () {
  "use strict";
  const cfg = window.QWAREHOUSE;
  const csrf = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const escape = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const urlFor = (template, id) => template.replace("/0/", `/${id}/`);
  async function request(url, options) {
    const response = await fetch(url, options);
    return { ok: response.ok, data: await response.json().catch(() => ({})) };
  }
  function reset() {
    ["warehouse-id", "warehouse-code", "warehouse-name", "warehouse-address"].forEach(id => document.getElementById(id).value = "");
    document.getElementById("warehouse-default").checked = false;
    document.getElementById("warehouse-active").checked = true;
  }
  function select(row) {
    document.getElementById("warehouse-id").value = row.dataset.id;
    document.getElementById("warehouse-code").value = row.dataset.code;
    document.getElementById("warehouse-name").value = row.dataset.name;
    document.getElementById("warehouse-address").value = row.dataset.address;
    document.getElementById("warehouse-default").checked = row.dataset.default === "true";
    document.getElementById("warehouse-active").checked = row.dataset.active === "true";
  }
  async function load() {
    const { ok, data } = await request(`${cfg.urls.list}?active=false`);
    const body = document.getElementById("warehouse-list");
    body.innerHTML = ok ? (data.warehouses || []).map(w =>
      `<tr tabindex="0" data-id="${w.warehouse_id}" data-code="${escape(w.warehouse_code)}" data-name="${escape(w.warehouse_name)}" data-address="${escape(w.address || "")}" data-default="${w.is_default}" data-active="${w.is_active}"><td>${escape(w.warehouse_code)}</td><td>${escape(w.warehouse_name)}</td><td>${escape(w.address || "")}</td><td>${w.is_default ? "Yes" : "No"}</td><td>${w.is_active ? "Active" : "Inactive"}</td></tr>`
    ).join("") : "";
    body.querySelectorAll("tr").forEach(row => {
      row.onclick = () => select(row);
      row.onkeydown = event => { if (event.key === "Enter") select(row); };
    });
  }
  document.getElementById("new").onclick = reset;
  document.getElementById("refresh").onclick = load;
  document.getElementById("save")?.addEventListener("click", event => QuantityUI.run(event.currentTarget, async () => {
    const id = document.getElementById("warehouse-id").value;
    const payload = {
      warehouse_code: document.getElementById("warehouse-code").value,
      warehouse_name: document.getElementById("warehouse-name").value,
      address: document.getElementById("warehouse-address").value,
      is_default: document.getElementById("warehouse-default").checked,
      is_active: document.getElementById("warehouse-active").checked
    };
    const { ok, data } = await request(id ? urlFor(cfg.urls.update, id) : cfg.urls.create, {
      method: "POST", headers: {"Content-Type":"application/json","X-CSRFToken":csrf()}, body: JSON.stringify(payload)
    });
    if (!ok) return QuantityUI.notify("error", data.message || "Warehouse save failed.");
    document.getElementById("warehouse-id").value = data.warehouse_id;
    QuantityUI.notify("success", "Warehouse saved."); await load();
  }));
  document.getElementById("delete")?.addEventListener("click", event => QuantityUI.run(event.currentTarget, async () => {
    const id = document.getElementById("warehouse-id").value;
    if (!id) return QuantityUI.notify("warning", "Select a warehouse.");
    const { ok, data } = await request(urlFor(cfg.urls.remove, id), {
      method: "DELETE", headers: {"X-CSRFToken":csrf()}
    });
    if (!ok) return QuantityUI.notify("error", data.message || "Warehouse deletion failed.");
    reset(); QuantityUI.notify("success", "Warehouse deleted."); await load();
  }));
  load();
})();
