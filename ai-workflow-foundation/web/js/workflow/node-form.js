import { $ } from "../core/dom.js";
import { api } from "../core/api.js";
import { workflowState } from "./state.js";
import { nodeRole, normalizeNodeType } from "./transitions.js";
import { applyNodeExecutorControls, normalizeExecutorValue } from "../core/executors.js";
import {
  defaultReviewInputs,
  normalizeNodeReview,
  parseReviewChecklist,
  reviewChecklistText,
  syncReviewFieldsToNode,
} from "./node-review.js";
import { fillNodeInputsEditor, initNodeInputsEditor, readNodeInputsFromEditor } from "./node-inputs-editor.js";

function populateRejectTargetOptions(node, selectId = "nodeRejectTarget") {
  const select = $(selectId);
  if (!select) return;
  const selected = node?.params?.review_reject_target || "";
  select.innerHTML = '<option value="">默认 · 重跑当前节点</option>';
  for (const item of workflowState.editingWorkflow.nodes || []) {
    if (!item.id || item.id === node?.id) continue;
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = `${item.name || item.id} (${item.id})`;
    select.appendChild(option);
  }
  select.value = selected;
}

function populateReviewSkillSelect(node) {
  const select = $("nodeReviewSkill");
  if (!select) return;
  const skillSelect = $("nodeSkill");
  const selected = normalizeNodeReview(node).skill || "";
  select.innerHTML = '<option value="">无 · 仅人工对照标准</option>';
  if (skillSelect) {
    for (const option of skillSelect.options) {
      if (!option.value) continue;
      const item = document.createElement("option");
      item.value = option.value;
      item.textContent = option.textContent;
      select.appendChild(item);
    }
  }
  select.value = selected;
}

export function setNodeDetailTab(tab, { persist = true } = {}) {
  const next = tab === "review" ? "review" : tab === "iterate" ? "iterate" : "execute";
  if (persist) workflowState.nodeDetailTab = next;
  document.querySelectorAll("[data-node-detail-tab]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-node-detail-tab") === next);
  });
  document.querySelectorAll("[data-node-detail-panel]").forEach((panel) => {
    panel.hidden = panel.getAttribute("data-node-detail-panel") !== next;
  });
}

export function setNodeEditTab(tab, { persist = true } = {}) {
  const next = tab === "review" ? "review" : "execute";
  if (persist) workflowState.nodeDetailTab = next;
  document.querySelectorAll("[data-node-edit-tab]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-node-edit-tab") === next);
  });
  document.querySelectorAll("[data-node-edit-panel]").forEach((panel) => {
    panel.hidden = panel.getAttribute("data-node-edit-panel") !== next;
  });
}

export function applyNodeTypeChange(type) {
  const node = currentNode();
  if (!node) return;
  const nextType = normalizeNodeType(type);
  node.type = nextType;

  if (nextType === "review") {
    node.skill = null;
    delete node.executor;
    delete node.agent_provider;
    node.outputs = {};
  }

  const review = normalizeNodeReview(node);
  syncReviewFieldsToNode(node, review);

  if ($("nodeType")) $("nodeType").value = nextType;
  applyNodeFormVisibility(node);
}

export function applyNodeFormVisibility(node) {
  const isReview = nodeRole(node) === "review";
  $("nodeSkillField").style.display = isReview ? "none" : "";
  $("nodeExecutorField").style.display = isReview ? "none" : "";
  $("nodeOutputsField").style.display = isReview ? "none" : "";
  $("nodeExecuteEditPanel").hidden = isReview;
  document.querySelectorAll("[data-node-edit-tab]").forEach((button) => {
    const tab = button.getAttribute("data-node-edit-tab");
    button.hidden = isReview && tab === "execute";
  });
  document.querySelectorAll("[data-node-detail-tab]").forEach((button) => {
    const tab = button.getAttribute("data-node-detail-tab");
    button.hidden = isReview && tab === "execute";
  });
  if (isReview) {
    setNodeEditTab("review", { persist: true });
    setNodeDetailTab("review", { persist: true });
  }
}

export function currentNode() {
  return workflowState.editingWorkflow.nodes[workflowState.selectedNodeIndex];
}

