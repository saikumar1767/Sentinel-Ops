const state = {
  incidents: [],
  selectedIncident: null,
  activeWorkflow: null,
};

const elements = {
  launchCommand: document.getElementById("launchCommand"),
  readinessSummary: document.getElementById("readinessSummary"),
  readinessDetail: document.getElementById("readinessDetail"),
  evalSummary: document.getElementById("evalSummary"),
  evalDetail: document.getElementById("evalDetail"),
  timelineSummary: document.getElementById("timelineSummary"),
  scenarioList: document.getElementById("scenarioList"),
  scenarioTitle: document.getElementById("scenarioTitle"),
  scenarioDescription: document.getElementById("scenarioDescription"),
  scenarioChip: document.getElementById("scenarioChip"),
  scenarioEndpoint: document.getElementById("scenarioEndpoint"),
  scenarioDuration: document.getElementById("scenarioDuration"),
  scenarioBundles: document.getElementById("scenarioBundles"),
  runScenarioButton: document.getElementById("runScenarioButton"),
  refreshTimelineButton: document.getElementById("refreshTimelineButton"),
  workflowControls: document.getElementById("workflowControls"),
  reviewNotesInput: document.getElementById("reviewNotesInput"),
  editedPlanInput: document.getElementById("editedPlanInput"),
  approveButton: document.getElementById("approveButton"),
  rejectButton: document.getElementById("rejectButton"),
  requestPayload: document.getElementById("requestPayload"),
  expectedOutcome: document.getElementById("expectedOutcome"),
  resultHighlights: document.getElementById("resultHighlights"),
  expectationChecks: document.getElementById("expectationChecks"),
  workflowEvidence: document.getElementById("workflowEvidence"),
  responsePayload: document.getElementById("responsePayload"),
  timelineList: document.getElementById("timelineList"),
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") || contentType.includes("application/problem+json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const error = new Error(typeof body === "string" ? body : body.detail || "Request failed.");
    error.payload = body;
    throw error;
  }

  return body;
}

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function createBulletCard(title, body, extra = "") {
  return `
    <article class="bullet-card">
      <strong>${title}</strong>
      <p>${body}</p>
      ${extra}
    </article>
  `;
}

function setWorkflowControlsVisible(visible) {
  elements.workflowControls.classList.toggle("is-hidden", !visible);
}

function renderOverview(overview) {
  elements.launchCommand.textContent = overview.launch_command;
  elements.evalSummary.textContent = `${overview.eval_total_cases} eval cases · ${(overview.overall_pass_rate * 100).toFixed(0)}% pass`;
  elements.evalDetail.textContent =
    `Analyze ${(overview.analyze_pass_rate * 100).toFixed(0)}% · Investigate ${(overview.investigate_pass_rate * 100).toFixed(0)}% · RAG ${(overview.rag_pass_rate * 100).toFixed(0)}% · Workflow ${(overview.workflow_pass_rate * 100).toFixed(0)}%`;
}

function renderReadiness(report) {
  elements.readinessSummary.textContent = report.summary;
  elements.readinessDetail.textContent = `${report.status.toUpperCase()} · traffic ready=${report.traffic_ready} · strict ready=${report.strict_ready}`;
}

function renderIncidentList() {
  elements.scenarioList.innerHTML = state.incidents.map((incident) => `
    <button class="scenario-card ${state.selectedIncident?.incident_id === incident.incident_id ? "is-active" : ""}" data-incident-id="${incident.incident_id}">
      <strong>${incident.recommended_order}. ${incident.title}</strong>
      <p>${incident.headline}</p>
    </button>
  `).join("");

  elements.scenarioList.querySelectorAll("[data-incident-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const incident = state.incidents.find((item) => item.incident_id === button.dataset.incidentId);
      if (incident) {
        selectIncident(incident);
      }
    });
  });
}

