/* ============================================================
   PROFIT REPORTS  —  JavaScript  (v4)
   • Compact filter form for sale-wise profit
   • Row colour coding (sale price / purchase price / profit-loss)
   • Vendor dropdown filter (populated from live table data)
   • Post-render table search/filter with row count
   • PDF: dark-blue header row + row highlight colours
   • CSV: row highlight label column + totals row
   ============================================================ */

let _rMeta = { title: "Profit Report", subtitle: "", filters: {} };

// ═══════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════
function getCSRFToken() {
  for (let c of decodeURIComponent(document.cookie).split(";")) {
    c = c.trim();
    if (c.startsWith("csrftoken=")) return c.slice("csrftoken=".length);
  }
  return "";
}

function showLoader(msg = "Loading…") {
  Swal.fire({ title: msg, didOpen: () => Swal.showLoading(), allowOutsideClick: false });
}

function fmt(date) {
  if (!date) return "—";
  return new Date(date).toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-PK", {
    style: "currency", currency: "PKR", currencyDisplay: "code", minimumFractionDigits: 2,
  }).format(value || 0);
}

// ═══════════════════════════════════════════
// REPORT SELECTOR
// ═══════════════════════════════════════════
function selectReport(type) {
  $(".report-btn").removeClass("active");
  $("#reportHeader").html("");
  $("#reportBody").html(`<tr><td class="no-data">Loading…</td></tr>`);
  $("#reportToolbar").remove();
  $("#report-form-container").html("");
  $("#saleRowLegend").remove();
  $("#vendorFilterBar").remove();
  _currentTotals = {}; _currentCols = []; _currentData = [];

  if (type === "sale") {
    $("#btn-sale").addClass("active");
    renderSaleProfitForm();
  } else {
    $("#btn-company").addClass("active");
    fetchCompanyValuation();
  }
}

// ═══════════════════════════════════════════
// FORM RENDERERS
// ═══════════════════════════════════════════
function renderSaleProfitForm() {
  const today = new Date().toISOString().split("T")[0];

  $("#report-form-container").html(`
    <div class="filter-form">
      <div class="filter-field">
        <label><i class="fa-regular fa-calendar"></i>&nbsp;From Date</label>
        <input type="date" id="from_date" value="2026-01-01">
      </div>
      <div class="filter-field">
        <label><i class="fa-regular fa-calendar"></i>&nbsp;To Date</label>
        <input type="date" id="to_date" value="${today}" max="${today}">
      </div>
      <button class="generate-btn" onclick="fetchSaleProfit()">
        <i class="fa-solid fa-bolt"></i> Generate
      </button>
    </div>
  `);
  $("#reportHeader").html("");
  $("#reportBody").html(`<tr><td class="no-data">Set a date range and click Generate</td></tr>`);
}

// ═══════════════════════════════════════════
// DATA FETCHERS
// ═══════════════════════════════════════════
function fetchSaleProfit() {
  const from = $("#from_date").val();
  const to   = $("#to_date").val();
  if (!from || !to) { Swal.fire("Missing Fields", "Please fill in both dates.", "warning"); return; }

  _rMeta = { title: "Sale-wise Profit", subtitle: "Profit & loss per sale transaction",
             filters: { From: fmt(from), To: fmt(to) } };
  showLoader("Fetching sale-wise profit…");

  fetch("/accountsReports/sale-wise-report/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
    body: JSON.stringify({ from_date: from, to_date: to })
  })
  .then(r => r.json())
  .then(data => { Swal.close(); data.error ? Swal.fire("Error", data.error, "error") : renderTable(data); })
  .catch(() => Swal.fire("Error", "Unable to fetch report data.", "error"));
}

function fetchCompanyValuation() {
  _rMeta = { title: "Company Valuation", subtitle: "Financial position and profit & loss summary", filters: {} };
  showLoader("Loading Company Valuation…");

  fetch("/accountsReports/company-valuation/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() }
  })
  .then(r => r.json())
  .then(data => { Swal.close(); data.error ? Swal.fire("Error", data.error, "error") : renderCompanyValuation(data); })
  .catch(() => Swal.fire("Error", "Unable to fetch company valuation.", "error"));
}

// ═══════════════════════════════════════════
// ROW COLOUR HELPER
// ═══════════════════════════════════════════

/**
 * Returns { cls, label } for a sale-wise profit row.
 * Priority:
 *   1. sale_price    <= 4  -> row-low-sale     (light blue)
 *   2. purchase_price <= 4 -> row-low-purchase (light yellow)
 *   3. profit_loss   <  0  -> row-loss         (light red)
 *   4. none                -> cls="", label=""
 */
