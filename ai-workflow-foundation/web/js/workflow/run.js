import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { readGlobalExecutorPayload } from "../core/executors.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { workflowState } from "./state.js";
import { renderEditorNodes, renderRunLiveBanner, shouldPollRunState, stopRunTimers, startRunTimers } from "./editor.js";
import { updateWorkflowCounts } from "./catalog.js";
import { workflowDisplayOrder, resolveNodeDisplayStatus, buildStateMachineNodeHtml, nodeRole, nodeNeedsReview } from "./transitions.js";
import { addOption } from "./node-form.js";

export function setState(state) {
  workflowState.currentState = state;
  $("runId").value = state.run_id;
  renderRunNodes();
  renderEditorNodes();
  refreshChanges();
  refreshRevisions();
  updateWorkflowCounts();
  startRunTimers();
  refreshArtifactOptions().catch((error) => setLog(error.message));
}

export function renderRunNodes() {
  const order = workflowDisplayOrder(workflowState.editingWorkflow);
  const nodeById = Object.fromEntries((workflowState.editingWorkflow.nodes || []).map((node) => [node.id, node]));
  $("nodes").innerHTML = "";
  $("reviewNode").innerHTML = "";
  $("targetNode").innerHTML = "";
  $("rerunNode").innerHTML = "";
  const defaultTarget = $("targetNode");
  if (defaultTarget) {
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "默认 · 重跑当前节点";
    defaultTarget.appendChild(blank);
  }
  const nodeIds = workflowState.currentState?.run_id ? order : Object.keys(workflowState.currentState?.nodes || {});
  for (const nodeId of nodeIds) {
    const spec = nodeById[nodeId] || { id: nodeId, name: nodeId, type: "ai" };
    const node = workflowState.currentState?.nodes?.[nodeId] || null;
    const displayStatus = resolveNodeDisplayStatus(nodeId, node);
    const item = document.createElement("div");
    const role = nodeRole(spec);
    item.className = `node sm-node node-role-${role} sm-status-${displayStatus}${workflowState.currentState?.current_node === nodeId ? " sm-active current" : ""}`;
    item.innerHTML = buildStateMachineNodeHtml(spec, node, displayStatus);
    $("nodes").appendChild(item);
    const reviewable =
      nodeRole(spec) === "review" ||
      (nodeNeedsReview(spec) && (displayStatus === "paused" || node?.phase === "review"));
    if (reviewable) addOption("reviewNode", nodeId, nodeId);
    addOption("targetNode", nodeId, nodeId);
    addOption("rerunNode", nodeId, nodeId);
  }
}

export async function refreshArtifactOptions() {
  const runId = $("runId").value.trim();
  $("artifactSelect").innerHTML = "";
  if (!runId) return;
  const payload = await api(`/runs/${encodeURIComponent(runId)}/artifacts`);
  for (const ref of payload.artifacts || []) addOption("artifactSelect", ref, ref);
}

export async function loadState(options = {}) {
  const runId = $("runId").value.trim();
  if (!runId) return;
  const payload = await api(`/runs/${encodeURIComponent(runId)}`);
  if (options.quiet) {
    workflowState.currentState = payload.state;
    $("runId").value = payload.state.run_id;
    renderRunLiveBanner();
    renderEditorNodes();
    renderRunNodes();
    updateWorkflowCounts();
    if (!shouldPollRunState()) stopRunTimers();
    else if (!workflowState.runClockTimer) startRunTimers();
    return;
  }
  setState(payload.state);
}

export async function refreshChanges() {
  const runId = $("runId").value.trim();
  if (!runId) return;
  const box = $("changes");
  box.innerHTML = "";
  const payload = await api(`/runs/${encodeURIComponent(runId)}/changes`);
  for (const change of payload.changes || []) {
    const item = document.createElement("div");
    item.className = "change";
    item.innerHTML = `
      <h3>${escapeHtml(change.change_id)}</h3>
      <div class="muted">node=${escapeHtml(change.node_id)} status=${escapeHtml(change.status)}</div>
      <div>${escapeHtml(change.feedback || "")}</div>
      <div class="row" style="margin-top:8px">
        <button data-apply="${escapeHtml(change.change_id)}">Apply + Rerun</button>
      </div>
    `;
    box.appendChild(item);
  }
  box.querySelectorAll("[data-apply]").forEach((button) => {
    button.addEventListener("click", async () => {
      const changeId = button.getAttribute("data-apply");
      const payload = await api(`/runs/${encodeURIComponent(runId)}/changes/${encodeURIComponent(changeId)}/apply`, {
        method: "POST",
        body: JSON.stringify({ rerun: true, ...readGlobalExecutorPayload() }),
      });
      setState(payload.state);
      setLog(`Applied ${changeId}`);
    });
  });
}

export async function refreshRevisions() {
  const runId = $("runId").value.trim();
  if (!runId) return;
  const box = $("revisions");
  box.innerHTML = "";
  const payload = await api(`/runs/${encodeURIComponent(runId)}/revisions`);
  for (const revision of payload.revisions || []) {
    const item = document.createElement("div");
    item.className = "revision";
    item.innerHTML = `
      <h3>${escapeHtml(revision.revision_id)}</h3>
      <div class="muted">${escapeHtml(revision.created_at || "")}</div>
      <div>${escapeHtml(revision.message || "")}</div>
      <div class="row" style="margin-top:8px">
        <button data-diff="${escapeHtml(revision.revision_id)}">Diff</button>
        <button data-rollback="${escapeHtml(revision.revision_id)}">Rollback</button>
      </div>
    `;
    box.appendChild(item);
  }
  box.querySelectorAll("[data-diff]").forEach((button) => {
    button.addEventListener("click", async () => {
      const revisionId = button.getAttribute("data-diff");
      const payload = await api(`/runs/${encodeURIComponent(runId)}/diff?left=${encodeURIComponent(revisionId)}`);
      $("diff").textContent = payload.diff;
    });
  });
  box.querySelectorAll("[data-rollback]").forEach((button) => {
    button.addEventListener("click", async () => {
      const revisionId = button.getAttribute("data-rollback");
      const payload = await api(`/runs/${encodeURIComponent(runId)}/rollback`, {
        method: "POST",
        body: JSON.stringify({ revision_id: revisionId }),
      });
      setState(payload.state);
      setLog(`Rolled back to ${revisionId}`);
    });
  });
}

export async function openArtifact(ref) {
  const runId = $("runId").value.trim();
  if (!runId || !ref) return;
  const payload = await api(`/runs/${encodeURIComponent(runId)}/artifact?ref=${encodeURIComponent(ref)}`);
  workflowState.currentArtifactRef = ref;
  $("artifact").value = payload.content;
  $("artifactMeta").textContent = `Editing ${ref}`;
}
