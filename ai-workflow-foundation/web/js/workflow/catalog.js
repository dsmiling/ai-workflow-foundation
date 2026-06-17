import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { workflowState } from "./state.js";
import { renderWorkflowInspector, renderNodeInspector, setWorkflowView } from "./inspector.js";
import { renderEditorNodes } from "./editor.js";
import { currentNode, syncNodeFormToWorkflow } from "./node-form.js";
import { syncNodeTestToWorkflow } from "../core/executors.js";

export function syncLinearTransitions() {
  const nodeIds = (workflowState.editingWorkflow.nodes || []).map((node) => node.id).filter(Boolean);
  const custom = (workflowState.editingWorkflow.transitions || []).filter((transition) => transition.when !== "always");
  const linear = [];
  for (let index = 0; index < nodeIds.length - 1; index += 1) {
    linear.push({ from: nodeIds[index], to: nodeIds[index + 1], when: "always" });
  }
  workflowState.editingWorkflow.initial = nodeIds[0] || "";
  workflowState.editingWorkflow.transitions = [...linear, ...custom];
}

export function defaultNode() {
  const id = `node_${workflowState.editingWorkflow.nodes.length + 1}`;
  return {
    id,
    name: `Node ${workflowState.editingWorkflow.nodes.length + 1}`,
    type: "ai",
    skill: "",
    inputs: {},
    outputs: { primary: "output.md" },
    approval: { mode: "human", level: "optional" },
    review: {
      mode: "human",
      level: "optional",
      inputs: { primary_output: `artifact.${id}` },
      criteria: "",
      checklist: [],
    },
  };
}

export function blankWorkflow() {
  const workflow = { id: "new_workflow", name: "New Workflow", workspace_root: "", nodes: [defaultNode()], initial: "", transitions: [] };
  workflowState.editingWorkflow = workflow;
  syncLinearTransitions();
  return workflowState.editingWorkflow;
}

export function renderWorkflowCards() {
  const box = $("workflowCards");
  if (!box) return;
  box.innerHTML = "";
  $("workflowCount").textContent = String(workflowState.workflowCatalog.length);
  if (!workflowState.workflowCatalog.length) {
    box.innerHTML = '<div class="empty-state">暂无工作流。</div>';
    return;
  }
  for (const item of workflowState.workflowCatalog) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `workflow-card${item.id === workflowState.editingWorkflow.id ? " selected" : ""}`;
    card.innerHTML = `
      <div class="workflow-card-title">${escapeHtml(item.name)}</div>
      <div class="workflow-card-meta">${escapeHtml(item.id)}</div>
      <div class="workflow-card-meta">${escapeHtml(item.source)} · ${item.editable ? "可编辑" : "只读"}</div>
    `;
    let clickTimer = null;
    card.addEventListener("click", () => {
      if (clickTimer) clearTimeout(clickTimer);
      clickTimer = setTimeout(() => {
        clickTimer = null;
        selectWorkflow(item.id).catch((error) => setLog(error.message));
      }, 220);
    });
    card.addEventListener("dblclick", (event) => {
      event.preventDefault();
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
      }
      openWorkflowNodes(item.id).catch((error) => setLog(error.message));
    });
    box.appendChild(card);
  }
}

export function updateWorkflowCounts() {
  $("nodeCount").textContent = String(workflowState.editingWorkflow.nodes?.length || 0);
  $("runStatusLabel").textContent = workflowState.currentState?.status || (workflowState.currentState?.run_id ? "loaded" : "idle");
}

export async function refreshWorkflowCatalog(selectId) {
  const payload = await api("/workflows");
  workflowState.workflowCatalog = payload.workflows || [];
  const select = $("workflowSelect");
  const previous = select.value;
  select.innerHTML = "";
  for (const item of workflowState.workflowCatalog) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = `${item.name} [${item.source}]`;
    select.appendChild(option);
  }
  const targetId = selectId || previous || (workflowState.workflowCatalog[0] && workflowState.workflowCatalog[0].id);
  if (targetId) {
    select.value = targetId;
    await selectWorkflow(targetId);
  } else {
    renderWorkflowCards();
    renderWorkflowInspector();
  }
}

