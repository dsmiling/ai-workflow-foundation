import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { workflowState } from "./state.js";
import { updateWorkflowCounts } from "./catalog.js";
import { renderRunNodes, loadState } from "./run.js";
import { workflowDisplayOrder, resolveNodeDisplayStatus, buildStateMachineNodeHtml, transitionEdgeHtml, nodeRole, formatDuration, runDurationMs, resolveNodeLifecycle } from "./transitions.js";
import { currentNode, syncNodeFormToWorkflow } from "./node-form.js";
import { syncNodeTestToWorkflow } from "../core/executors.js";
import { renderNodeForm } from "./node-form.js";
import { renderNodeInspector } from "./inspector.js";
import { renderAssistFocusChips } from "./assist.js";

export function selectNode(index) {
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
  else syncNodeTestToWorkflow(currentNode());
  workflowState.selectedNodeIndex = index;
  workflowState.nodeEditOpen = false;
  renderNodeForm();
  renderEditorNodes();
  renderNodeInspector();
  renderAssistFocusChips();
}

export function openNodeEditor(index = workflowState.selectedNodeIndex) {
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
  else syncNodeTestToWorkflow(currentNode());
  workflowState.selectedNodeIndex = index;
  workflowState.nodeEditOpen = true;
  renderEditorNodes();
  renderNodeForm();
  renderNodeInspector();
  renderAssistFocusChips();
}

export function renderRunLiveBanner() {
  const banner = $("runLiveBanner");
  if (!banner) return;
  if (!workflowState.currentState?.run_id) {
    banner.classList.add("hidden");
    banner.innerHTML = "";
    return;
  }
  const currentNode = (workflowState.editingWorkflow.nodes || []).find((node) => node.id === workflowState.currentState.current_node);
  const currentLabel = currentNode?.name || workflowState.currentState.current_node || "-";
  const runMs = runDurationMs();
  banner.classList.remove("hidden");
  banner.innerHTML = `
    <div><strong>Run</strong><div class="run-live-value">${escapeHtml(workflowState.currentState.run_id)}</div></div>
    <div><strong>工作流状态</strong><div class="run-live-value">${escapeHtml(workflowState.currentState.status || "-")}</div></div>
    <div><strong>当前阶段</strong><div class="run-live-value">${escapeHtml(currentLabel)}</div></div>
    <div><strong>总运行时长</strong><div class="run-live-value">${runMs == null ? "-" : formatDuration(runMs)}</div></div>
  `;
}

export function shouldPollRunState() {
  if (!workflowState.currentState?.run_id) return false;
  if (workflowState.currentState.status === "running") return true;
  if (workflowState.currentState.status === "paused" && workflowState.currentState.current_node) return true;
  return false;
}

export function stopRunTimers() {
  if (workflowState.runPollTimer) {
    clearInterval(workflowState.runPollTimer);
    workflowState.runPollTimer = null;
  }
  if (workflowState.runClockTimer) {
    clearInterval(workflowState.runClockTimer);
    workflowState.runClockTimer = null;
  }
}

export function startRunTimers() {
  stopRunTimers();
  if (!shouldPollRunState() && !workflowState.currentState?.run_id) return;
  workflowState.runClockTimer = setInterval(() => {
    renderRunLiveBanner();
    renderEditorNodes();
    renderRunNodes();
  }, 1000);
  if (shouldPollRunState()) {
    workflowState.runPollTimer = setInterval(() => {
      loadState({ quiet: true }).catch(() => {});
    }, 2000);
  }
}

export function renderEditorNodes() {
  const box = $("editorNodes");
  box.innerHTML = "";
  renderRunLiveBanner();
  const order = workflowDisplayOrder(workflowState.editingWorkflow);
  const nodeById = Object.fromEntries((workflowState.editingWorkflow.nodes || []).map((node) => [node.id, node]));
  const transitions = workflowState.editingWorkflow.transitions || [];
  order.forEach((nodeId) => {
    const node = nodeById[nodeId];
    if (!node) return;
    const nodeIndex = workflowState.editingWorkflow.nodes.findIndex((item) => item.id === nodeId);
    const runNode = workflowState.currentState?.nodes?.[nodeId] || null;
    const displayStatus = resolveNodeDisplayStatus(nodeId, runNode);
    const lifecycle = resolveNodeLifecycle(node, nodeIndex, runNode);
    const item = document.createElement("div");
    const role = nodeRole(node);
    const isActive = workflowState.currentState?.current_node === nodeId;
    const isSelected = nodeIndex === workflowState.selectedNodeIndex;
    item.className = `sm-node editor-node node-role-${role} sm-status-${displayStatus} ${lifecycle.className}${isActive ? " sm-active current" : ""}${isSelected ? " selected" : ""}${workflowState.nodeEditOpen && isSelected ? " editing" : ""}`;
    item.innerHTML = buildStateMachineNodeHtml(node, runNode, displayStatus, nodeIndex);
    item.addEventListener("click", () => selectNode(nodeIndex));
    item.addEventListener("dblclick", (event) => {
      event.preventDefault();
      openNodeEditor(nodeIndex);
    });
    box.appendChild(item);

    const currentOrderIndex = order.indexOf(nodeId);
    const nextId = order[currentOrderIndex + 1];
    if (!nextId) return;
    const edge = transitions.find((transition) => transition.from === nodeId && transition.to === nextId)
      || { from: nodeId, to: nextId, when: "always" };
    if (edge.when === "rejected") return;
    const edgeNode = document.createElement("div");
    edgeNode.innerHTML = transitionEdgeHtml(edge);
    box.appendChild(edgeNode.firstElementChild);
  });
  updateWorkflowCounts();
}