function renderIncidentDetails(incident) {
  elements.scenarioTitle.textContent = incident.title;
  elements.scenarioDescription.textContent = incident.description;
  elements.scenarioChip.textContent = incident.category;
  elements.scenarioEndpoint.textContent = incident.endpoint;
  elements.scenarioDuration.textContent = `${incident.estimated_run_seconds}s`;
  elements.scenarioBundles.textContent = incident.artifact_paths.length
    ? incident.artifact_paths.join(", ")
    : "Direct input only";
  elements.requestPayload.textContent = formatJson(incident.request_body);
  elements.expectedOutcome.innerHTML = [
    createBulletCard(
      "Headline",
      incident.headline,
      `<p class="muted">Expected incident: ${incident.expected_outcome.incident_type || "n/a"} · severity: ${incident.expected_outcome.severity || "n/a"}</p>`
    ),
    ...incident.operator_steps.map((step, index) => createBulletCard(`Run step ${index + 1}`, step)),
    ...incident.expected_outcome.notes.map((note, index) => createBulletCard(`Operator note ${index + 1}`, note)),
  ].join("");
  elements.resultHighlights.innerHTML = "Run an incident to see live result highlights.";
  elements.expectationChecks.innerHTML = "No live result yet.";
  elements.workflowEvidence.innerHTML = "Workflow tool results and audit events appear here when available.";
  elements.responsePayload.textContent = "Run an incident to capture the raw response.";
  elements.runScenarioButton.disabled = false;
  elements.runScenarioButton.textContent = incident.endpoint === "/analyze"
    ? "Run Analyze"
    : incident.endpoint === "/investigate"
      ? "Run Investigate"
      : "Run Workflow";
  setWorkflowControlsVisible(false);
  state.activeWorkflow = null;
}

function selectIncident(incident) {
  state.selectedIncident = incident;
  renderIncidentList();
  renderIncidentDetails(incident);
}

function flattenTextForChecks(payload) {
  return formatJson(payload).toLowerCase();
}

function buildExpectationChecks(incident, payload) {
  const expected = incident.expected_outcome;
  const checks = [];
  const citations = payload.source_citations || payload.final_report?.source_citations || [];
  const text = flattenTextForChecks(payload);

  if (expected.incident_type) {
    checks.push({
      label: "Incident type",
      ok: String(payload.incident_type || payload.final_report?.incident_type || "").toLowerCase() === expected.incident_type,
      detail: `expected ${expected.incident_type}`,
    });
  }
  if (expected.severity) {
    checks.push({
      label: "Severity",
      ok: String(payload.severity || payload.final_report?.severity || "").toLowerCase() === expected.severity,
      detail: `expected ${expected.severity}`,
    });
  }
  if (expected.retrieval_status) {
    checks.push({
      label: "Retrieval status",
      ok: String(payload.retrieval_status || payload.final_report?.retrieval_status || "").toLowerCase() === expected.retrieval_status,
      detail: `expected ${expected.retrieval_status}`,
    });
  }
  if (expected.workflow_status) {
    checks.push({
      label: "Workflow status",
      ok: String(payload.status || "").toLowerCase() === expected.workflow_status,
      detail: `expected ${expected.workflow_status}`,
    });
  }
  if (expected.approval_status) {
    checks.push({
      label: "Approval status",
      ok: String(payload.approval_status || payload.final_report?.approval_status || "").toLowerCase() === expected.approval_status,
      detail: `expected ${expected.approval_status}`,
    });
  }

  expected.citation_keywords.forEach((keyword) => {
    checks.push({
      label: `Citation contains "${keyword}"`,
      ok: citations.some((citation) => citation.toLowerCase().includes(keyword.toLowerCase())),
      detail: "expected citation keyword",
    });
  });

  expected.evidence_keywords.forEach((keyword) => {
    checks.push({
      label: `Evidence mentions "${keyword}"`,
      ok: text.includes(keyword.toLowerCase()),
      detail: "expected evidence keyword",
    });
  });

  return checks;
}