export function populateWorkflowForm() {
  $("wfId").value = workflowState.editingWorkflow.id || "";
  $("wfName").value = workflowState.editingWorkflow.name || "";
  $("wfRoot").value = workflowState.editingWorkflow.workspace_root || "";
  $("wfInitial").value = workflowState.editingWorkflow.initial || (workflowState.editingWorkflow.nodes?.[0]?.id || "");
  $("wfTransitions").value = JSON.stringify(workflowState.editingWorkflow.transitions || [], null, 2);
  $("workflowPath").value = workflowState.currentWorkflowPath || "";
}

export function syncWorkflowFormToWorkflow() {
  if (!workflowState.workflowEditOpen) return;
  workflowState.editingWorkflow.id = $("wfId").value.trim();
  workflowState.editingWorkflow.name = $("wfName").value.trim();
  workflowState.editingWorkflow.workspace_root = $("wfRoot").value.trim();
  workflowState.editingWorkflow.initial = $("wfInitial").value.trim();
  try {
    const transitions = $("wfTransitions").value.trim();
    workflowState.editingWorkflow.transitions = transitions ? JSON.parse(transitions) : [];
  } catch (error) {
    throw new Error(`transitions JSON 无效: ${error.message}`);
  }
}

export async function loadWorkflowData(workflowId) {
  const payload = await api(`/workflows/${encodeURIComponent(workflowId)}`);
  workflowState.editingWorkflow = payload.workflow;
  workflowState.currentWorkflowPath = payload.path;
  workflowState.currentWorkflowEditable = payload.editable;
  workflowState.selectedNodeIndex = 0;
  workflowState.nodeEditOpen = false;
  $("workflowPath").value = payload.path;
  $("workflowMeta").textContent = `${payload.source} · ${payload.editable ? "可编辑" : "只读示例"}`;
  $("wfId").readOnly = !workflowState.currentWorkflowEditable && payload.source === "workspace";
  $("workflowSelect").value = workflowId;
  renderEditorNodes();
  renderNodeInspector();
  return payload;
}

export async function selectWorkflow(workflowId) {
  if (workflowState.workflowEditOpen) syncWorkflowFormToWorkflow();
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
  await loadWorkflowData(workflowId);
  workflowState.workflowEditOpen = false;
  renderWorkflowCards();
  renderWorkflowInspector();
}

export async function openWorkflowEditor(workflowId = workflowState.editingWorkflow.id) {
  if (workflowState.workflowEditOpen) syncWorkflowFormToWorkflow();
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
  if (workflowId && workflowId !== workflowState.editingWorkflow.id) {
    await loadWorkflowData(workflowId);
  }
  workflowState.workflowEditOpen = true;
  workflowState.nodeEditOpen = false;
  populateWorkflowForm();
  renderWorkflowCards();
  renderWorkflowInspector();
  renderNodeInspector();
  setWorkflowView("workflows");
}

export async function openWorkflowNodes(workflowId = workflowState.editingWorkflow.id) {
  if (workflowState.workflowEditOpen) syncWorkflowFormToWorkflow();
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
  if (workflowId && workflowId !== workflowState.editingWorkflow.id) {
    await loadWorkflowData(workflowId);
  }
  workflowState.workflowEditOpen = false;
  workflowState.nodeEditOpen = false;
  workflowState.selectedNodeIndex = 0;
  renderWorkflowCards();
  renderWorkflowInspector();
  renderEditorNodes();
  renderNodeInspector();
  setWorkflowView("nodes");
}

export async function loadWorkflowForEdit(workflowId) {
  await selectWorkflow(workflowId);
}

export async function saveWorkflow() {
  if (workflowState.workflowEditOpen) syncWorkflowFormToWorkflow();
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
  else syncNodeTestToWorkflow(currentNode());
  workflowState.editingWorkflow.id = $("wfId").value.trim() || workflowState.editingWorkflow.id;
  workflowState.editingWorkflow.name = $("wfName").value.trim() || workflowState.editingWorkflow.name;
  workflowState.editingWorkflow.workspace_root = $("wfRoot").value.trim();
  const method = workflowState.currentWorkflowEditable && workflowState.editingWorkflow.id === $("workflowSelect").value ? "PUT" : "POST";
  const path = method === "PUT"
    ? `/workflows/${encodeURIComponent(workflowState.editingWorkflow.id)}`
    : "/workflows";
  const payload = await api(path, {
    method,
    body: JSON.stringify({ workflow: workflowState.editingWorkflow }),
  });
  workflowState.currentWorkflowEditable = true;
  await refreshWorkflowCatalog(payload.workflow.id);
  setLog(`Saved workflow ${payload.workflow.id}`);
}
