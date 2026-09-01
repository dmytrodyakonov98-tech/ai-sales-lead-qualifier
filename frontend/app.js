const byId = (id) => document.getElementById(id);

const form = byId("lead-form");
const rawText = byId("raw-text");
const submitLead = byId("submit-lead");
const formError = byId("form-error");
const resultPanel = byId("result-panel");
const approveButton = byId("approve-draft");
const rejectButton = byId("reject-draft");
const historyList = byId("history-list");

let activeLeadId = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload?.error?.message || `Request failed (${response.status})`);
  }
  return payload;
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function addLine(node, label, value) {
  const row = document.createElement("div");
  row.className = "fact-row";
  const key = document.createElement("span");
  key.className = "fact-label";
  key.textContent = label;
  const val = document.createElement("span");
  val.textContent = value ?? "Unknown";
  row.append(key, val);
  node.appendChild(row);
}

function formatBudget(q) {
  if (!q) return "Unknown";
  const min = q.estimated_deal_min_usd;
  const max = q.estimated_deal_max_usd;
  if (min == null && max == null) return "Unknown";
  if (min != null && max != null) return `$${min.toLocaleString()}–$${max.toLocaleString()}`;
  return `$${(max ?? min).toLocaleString()}`;
}

function renderDetail(detail) {
  activeLeadId = detail.lead.id;
  resultPanel.hidden = false;
  const q = detail.qualification;
  const facts = detail.facts;
  const draft = detail.draft;

  byId("score-total").textContent = q ? `${q.score.total}/100` : "Qualification unavailable";

  const components = byId("score-components");
  clearChildren(components);
  if (q) {
    const labels = [
      ["Budget", q.score.budget_fit, 25],
      ["Need", q.score.need_fit, 25],
      ["Timeline", q.score.timeline_fit, 15],
      ["Intent", q.score.decision_intent, 15],
      ["Clarity", q.score.project_clarity, 10],
      ["Company", q.score.company_fit, 10],
    ];
    for (const [label, value, max] of labels) addLine(components, label, `${value}/${max}`);
  }

  const factsNode = byId("lead-facts");
  clearChildren(factsNode);
  addLine(factsNode, "Status", detail.lead.status);
  addLine(factsNode, "Company", facts?.company_name);
  addLine(factsNode, "Need", facts?.need);
  addLine(factsNode, "Budget", formatBudget(q));
  addLine(factsNode, "Timeline", facts?.timeline_days == null ? "Unknown" : `${facts.timeline_days} days`);
  addLine(factsNode, "Fit", q?.fit);
  addLine(factsNode, "Priority", q?.priority);

  const missing = byId("missing-info");
  clearChildren(missing);
  const missingTitle = document.createElement("strong");
  missingTitle.textContent = "Missing information: ";
  const missingValue = document.createElement("span");
  missingValue.textContent = q?.missing_information?.length ? q.missing_information.join(", ") : "None";
  missing.append(missingTitle, missingValue);

  byId("recommended-action").textContent = q ? `Next action: ${q.recommended_action}` : "Next action unavailable";
  byId("draft-body").textContent = draft?.body || "No draft was created for this lead.";

  const pending = draft?.status === "pending";
  approveButton.disabled = !pending;
  rejectButton.disabled = !pending;
}

async function loadHistory() {
  const items = await api("/api/leads");
  clearChildren(historyList);
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    const company = item.company_name || "Unknown company";
    const score = item.score == null ? "—" : `${item.score}/100`;
    button.textContent = `${company} · ${score} · ${item.priority || "—"} · ${item.status}`;
    button.addEventListener("click", async () => {
      formError.textContent = "";
      try {
        renderDetail(await api(`/api/leads/${item.id}`));
      } catch (error) {
        formError.textContent = error.message;
      }
    });
    historyList.appendChild(button);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.textContent = "";
  submitLead.disabled = true;
  submitLead.textContent = "Qualifying…";
  try {
    const detail = await api("/api/leads", {
      method: "POST",
      body: JSON.stringify({raw_text: rawText.value}),
    });
    renderDetail(detail);
    await loadHistory();
  } catch (error) {
    formError.textContent = error.message;
    await loadHistory();
  } finally {
    submitLead.disabled = false;
    submitLead.textContent = "Qualify lead";
  }
});

async function review(action) {
  if (!activeLeadId) return;
  formError.textContent = "";
  try {
    const detail = await api(`/api/leads/${activeLeadId}/draft/${action}`, {method: "POST"});
    renderDetail(detail);
    await loadHistory();
  } catch (error) {
    formError.textContent = error.message;
  }
}

approveButton.addEventListener("click", () => review("approve"));
rejectButton.addEventListener("click", () => review("reject"));

loadHistory().catch((error) => { formError.textContent = error.message; });