function renderExpectationChecks(incident, payload) {
  const checks = buildExpectationChecks(incident, payload);
  if (!checks.length) {
    elements.expectationChecks.innerHTML = '<div class="empty-state">No expectation checks were defined for this incident.</div>';
    return;
  }

  elements.expectationChecks.innerHTML = checks.map((check) => createBulletCard(
    check.label,
    check.detail,
    `<p class="${check.ok ? "status-pass" : "status-fail"}">${check.ok ? "Match" : "Needs review"}</p>`
  )).join("");
}

function renderHighlights(payload) {
  const cards = [];
  const finalReport = payload.final_report || {};
  const incidentType = payload.incident_type || finalReport.incident_type;
  const severity = payload.severity || finalReport.severity;
  const managerSummary = payload.manager_summary || finalReport.manager_summary;
  const rootCause = payload.suspected_root_cause || finalReport.suspected_root_cause;
  const retrievedEvidence = payload.retrieved_evidence || finalReport.retrieved_evidence || [];
  const citations = payload.source_citations || finalReport.source_citations || [];

  if (payload.status) {
    cards.push(createBulletCard("Workflow status", payload.status, `<p class="muted">Approval: ${payload.approval_status || "n/a"}</p>`));
  }
  if (incidentType) {
    cards.push(createBulletCard("Incident", `${incidentType} · ${severity || "n/a"}`));
  }
  if (managerSummary) {
    cards.push(createBulletCard("Manager summary", managerSummary));
  }
  if (rootCause) {
    cards.push(createBulletCard("Root cause", rootCause));
  }
  if (retrievedEvidence.length) {
    cards.push(createBulletCard("Retrieved evidence", retrievedEvidence.join(" | ")));
  }
  if (citations.length) {
    cards.push(createBulletCard("Citations", citations.join(" | ")));
  }

  elements.resultHighlights.innerHTML = cards.length ? cards.join("") : "No highlights available.";
}

function renderWorkflowEvidence(payload, audit = null) {
  const blocks = [];

  if (Array.isArray(payload.tool_results) && payload.tool_results.length) {
    payload.tool_results.slice(0, 6).forEach((record) => {
      const status = record.ok ? "ok" : "safe failure";
      blocks.push(createBulletCard(
        `${record.name} · ${status}`,
        `cached=${record.cached} · duration=${record.duration_ms ?? "n/a"}ms`,
        `<pre class="code-block">${formatJson(record.payload)}</pre>`
      ));
    });
  }

  if (audit?.events?.length) {
    audit.events.forEach((event) => {
      blocks.push(createBulletCard(
        `Audit · ${event.action}`,
        `${event.decision} · ${event.status_after}`,
        `<p class="muted">${event.review_notes || "No review notes."}</p>`
      ));
    });
  }

  elements.workflowEvidence.innerHTML = blocks.length
    ? blocks.join("")
    : "Workflow tool results and audit events appear here when available.";
}

function renderResponse(incident, payload, audit = null) {
  renderHighlights(payload);
  renderExpectationChecks(incident, payload);
  renderWorkflowEvidence(payload, audit);
  elements.responsePayload.textContent = formatJson(payload);
}

function renderTimeline(entries) {
  elements.timelineSummary.textContent = `${entries.length} recent incidents ready`;
  elements.timelineList.innerHTML = entries.map((entry) => `
    <article class="timeline-entry">
      <header>
        <strong>${entry.incident_type} · ${entry.severity}</strong>
        <time>${new Date(entry.created_at).toLocaleString()}</time>
      </header>
      <p>${entry.manager_summary}</p>
      <p class="muted">${entry.source} timeline · retrieval=${entry.retrieval_status} · confidence=${entry.confidence}</p>
    </article>
  `).join("");
}

async function loadTimeline() {
  const timeline = await fetchJson("/console/timeline");
  renderTimeline(timeline.entries);
}

