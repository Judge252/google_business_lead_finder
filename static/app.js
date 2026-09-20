const state = {
  leads: [],
  query: "",
};

const els = {
  form: document.getElementById("searchForm"),
  service: document.getElementById("service"),
  location: document.getElementById("location"),
  maxResults: document.getElementById("maxResults"),
  enrich: document.getElementById("enrich"),
  button: document.getElementById("searchButton"),
  apiStatus: document.getElementById("apiStatus"),
  progress: document.getElementById("progressPanel"),
  progressTitle: document.getElementById("progressTitle"),
  progressText: document.getElementById("progressText"),
  error: document.getElementById("errorPanel"),
  section: document.getElementById("resultsSection"),
  body: document.getElementById("resultsBody"),
  filter: document.getElementById("filterInput"),
  scoreFilter: document.getElementById("scoreFilter"),
  contactOnly: document.getElementById("contactOnly"),
  exportButton: document.getElementById("exportButton"),
  emptyFilter: document.getElementById("emptyFilter"),
  statLeads: document.getElementById("statLeads"),
  statPhones: document.getElementById("statPhones"),
  statEmails: document.getElementById("statEmails"),
  statWhatsApp: document.getElementById("statWhatsApp"),
  statScore: document.getElementById("statScore"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeLink(url) {
  try {
    const u = new URL(url);
    return ["http:", "https:"].includes(u.protocol) ? u.href : "#";
  } catch {
    return "#";
  }
}

function first(list) {
  return Array.isArray(list) && list.length ? list[0] : "";
}

function contactable(lead) {
  return Boolean(
    lead.phone ||
    (lead.emails || []).length ||
    (lead.whatsapp || []).length ||
    (lead.website_phones || []).length
  );
}

function displayStats() {
  const leads = state.leads;
  els.statLeads.textContent = leads.length;
  els.statPhones.textContent = leads.filter(x => x.phone || (x.website_phones || []).length).length;
  els.statEmails.textContent = leads.filter(x => (x.emails || []).length).length;
  els.statWhatsApp.textContent = leads.filter(x => (x.whatsapp || []).length).length;
  const avg = leads.length
    ? Math.round(leads.reduce((sum, x) => sum + (x.lead_score || 0), 0) / leads.length)
    : 0;
  els.statScore.textContent = avg;
}

function filteredLeads() {
  const q = els.filter.value.trim().toLowerCase();
  const minScore = Number(els.scoreFilter.value || 0);
  const onlyContactable = els.contactOnly.checked;

  return state.leads.filter(lead => {
    const haystack = [
      lead.business_name,
      lead.category,
      lead.address,
      lead.phone,
      lead.website,
      ...(lead.emails || []),
    ].join(" ").toLowerCase();

    if (q && !haystack.includes(q)) return false;
    if ((lead.lead_score || 0) < minScore) return false;
    if (onlyContactable && !contactable(lead)) return false;
    return true;
  });
}

function scoreClass(score) {
  if (score >= 75) return "high";
  if (score >= 50) return "mid";
  return "";
}

function tags(values, cls = "") {
  if (!Array.isArray(values) || !values.length) return "";
  return values.slice(0, 3).map(v => `<span class="tag ${cls}" title="${escapeHtml(v)}">${escapeHtml(v)}</span>`).join("");
}

function render() {
  const leads = filteredLeads();
  els.body.innerHTML = "";

  els.emptyFilter.classList.toggle("hidden", leads.length > 0);
  document.querySelector(".table-wrap").classList.toggle("hidden", leads.length === 0);

  for (const lead of leads) {
    const tr = document.createElement("tr");
    const rating = lead.rating ? `${Number(lead.rating).toFixed(1)} ★` : "—";
    const reviews = lead.review_count ? `${Number(lead.review_count).toLocaleString()} reviews` : "No review count";

    const siteUrl = safeLink(lead.website);
    const mapsUrl = safeLink(lead.google_maps_url);

    const socialLinks = [
      ["Instagram", first(lead.instagram)],
      ["Facebook", first(lead.facebook)],
      ["LinkedIn", first(lead.linkedin)],
    ].filter(x => x[1]);

    tr.innerHTML = `
      <td><div class="score ${scoreClass(lead.lead_score || 0)}">${lead.lead_score || 0}</div></td>
      <td>
        <div class="biz-name">${escapeHtml(lead.business_name || "Unnamed business")}</div>
        <div class="subtle">${escapeHtml(lead.category || "Business")}</div>
        <div class="subtle">${escapeHtml(lead.address || "")}</div>
      </td>
      <td>
        <div class="contact-line">${escapeHtml(lead.phone || "No Google phone")}</div>
        ${lead.website_phones?.length ? `<div class="tag-row">${tags(lead.website_phones)}</div>` : ""}
      </td>
      <td>
        <div class="tag-row">
          ${tags(lead.emails, "good")}
          ${lead.whatsapp?.length ? `<span class="tag good">WhatsApp found</span>` : ""}
          ${!lead.emails?.length && !lead.whatsapp?.length ? `<span class="subtle">No extra public contacts found</span>` : ""}
        </div>
      </td>
      <td>
        <div class="rating">${rating}</div>
        <div class="subtle">${escapeHtml(reviews)}</div>
      </td>
      <td>
        <div class="links">
          ${siteUrl !== "#" ? `<a href="${escapeHtml(siteUrl)}" target="_blank" rel="noopener noreferrer">Website</a>` : ""}
          ${mapsUrl !== "#" ? `<a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noopener noreferrer">Maps</a>` : ""}
          ${lead.whatsapp?.length ? `<a href="${escapeHtml(safeLink(first(lead.whatsapp)))}" target="_blank" rel="noopener noreferrer">WhatsApp</a>` : ""}
          ${socialLinks.map(([name, url]) => `<a href="${escapeHtml(safeLink(url))}" target="_blank" rel="noopener noreferrer">${name}</a>`).join("")}
        </div>
      </td>
    `;
    els.body.appendChild(tr);
  }
}

function setLoading(isLoading, enrich) {
  els.button.disabled = isLoading;
  els.progress.classList.toggle("hidden", !isLoading);
  if (isLoading) {
    els.progressTitle.textContent = enrich ? "Finding and enriching businesses…" : "Finding businesses…";
    els.progressText.textContent = enrich
      ? "This may take longer because public business websites are checked after Google Places returns."
      : "Google Places is returning matching businesses.";
  }
}

function showError(message) {
  els.error.textContent = message;
  els.error.classList.remove("hidden");
}
function clearError() {
  els.error.classList.add("hidden");
  els.error.textContent = "";
}

async function healthCheck() {
  try {
    const r = await fetch("/api/health");
    const data = await r.json();
    if (data.google_key_configured) {
      els.apiStatus.textContent = "Places API ready";
      els.apiStatus.className = "status-pill good";
    } else {
      els.apiStatus.textContent = "API key needed";
      els.apiStatus.className = "status-pill bad";
    }
  } catch {
    els.apiStatus.textContent = "Server unavailable";
    els.apiStatus.className = "status-pill bad";
  }
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();

  const payload = {
    service: els.service.value.trim(),
    location: els.location.value.trim(),
    max_results: Number(els.maxResults.value),
    enrich_websites: els.enrich.checked,
  };

  if (!payload.service || !payload.location) return;

  setLoading(true, payload.enrich_websites);
  els.section.classList.add("hidden");

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail, null, 2);
      throw new Error(detail || `Request failed (${response.status})`);
    }

    state.leads = data.leads || [];
    state.query = data.query || "";
    displayStats();
    render();
    els.section.classList.remove("hidden");
  } catch (err) {
    showError(err.message || "Search failed.");
  } finally {
    setLoading(false, payload.enrich_websites);
  }
});

[els.filter, els.scoreFilter, els.contactOnly].forEach(el => {
  el.addEventListener("input", render);
  el.addEventListener("change", render);
});

function csvEscape(value) {
  const text = Array.isArray(value) ? value.join(" | ") : String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

els.exportButton.addEventListener("click", () => {
  const rows = filteredLeads();
  if (!rows.length) return;

  const columns = [
    ["lead_score", "Lead Score"],
    ["business_name", "Business Name"],
    ["category", "Category"],
    ["address", "Address"],
    ["phone", "Google Phone"],
    ["website_phones", "Website Phones"],
    ["emails", "Public Business Emails"],
    ["whatsapp", "WhatsApp"],
    ["instagram", "Instagram"],
    ["facebook", "Facebook"],
    ["linkedin", "LinkedIn"],
    ["website", "Website"],
    ["google_maps_url", "Google Maps"],
    ["rating", "Rating"],
    ["review_count", "Review Count"],
    ["place_id", "Google Place ID"],
  ];

  const lines = [
    columns.map(([, label]) => csvEscape(label)).join(","),
    ...rows.map(row => columns.map(([key]) => csvEscape(row[key])).join(",")),
  ];

  const blob = new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeName = (state.query || "business-leads").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").toLowerCase();
  a.href = url;
  a.download = `${safeName || "business-leads"}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
});

healthCheck();