function getSaleRowMeta(row) {
  const norm = k => k.toLowerCase().replace(/[\s-]+/g, "_");
  const keys  = Object.keys(row);
  const find  = patterns => {
    for (const k of keys) if (patterns.some(p => norm(k).includes(p))) return k;
    return null;
  };

  const saleKey     = find(["sale_price", "saleprice", "selling_price"]);
  const purchaseKey = find(["purchase_price", "purchaseprice", "cost_price", "buying_price"]);
  const plKey       = find(["profit_loss", "profitloss", "profit", "net_profit", "p_l", "pl"]);

  const toNum = v => parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, "")) || 0;

  if (saleKey     !== null && toNum(row[saleKey])     <= 4) return { cls: "row-low-sale",     label: "Low Sale Price"     };
  if (purchaseKey !== null && toNum(row[purchaseKey]) <= 4) return { cls: "row-low-purchase", label: "Low Purchase Price" };
  if (plKey       !== null && toNum(row[plKey])       <  0) return { cls: "row-loss",         label: "Loss"               };
  return { cls: "", label: "" };
}

// ═══════════════════════════════════════════
// VENDOR COLUMN DETECTOR
// ═══════════════════════════════════════════
function findVendorKey(cols) {
  const patterns = ["vendor", "party", "supplier", "customer", "buyer", "seller", "client", "name"];
  const norm = k => k.toLowerCase().replace(/[\s_-]+/g, "");
  for (const p of patterns)
    for (const c of cols)
      if (norm(c).includes(p)) return c;
  return null;
}

// ═══════════════════════════════════════════
// TABLE STATE
// ═══════════════════════════════════════════
let _currentTotals  = {};
let _currentCols    = [];
let _currentData    = [];
let _vendorKey      = null;   // column name used as "vendor"
let _activeVendor   = "";     // currently selected vendor filter
let _activeSearch   = "";     // current text-search value

// ═══════════════════════════════════════════
// APPLY FILTERS  (vendor + text search)
// ═══════════════════════════════════════════
function applyFilters() {
  const vendor = _activeVendor.toLowerCase();
  const q      = _activeSearch.toLowerCase().trim();
  let vis = 0;

  $("#reportBody tr:not(.row-totals)").each(function () {
    const text = $(this).text().toLowerCase();

    // vendor filter: match against the vendor cell specifically if we know the column
    let vendorOk = true;
    if (vendor && _vendorKey !== null) {
      const colIdx = _currentCols.indexOf(_vendorKey);
      if (colIdx >= 0) {
        const cellText = $(this).find("td").eq(colIdx).text().toLowerCase();
        vendorOk = cellText === vendor;
      }
    }

    const searchOk = !q || text.includes(q);
    const show     = vendorOk && searchOk;
    $(this).toggleClass("filtered-out", !show);
    if (show) vis++;
  });

  // always show totals row
  $("#reportBody tr.row-totals").removeClass("filtered-out");
  $("#rowCount").text(`${vis} row${vis !== 1 ? "s" : ""}`);
}

// ═══════════════════════════════════════════
// VENDOR FILTER BAR
// ═══════════════════════════════════════════
function injectVendorFilter(data, vendorKey) {
  $("#vendorFilterBar").remove();
  if (!vendorKey) return;

  // Collect unique vendor names
  const vendors = [...new Set(data.map(r => String(r[vendorKey] ?? "").trim()).filter(Boolean))].sort();

  const opts = vendors.map(v => `<option value="${v}">${v}</option>`).join("");

  const bar = `
    <div id="vendorFilterBar" class="vendor-filter-bar">
      <i class="fa-solid fa-filter vendor-filter-icon"></i>
      <label for="vendorSelect" class="vendor-filter-label">Filter by Vendor</label>
      <select id="vendorSelect" class="vendor-filter-select">
        <option value="">— All Vendors —</option>
        ${opts}
      </select>
      <button id="vendorClearBtn" class="vendor-clear-btn" title="Clear vendor filter">
        <i class="fa-solid fa-xmark"></i>
      </button>
      <span class="vendor-count-badge" id="vendorCountBadge">${vendors.length} vendor${vendors.length !== 1 ? "s" : ""}</span>
    </div>`;

  // Insert right before the legend (which is before table-container)
  $("#saleRowLegend").before(bar);

  $("#vendorSelect").on("change", function () {
    _activeVendor = this.value;
    applyFilters();
  });

  $("#vendorClearBtn").on("click", function () {
    _activeVendor = "";
    $("#vendorSelect").val("");
    applyFilters();
  });
}