async function loadBootData() {
  const [overview, readiness, library, timeline] = await Promise.all([
    fetchJson("/console/overview"),
    fetchJson("/ready"),
    fetchJson("/console/incidents"),
    fetchJson("/console/timeline"),
  ]);

  renderOverview(overview);
  renderReadiness(readiness);
  state.incidents = library.incidents;
  renderIncidentList();
  renderTimeline(timeline.entries);
  if (state.incidents.length) {
    selectIncident(state.incidents[0]);
  }
}

async function runScenario() {
  if (!state.selectedIncident) {
    return;
  }

  elements.runScenarioButton.disabled = true;
  elements.runScenarioButton.textContent = "Running...";

  try {
    const payload = await fetchJson(state.selectedIncident.endpoint, {
      method: "POST",
      body: JSON.stringify(state.selectedIncident.request_body),
    });

    if (state.selectedIncident.endpoint === "/workflow/investigate") {
      state.activeWorkflow = { threadId: payload.thread_id };
      const audit = await fetchJson(`/workflow/${payload.thread_id}/audit`);
      renderResponse(state.selectedIncident, payload, audit);
      setWorkflowControlsVisible(payload.status === "waiting_for_approval");
    } else {
      renderResponse(state.selectedIncident, payload);
      setWorkflowControlsVisible(false);
      await loadTimeline();
    }
  } catch (error) {
    const payload = error.payload || { detail: error.message };
    elements.resultHighlights.innerHTML = createBulletCard("Request failed", payload.detail || "Unexpected error");
    elements.responsePayload.textContent = formatJson(payload);
    elements.expectationChecks.innerHTML = '<div class="status-fail">The live request failed. Inspect the raw response.</div>';
  } finally {
    elements.runScenarioButton.disabled = false;
    elements.runScenarioButton.textContent = state.selectedIncident.endpoint === "/analyze"
      ? "Run Analyze"
      : state.selectedIncident.endpoint === "/investigate"
        ? "Run Investigate"
        : "Run Workflow";
  }
}

function approvalPayload(decision) {
  const notes = elements.reviewNotesInput.value.trim();
  const editedPlan = elements.editedPlanInput.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (decision === "approve") {
    return {
      review_notes: notes || "Approved from the operations console.",
      edited_remediation_plan: editedPlan,
    };
  }

  return {
    reason: notes || "Rejected from the operations console.",
    edited_remediation_plan: editedPlan,
  };
}

async function resolveWorkflow(decision) {
  if (!state.activeWorkflow || !state.selectedIncident) {
    return;
  }

  const endpoint = decision === "approve"
    ? `/workflow/${state.activeWorkflow.threadId}/approve`
    : `/workflow/${state.activeWorkflow.threadId}/reject`;

  try {
    const payload = await fetchJson(endpoint, {
      method: "POST",
      body: JSON.stringify(approvalPayload(decision)),
    });
    const audit = await fetchJson(`/workflow/${state.activeWorkflow.threadId}/audit`);
    renderResponse(state.selectedIncident, payload, audit);
    setWorkflowControlsVisible(false);
    await loadTimeline();
  } catch (error) {
    const payload = error.payload || { detail: error.message };
    elements.responsePayload.textContent = formatJson(payload);
    elements.workflowEvidence.innerHTML = createBulletCard("Workflow decision failed", payload.detail || "Unexpected error");
  }
}

elements.runScenarioButton.addEventListener("click", runScenario);
elements.refreshTimelineButton.addEventListener("click", loadTimeline);
elements.approveButton.addEventListener("click", () => resolveWorkflow("approve"));
elements.rejectButton.addEventListener("click", () => resolveWorkflow("reject"));

loadBootData().catch((error) => {
  elements.resultHighlights.innerHTML = createBulletCard(
    "Console boot failed",
    error.message || "Unexpected error while loading the operations console."
  );
  elements.responsePayload.textContent = formatJson(error.payload || { detail: error.message });
});
