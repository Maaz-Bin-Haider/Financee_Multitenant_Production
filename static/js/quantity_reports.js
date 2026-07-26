(() => {
  "use strict";
  const shell = document.querySelector(".qr-shell");
  if (!shell) return;
  const form = document.getElementById("qr-filters");
  const status = document.getElementById("qr-status");
  const head = document.getElementById("qr-head");
  const body = document.getElementById("qr-body");
  const totals = document.getElementById("qr-totals");
  const exportLink = document.getElementById("qr-export");
  const excelLink = document.getElementById("qr-excel");
  let active = "";

  const url = (template, key) => {
    const params = new URLSearchParams(new FormData(form));
    [...params].forEach(([name, value]) => { if (!value) params.delete(name); });
    return `${template.replace("REPORT_KEY", key)}?${params}`;
  };
  const value = (input) => input === null || input === undefined ? "" : String(input);
  const render = (report) => {
    head.replaceChildren();
    body.replaceChildren();
    totals.replaceChildren();
    const row = document.createElement("tr");
    report.columns.forEach(column => {
      const th = document.createElement("th"); th.textContent = column.label; row.append(th);
    });
    head.append(row);
    report.rows.forEach(item => {
      const tr = document.createElement("tr");
      report.columns.forEach(column => {
        const td = document.createElement("td"); td.textContent = value(item[column.key]); tr.append(td);
      });
      body.append(tr);
    });
    Object.entries(report.totals || {}).forEach(([key, amount]) => {
      const card = document.createElement("div");
      card.innerHTML = `<span></span><strong></strong>`;
      card.querySelector("span").textContent = key.replaceAll("_", " ");
      card.querySelector("strong").textContent = value(amount);
      totals.append(card);
    });
    status.textContent = `${report.label}: ${report.rows.length} row(s)`;
  };
  const load = async (key) => {
    active = key; status.textContent = "Loading report…"; shell.setAttribute("aria-busy", "true");
    document.querySelectorAll("[data-report]").forEach(button =>
      button.classList.toggle("active", button.dataset.report === key));
    try {
      const response = await fetch(url(shell.dataset.apiTemplate, key), {headers: {"X-Requested-With": "XMLHttpRequest"}});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || "Report failed.");
      render(payload.data);
      exportLink.href = url(shell.dataset.exportTemplate, key);
      exportLink.setAttribute("aria-disabled", "false");
      excelLink.href = url(shell.dataset.excelTemplate, key);
      excelLink.setAttribute("aria-disabled", "false");
    } catch (error) { status.textContent = error.message; }
    finally { shell.removeAttribute("aria-busy"); }
  };
  document.querySelectorAll("[data-report]").forEach(button =>
    button.addEventListener("click", () => load(button.dataset.report)));
  form.addEventListener("submit", event => { event.preventDefault(); if (active) load(active); });
  const first = document.querySelector("[data-report]"); if (first) load(first.dataset.report);
})();
