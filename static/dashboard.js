function authHeaders() {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function isLoggedIn() {
  return !!localStorage.getItem("access_token");
}

function showLoginRequired() {
  const main = document.querySelector("main");
  main.innerHTML = `
    <div class="result">
      <h2>Log in to view your dashboard</h2>
      <p>Your prediction history, analytics, and exports are private to your
      account. <a href="/login">Log in or sign up</a> to view them.</p>
    </div>
  `;
}

async function loadStats() {
  try {
    const res = await fetch("/stats", { headers: authHeaders() });
    if (res.status === 401) return; // handled by the guard at the bottom of this file
    const data = await res.json();
    document.getElementById("stat-total").textContent = data.total;
    document.getElementById("stat-fake").textContent = data.fake_count;
    document.getElementById("stat-fake-pct").textContent = data.fake_percentage;
    document.getElementById("stat-genuine").textContent = data.genuine_count;
    document.getElementById("stat-genuine-pct").textContent = data.genuine_percentage;
    document.getElementById("stat-confidence").textContent = data.avg_confidence + "%";
    document.getElementById("stat-human-review").textContent = data.needs_human_review_count;
    document.getElementById("stat-cache-hits").textContent = data.cache_hits;
    document.getElementById("stat-llm-calls").textContent = data.llm_calls;
  } catch (err) {
    console.error("Failed to load stats", err);
  }
}

async function loadConfidenceDistribution() {
  try {
    const res = await fetch("/stats/confidence-distribution", { headers: authHeaders() });
    if (res.status === 401) return;
    const data = await res.json();
    document.getElementById("dist-high").textContent = data.HIGH;
    document.getElementById("dist-medium").textContent = data.MEDIUM;
    document.getElementById("dist-low").textContent = data.LOW;
  } catch (err) {
    console.error("Failed to load confidence distribution", err);
  }
}

let trendChart = null;

async function loadTrend() {
  try {
    const res = await fetch("/stats/trend?days=14", { headers: authHeaders() });
    if (res.status === 401) return;
    const rows = await res.json();

    const labels = rows.map((r) => r.day);
    const fakeData = rows.map((r) => r.fake_count);
    const genuineData = rows.map((r) => r.genuine_count);

    const ctx = document.getElementById("trend-chart").getContext("2d");
    if (trendChart) trendChart.destroy();

    trendChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Fake (False)",
            data: fakeData,
            borderColor: "#ef4444",
            backgroundColor: "rgba(239,68,68,0.12)",
            tension: 0.3,
            fill: true,
            borderWidth: 3,
            pointBackgroundColor: "#ef4444",
          },
          {
            label: "Genuine (True)",
            data: genuineData,
            borderColor: "#10b981",
            backgroundColor: "rgba(16,185,129,0.12)",
            tension: 0.3,
            fill: true,
            borderWidth: 3,
            pointBackgroundColor: "#10b981",
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { position: "top" } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  } catch (err) {
    console.error("Failed to load trend", err);
  }
}

function truncate(text, max = 80) {
  return text.length > max ? text.slice(0, max) + "…" : text;
}

async function loadHistory() {
  const tbody = document.getElementById("history-body");
  try {
    const res = await fetch("/history?limit=50", { headers: authHeaders() });
    if (res.status === 401) return;
    const rows = await res.json();

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7">No predictions yet.</td></tr>';
      return;
    }

    tbody.innerHTML = rows
      .map((r) => {
        const isFake = r.predicted_label === "Fake";
        const rowClass = isFake ? "row-false" : "row-true";
        const indicatorClass = isFake ? "line-indicator-false" : "line-indicator-true";
        return `
        <tr data-id="${r.id}" class="${rowClass}">
          <td><span class="line-indicator ${indicatorClass}" title="${isFake ? 'False (Fake) - Red Line' : 'True (Genuine) - Green Line'}"></span>${r.id}</td>
          <td title="${escapeHtml(r.review_text)}">${escapeHtml(truncate(r.review_text))}</td>
          <td>${r.rating ?? "—"}</td>
          <td><span class="badge ${isFake ? "badge-fake" : "badge-genuine"}">${r.predicted_label}</span></td>
          <td>${r.confidence}% ${r.needs_human_review ? '<span title="Needs human review">⚠️</span>' : ""}</td>
          <td>${new Date(r.created_at).toLocaleString()}</td>
          <td><button class="delete-btn" data-id="${r.id}">Delete</button></td>
        </tr>`;
      })
      .join("");

    document.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteReview(btn.dataset.id));
    });
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="7">Failed to load history.</td></tr>';
    console.error(err);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function deleteReview(id) {
  if (!confirm(`Delete review #${id}?`)) return;
  try {
    const res = await fetch(`/reviews/${id}`, { method: "DELETE", headers: authHeaders() });
    if (!res.ok) throw new Error("Delete failed");
    await Promise.all([loadHistory(), loadStats(), loadTrend()]);
  } catch (err) {
    alert("Could not delete this review. Please try again.");
  }
}

async function downloadExport(endpoint, filename) {
  try {
    const res = await fetch(endpoint, { headers: authHeaders() });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Export failed.");
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (err) {
    alert(err.message);
  }
}

document.getElementById("export-excel-btn").addEventListener("click", () => {
  downloadExport("/export/excel?limit=200", "review_history.xlsx");
});

document.getElementById("export-pdf-btn").addEventListener("click", () => {
  downloadExport("/export/pdf?limit=200", "review_history.pdf");
});

// Dashboard is now a private, auth-required area (security fix — guests
// previously fell through to unfiltered/global data on these endpoints).
if (!isLoggedIn()) {
  showLoginRequired();
} else {
  loadStats();
  loadConfidenceDistribution();
  loadTrend();
  loadHistory();
}