// ═══════════════════════════════════════════
// TABLE RENDERER
// ═══════════════════════════════════════════
function renderTable(data) {
  const $header = $("#reportHeader");
  const $body   = $("#reportBody");

  if (!data || !data.length) {
    $header.html("");
    $body.html(`<tr><td class="no-data">No records found</td></tr>`);
    injectToolbar(0);
    _currentTotals = {}; _currentCols = []; _currentData = [];
    _vendorKey = null; _activeVendor = ""; _activeSearch = "";
    return;
  }

  _currentCols = Object.keys(data[0]);
  _currentData = data;
  _vendorKey   = findVendorKey(_currentCols);
  _activeVendor = "";
  _activeSearch = "";

  // Detect numeric columns and compute totals
  const isNumericCol = {};
  _currentCols.forEach(c => {
    isNumericCol[c] = data.every(row => {
      const v = row[c];
      return v === null || v === "" || v === undefined || !isNaN(parseFloat(String(v)));
    }) && data.some(row => !isNaN(parseFloat(String(row[c] ?? ""))));
  });

  const totals = {};
  _currentCols.forEach(c => {
    if (isNumericCol[c])
      totals[c] = data.reduce((s, row) => s + (parseFloat(String(row[c] ?? "")) || 0), 0);
  });
  _currentTotals = totals;

  // Header
  $header.html(`<tr>${_currentCols.map(c => `<th>${c.replace(/_/g, " ")}</th>`).join("")}</tr>`);

  // Data rows with colour coding
  const rowsHtml = data.map(row => {
    const { cls } = getSaleRowMeta(row);
    const cells   = _currentCols.map(c => `<td>${row[c] ?? ""}</td>`).join("");
    return `<tr${cls ? ` class="${cls}"` : ""}>${cells}</tr>`;
  }).join("");

  // Totals row
  const totalsHtml = `<tr class="row-totals">` +
    _currentCols.map((c, i) => {
      if (i === 0) return `<td>TOTAL</td>`;
      if (totals[c] !== undefined) {
        const v = Math.round(totals[c] * 100) / 100;
        return `<td>${v.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>`;
      }
      return `<td></td>`;
    }).join("") + `</tr>`;

  $body.html(rowsHtml + totalsHtml);

  // Legend
  $("#saleRowLegend").remove();
  $(".table-container").before(`
    <div id="saleRowLegend" class="row-colour-legend">
      <strong style="margin-right:4px;">Legend:</strong>
      <span class="legend-item"><span class="swatch swatch-blue"></span> Sale price &le; 4</span>
      <span class="legend-item"><span class="swatch swatch-yellow"></span> Purchase price &le; 4</span>
      <span class="legend-item"><span class="swatch swatch-red"></span> Profit / loss &lt; 0</span>
    </div>`);

  // Vendor filter bar (above the legend)
  injectVendorFilter(data, _vendorKey);

  injectToolbar(data.length);
}