export function renderNodeForm() {
  workflowState.suppressNodeForm = true;
  const node = currentNode();
  if (!node) {
    workflowState.suppressNodeForm = false;
    return;
  }
  $("nodeId").value = node.id || "";
  $("nodeName").value = node.name || "";
  $("nodeType").value = normalizeNodeType(node.type || "ai");
  $("nodeSkill").value = node.skill || "";
  $("nodeExecutor").value = normalizeExecutorValue(node.executor || "");
  $("nodeAgentProvider").value = node.agent_provider || "";
  fillNodeInputsEditor(node.inputs || {}, node.id);
  $("nodeOutputs").value = JSON.stringify(node.outputs || {}, null, 2);

  const review = normalizeNodeReview(node);
  $("approvalMode").value = review.mode;
  $("approvalLevel").value = review.level;
  $("nodeReviewInputs").value = JSON.stringify(review.inputs || defaultReviewInputs(node), null, 2);
  $("nodeReviewCriteria").value = review.criteria || "";
  $("nodeReviewChecklist").value = reviewChecklistText(review.checklist);
  populateReviewSkillSelect(node);
  $("nodeReviewSkill").value = review.skill || "";
  populateRejectTargetOptions(node);
  populateRejectTargetOptions(node, "nodeReviewRejectTarget");

  applyNodeFormVisibility(node);
  applyNodeExecutorControls(node);
  setNodeEditTab(workflowState.nodeDetailTab, { persist: false });
  workflowState.suppressNodeForm = false;
  refreshSkillPreview();
}

function readReviewFieldsFromForm(node) {
  let inputs = defaultReviewInputs(node);
  try {
    inputs = JSON.parse($("nodeReviewInputs").value || "{}");
  } catch {
    // Keep previous review inputs while typing invalid JSON.
  }
  return {
    mode: $("approvalMode").value || "auto",
    level: $("approvalLevel").value || "optional",
    inputs,
    skill: $("nodeReviewSkill")?.value || null,
    criteria: $("nodeReviewCriteria")?.value?.trim() || "",
    checklist: parseReviewChecklist($("nodeReviewChecklist")?.value || ""),
  };
}

export function syncNodeFormToWorkflow() {
  if (workflowState.suppressNodeForm) return;
  const node = currentNode();
  if (!node) return;
  node.id = $("nodeId").value.trim() || node.id;
  node.name = $("nodeName").value.trim() || node.name;
  node.type = normalizeNodeType($("nodeType").value);

  const reviewFields = readReviewFieldsFromForm(node);
  syncReviewFieldsToNode(node, reviewFields);

  if (nodeRole(node) === "review") {
    node.skill = null;
    node.executor = undefined;
    delete node.executor;
    node.agent_provider = undefined;
    delete node.agent_provider;
    node.outputs = {};
    applyNodeFormVisibility(node);
    return;
  }

  node.skill = $("nodeSkill").value || null;
  const executor = normalizeExecutorValue($("nodeExecutor").value);
  node.executor = executor || undefined;
  if (!node.executor) delete node.executor;
  const agentProvider = $("nodeAgentProvider").value;
  if (executor === "agent" && agentProvider) {
    node.agent_provider = agentProvider;
  } else {
    delete node.agent_provider;
  }
  try {
    node.inputs = readNodeInputsFromEditor();
    node.outputs = JSON.parse($("nodeOutputs").value || "{}");
  } catch (error) {
    throw new Error(`节点 JSON 无效: ${error.message}`);
  }

  if (!node.params) node.params = {};
  const rejectTarget = $("nodeRejectTarget")?.value || "";
  if (rejectTarget) node.params.review_reject_target = rejectTarget;
  else delete node.params.review_reject_target;
  if (Object.keys(node.params).length === 0) delete node.params;

  applyNodeFormVisibility(node);
}

export async function refreshSkillPreview() {
  const skillId = $("nodeSkill").value;
  const contractEl = $("nodeOutputContractPreview");
  if (!skillId) {
    $("skillPreview").textContent = "未选择 Skill。";
    if (contractEl) contractEl.textContent = "选择 Skill 后显示 Output Contract。";
    return;
  }
  try {
    const payload = await api(`/skills/${encodeURIComponent(skillId)}`);
    const skill = payload.skill;
    $("skillPreview").textContent = [
      `goal: ${skill.goal}`,
      payload.markdown ? `SKILL.md: ${payload.markdown.slice(0, 160)}${payload.markdown.length > 160 ? "..." : ""}` : skill.ref ? `ref: ${skill.ref}` : "",
      skill.executor ? `executor: ${skill.executor}` : "",
      skill.quality?.length ? `quality: ${skill.quality.join(" | ")}` : "",
    ].filter(Boolean).join("\n");
    const node = currentNode();
    const nodeOutputs = node?.outputs && Object.keys(node.outputs).length ? node.outputs : null;
    const contract = nodeOutputs || skill.output || {};
    if (contractEl) {
      contractEl.textContent = JSON.stringify(contract, null, 2);
    }
  } catch (error) {
    $("skillPreview").textContent = error.message;
    if (contractEl) contractEl.textContent = error.message;
  }
}

export function addOption(selectId, value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  $(selectId).appendChild(option);
}
