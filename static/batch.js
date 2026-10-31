const form = document.getElementById("batch-form");
const fileInput = document.getElementById("csv-file");
const submitBtn = document.getElementById("batch-submit-btn");
const progressEl = document.getElementById("batch-progress");
const errorEl = document.getElementById("batch-error");
const successEl = document.getElementById("batch-success");
const summaryEl = document.getElementById("batch-summary");

function decodeSummaryHeader(header) {
  try {
    return JSON.parse(atob(header));
  } catch (e) {
    return null;
  }
}

function renderSummary(summary) {
  if (!summary) return;
  summaryEl.innerHTML = `
    <strong>Batch Analysis Complete</strong><br/>
    Total Rows: ${summary.total_rows}<br/>
    Processed: ${summary.processed}<br/>
    Cache Hits: ${summary.cache_hits}<br/>
    LLM Calls: ${summary.llm_calls}<br/>
    Needs Human Review: ${summary.needs_human_review}<br/>
    Skipped (too short): ${summary.skipped}<br/>
    Errors: ${summary.errors}
  `;
  summaryEl.classList.remove("hidden");
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.classList.add("hidden");
  successEl.classList.add("hidden");
  summaryEl.classList.add("hidden");

  const file = fileInput.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  submitBtn.disabled = true;
  progressEl.classList.remove("hidden");

  const token = localStorage.getItem("access_token");
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  try {
    const res = await fetch("/predict/batch", {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Batch processing failed.");
    }

    const summaryHeader = res.headers.get("X-Batch-Summary");
    const summary = summaryHeader ? decodeSummaryHeader(summaryHeader) : null;

    const blob = await res.blob();
    const text = await blob.text();
    const rows = parseCSV(text);
    renderBatchTable(rows);

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "batch_results.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();

    successEl.textContent = "Done! Your results file has been downloaded and previewed below.";
    successEl.classList.remove("hidden");
    renderSummary(summary);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    progressEl.classList.add("hidden");
  }
});

function parseCSVLine(line) {
  const res = [];
  let inQuotes = false;
  let cur = "";
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (c === ',' && !inQuotes) {
      res.push(cur);
      cur = "";
    } else {
      cur += c;
    }
  }
  res.push(cur);
  return res;
}

function parseCSV(text) {
  const lines = text.trim().split("\n");
  if (lines.length <= 1) return [];
  const header = parseCSVLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length && i <= 100; i++) {
    if (!lines[i].trim()) continue;
    const values = parseCSVLine(lines[i]);
    const obj = {};
    header.forEach((h, idx) => {
      obj[h.trim()] = (values[idx] || "").trim();
    });
    rows.push(obj);
  }
  return rows;
}

function renderBatchTable(rows) {
  const wrap = document.getElementById("batch-results-wrap");
  const tbody = document.getElementById("batch-table-body");
  if (!wrap || !tbody || !rows.length) return;
  tbody.innerHTML = rows
    .map((r, idx) => {
      const isFake = (r.predicted_label || "").toLowerCase() === "fake";
      const rowClass = isFake ? "row-false" : "row-true";
      const indicatorClass = isFake ? "line-indicator-false" : "line-indicator-true";
      return `
      <tr class="${rowClass}">
        <td><span class="line-indicator ${indicatorClass}" title="${isFake ? 'False (Fake) - Red Line' : 'True (Genuine) - Green Line'}"></span>${idx + 1}</td>
        <td title="${escapeHtml(r.review_text || '')}">${escapeHtml(truncate(r.review_text || '', 60))}</td>
        <td>${r.rating || '—'}</td>
        <td><span class="badge ${isFake ? 'badge-fake' : 'badge-genuine'}">${r.predicted_label || '—'}</span></td>
        <td>${r.confidence ? r.confidence + '%' : '—'}</td>
        <td title="${escapeHtml(r.reasoning || '')}">${escapeHtml(truncate(r.reasoning || '', 60))}</td>
      </tr>`;
    })
    .join("");
  wrap.classList.remove("hidden");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, max = 60) {
  return str.length > max ? str.slice(0, max) + "…" : str;
}