// ── Company Valuation — special rich layout ──────────────────
function renderCompanyValuation(data) {
  const { financial_position: fp, profit_and_loss: pl } = data;

  if (!fp || !pl) {
    $("#reportHeader").html("");
    $("#reportBody").html(`<tr><td class="no-data">Incomplete valuation data</td></tr>`);
    return;
  }

  const netProfit   = pl.net_profit_loss || 0;
  const isProfit    = netProfit >= 0;
  const profitColor = isProfit ? "var(--brand-success)" : "var(--brand-danger)";
  const profitLabel = isProfit ? "Net Profit" : "Net Loss";

  const html = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;padding:0.25rem;">
      <div class="valuation-section">
        <h3><i class="fa-solid fa-scale-balanced"></i> Financial Position</h3>
        <table class="valuation-table">
          <tr><th>Total Assets</th><td>${formatCurrency(fp.total_assets)}</td></tr>
          <tr><th>Total Liabilities</th><td style="color:var(--brand-danger)">${formatCurrency(fp.total_liabilities)}</td></tr>
          <tr><th>Total Equity</th><td>${formatCurrency(fp.total_equity)}</td></tr>
          <tr class="highlight"><th>Net Worth</th><td>${formatCurrency(fp.net_worth)}</td></tr>
        </table>
      </div>
      <div class="valuation-section">
        <h3><i class="fa-solid fa-chart-line"></i> Profit &amp; Loss</h3>
        <table class="valuation-table">
          <tr><th>Total Revenue</th><td style="color:var(--brand-success)">${formatCurrency(pl.total_revenue)}</td></tr>
          <tr><th>Total Expenses</th><td style="color:var(--brand-danger)">${formatCurrency(pl.total_expenses)}</td></tr>
          <tr class="highlight"><th>${profitLabel}</th>
              <td style="color:${profitColor};font-size:1.05rem;">${formatCurrency(netProfit)}</td></tr>
        </table>
      </div>
    </div>`;

  $("#reportHeader").html("");
  $("#reportBody").html(`<tr><td colspan="100%" style="padding:0;">${html}</td></tr>`);
}

// ═══════════════════════════════════════════
// TOOLBAR
// ═══════════════════════════════════════════
function injectToolbar(total) {
  $("#reportToolbar").remove();

  $(`<div id="reportToolbar" class="report-toolbar">
      <div class="table-filter-bar">
        <div class="table-search-wrap">
          <i class="fa-solid fa-magnifying-glass"></i>
          <input type="text" id="tableSearch" placeholder="Filter results…" autocomplete="off">
        </div>
        <span class="table-row-count" id="rowCount">${total} row${total !== 1 ? "s" : ""}</span>
      </div>
      <div class="table-actions">
        <button id="download_pdf" class="btn-download">
          <i class="fa-solid fa-file-pdf"></i> PDF
        </button>
        <button id="download_csv" class="btn-download btn-csv">
          <i class="fa-solid fa-file-csv"></i> CSV
        </button>
      </div>
    </div>`).insertBefore(".table-container");

  $("#tableSearch").on("input", function () {
    _activeSearch = this.value;
    applyFilters();
  });
}

// ═══════════════════════════════════════════
// PDF  —  dark-blue header row + row colours
// ═══════════════════════════════════════════
$(document).on("click", "#download_pdf", function () {
  const { jsPDF } = window.jspdf;

  const colHeaders = [...document.querySelectorAll("#reportTable thead th")].map(th => th.textContent.trim());

  // Collect visible data rows (exclude totals row — rebuilt separately)
  const rowData    = [];
  const rowClasses = [];
  document.querySelectorAll("#reportBody tr:not(.filtered-out):not(.row-totals)").forEach(tr => {
    const cells = [...tr.querySelectorAll("td")].map(td => td.textContent.trim());
    if (cells.length && !cells[0].includes("No records") && !cells[0].includes("valuation-section")) {
      rowData.push(cells);
      if      (tr.classList.contains("row-low-sale"))     rowClasses.push("sale");
      else if (tr.classList.contains("row-low-purchase")) rowClasses.push("purchase");
      else if (tr.classList.contains("row-loss"))         rowClasses.push("loss");
      else                                                rowClasses.push("");
    }
  });

  if (!rowData.length || !colHeaders.length) {
    Swal.fire("No Data", "Nothing visible to export as PDF.\nFor Company Valuation, use the browser print function.", "info");
    return;
  }

  // Totals row
  const totalsRow = _currentCols.map((c, i) => {
    if (i === 0) return "TOTAL";
    if (_currentTotals[c] !== undefined) {
      const v = Math.round(_currentTotals[c] * 100) / 100;
      return v.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return "";
  });

  const doc   = new jsPDF("l", "pt", "a4");
  const pW    = doc.internal.pageSize.width;
  const pH    = doc.internal.pageSize.height;
  const today = new Date().toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
  const m     = _rMeta;
  const fStr  = Object.entries(m.filters || {}).map(([k, v]) => `${k}: ${v}`).join("   ·   ");

  function drawHeader(pg, total) {
    // Amber brand bar at top
    doc.setFillColor(180, 83, 9);
    doc.rect(0, 0, pW, 38, "F");
    doc.setFont("helvetica", "bold"); doc.setFontSize(13); doc.setTextColor(255, 255, 255);
    doc.text("Financee", 36, 25);
    doc.setFont("helvetica", "normal"); doc.setFontSize(10);
    doc.text(m.title, pW - 36, 25, { align: "right" });

    doc.setFillColor(255, 251, 235);
    doc.rect(0, 38, pW, 26, "F");
    doc.setFont("helvetica", "italic"); doc.setFontSize(8); doc.setTextColor(71, 85, 105);
    let sub = m.subtitle || "";
    if (fStr) sub += (sub ? "   ·   " : "") + fStr;
    doc.text(sub, 36, 55);
    doc.setFont("helvetica", "normal");
    doc.text(`Generated: ${today}   Page ${pg} of ${total}`, pW - 36, 55, { align: "right" });
    doc.setDrawColor(203, 213, 225); doc.setLineWidth(0.5); doc.line(0, 64, pW, 64);
  }

  function drawFooter(pg, total) {
    const y = pH - 18;
    doc.setDrawColor(226, 232, 240); doc.setLineWidth(0.4); doc.line(36, y - 7, pW - 36, y - 7);
    doc.setFont("helvetica", "normal"); doc.setFontSize(7.5); doc.setTextColor(148, 163, 184);
    doc.text("Financee  —  Confidential", 36, y + 2);
    doc.text(`Page ${pg} of ${total}`, pW - 36, y + 2, { align: "right" });
  }

  // Row highlight colours  [R, G, B]
  const BG = { sale: [219, 234, 254], purchase: [254, 249, 195], loss: [254, 226, 226], "": null };

  doc.autoTable({
    head:             [colHeaders],
    body:             [...rowData, totalsRow],
    startY:           72,
    margin:           { left: 28, right: 28, top: 72, bottom: 32 },
    theme:            "grid",
    // ── DARK BLUE header row ──
    headStyles:       { fillColor: [15, 30, 80], textColor: [255, 255, 255], fontStyle: "bold", fontSize: 7.5, cellPadding: 5 },
    bodyStyles:       { fontSize: 7.5, textColor: [30, 41, 59], cellPadding: 4, lineColor: [226, 232, 240] },
    alternateRowStyles: {},   // disable auto-alternate so our colours dominate
    didParseCell: function (hookData) {
      const ri = hookData.row.index;
      // Totals row (last row in body)
      if (hookData.section === "body" && ri === rowData.length) {
        hookData.cell.styles.fillColor = [241, 245, 249];
        hookData.cell.styles.fontStyle = "bold";
        hookData.cell.styles.lineColor = [100, 116, 139];
        return;
      }
      // Colour-coded data rows
      if (hookData.section === "body") {
        const bg = BG[rowClasses[ri] || ""];
        if (bg) hookData.cell.styles.fillColor = bg;
      }
    },
    didDrawPage: d => drawHeader(d.pageNumber, "…"),
  });

  const totalPg = doc.internal.getNumberOfPages();
  for (let i = 1; i <= totalPg; i++) { doc.setPage(i); drawHeader(i, totalPg); drawFooter(i, totalPg); }

  doc.save(`${m.title.replace(/\s+/g, "_")}_${new Date().toISOString().split("T")[0]}.pdf`);
});

// ═══════════════════════════════════════════
// CSV  —  extra "Row Highlight" column
// ═══════════════════════════════════════════
$(document).on("click", "#download_csv", function () {
  const tbl = document.getElementById("reportTable");
  if (!tbl) { Swal.fire("No Data", "Nothing to export.", "warning"); return; }

  const m    = _rMeta;
  const rows = [];
  rows.push([`${m.title} Report`]);
  Object.entries(m.filters || {}).forEach(([k, v]) => rows.push([`${k}: ${v}`]));
  rows.push([`Generated: ${new Date().toLocaleString()}`]);
  rows.push([]);

  // Header row: original columns + "Row Highlight" at the end
  const headerCells = [...tbl.querySelectorAll("thead th")].map(th => th.textContent.trim());
  rows.push([...headerCells, "Row Highlight"]);

  // Data rows: append highlight label to each
  tbl.querySelectorAll("tbody tr:not(.filtered-out):not(.row-totals)").forEach(tr => {
    const cells = [...tr.querySelectorAll("td")].map(td => {
      let v = td.textContent.trim();
      if (/[,"\n]/.test(v)) v = `"${v.replace(/"/g, '""')}"`;
      return v;
    });
    if (!cells.length || cells[0].includes("No records")) return;

    // Determine highlight label from class
    let highlight = "";
    if      (tr.classList.contains("row-low-sale"))     highlight = "Low Sale Price";
    else if (tr.classList.contains("row-low-purchase")) highlight = "Low Purchase Price";
    else if (tr.classList.contains("row-loss"))         highlight = "Loss";

    rows.push([...cells, highlight]);
  });

  // Totals row — blank for the highlight column
  if (_currentCols.length) {
    const totalsRow = _currentCols.map((c, i) => {
      if (i === 0) return "TOTAL";
      if (_currentTotals[c] !== undefined) {
        const v = Math.round(_currentTotals[c] * 100) / 100;
        return v.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      }
      return "";
    });
    rows.push([]);
    rows.push([...totalsRow, ""]);
  }

  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(new Blob([rows.map(r => r.join(",")).join("\n")], { type: "text/csv;charset=utf-8;" })),
    download: `${m.title.replace(/\s+/g,"_")}_${new Date().toISOString().split("T")[0]}.csv`,
    style: "display:none",
  });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
});

// ═══════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════
$(document).ready(() => selectReport("company"));
