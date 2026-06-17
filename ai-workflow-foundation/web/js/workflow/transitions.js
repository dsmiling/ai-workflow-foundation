import { escapeHtml } from "../core/dom.js";
import { resolveExecutorLabel } from "../core/executors.js";
import { workflowState } from "./state.js";

export function nodeRole(node) {
  return node?.type === "review" ? "review" : "execute";
}

export function nodeRoleLabel(node) {
  return nodeRole(node) === "review" ? "独立 Review" : "执行 + Review";
}

export function nodeNeedsReview(node) {
  if (nodeRole(node) === "review") return true;
  const mode = node?.review?.mode || node?.approval?.mode || "auto";
  return mode === "human" || mode === "ai";
}

export function approvalModeLabel(mode) {
  const labels = { auto: "自动通过", human: "人工验收", ai: "AI 验收" };
  return labels[mode] || mode || "自动通过";
}

export function normalizeNodeType(type) {
  return type === "review" ? "review" : "ai";
}


export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

export function parseTimestamp(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function nodePhaseLabel(status, phase = "") {
  if (status === "paused" && phase === "review") return "等待 Review";
  const labels = {
    idle: "未启动",
    pending: "等待中",
    running: "执行中",
    completed: "已完成",
    approved: "Review 通过",
    paused: "等待处理",
    failed: "执行失败",
    rejected: "Review 驳回",
  };
  return labels[status] || status;
}

function phaseStepState(stepId, node, runNode, displayStatus) {
  if (displayStatus === "idle") return "idle";
  if (stepId === "execute") {
    if (["failed"].includes(displayStatus)) return "failed";
    if (runNode?.artifact || ["paused", "completed", "approved", "rejected"].includes(displayStatus)) {
      return displayStatus === "running" ? "running" : "completed";
    }
    return displayStatus === "running" ? "running" : "pending";
  }
  if (!nodeNeedsReview(node)) return "skipped";
  if (["completed", "approved"].includes(displayStatus)) return "completed";
  if (displayStatus === "rejected") return "rejected";
  if (displayStatus === "paused" || runNode?.phase === "review") return "active";
  if (runNode?.artifact) return "pending";
  return "idle";
}

export function buildNodePhaseTrackHtml(node, runNode, displayStatus) {
  if (nodeRole(node) === "review") {
    const reviewState = displayStatus === "idle" ? "idle" : displayStatus;
    return `
      <div class="sm-phase-track">
        <span class="sm-phase review ${escapeHtml(reviewState)}">Review 验收</span>
      </div>
    `;
  }
  const executeState = phaseStepState("execute", node, runNode, displayStatus);
  const reviewState = nodeNeedsReview(node) ? phaseStepState("review", node, runNode, displayStatus) : "skipped";
  const reviewHtml =
    reviewState === "skipped"
      ? `<span class="sm-phase review skipped">Review · ${escapeHtml(approvalModeLabel(node.approval?.mode || "auto"))}</span>`
      : `<span class="sm-phase-arrow">→</span><span class="sm-phase review ${escapeHtml(reviewState)}">Review 验收</span>`;
  return `
    <div class="sm-phase-track">
      <span class="sm-phase execute ${escapeHtml(executeState)}">执行</span>
      ${reviewHtml}
    </div>
  `;
}

export function expectedOutputLabel(node) {
  if (nodeRole(node) === "review") return "审核决策 (approve / reject)";
  const primary = node.outputs?.primary || `${node.id}.md`;
  const structured = node.outputs?.structured;
  return structured ? `${primary} + ${structured}` : primary;
}

export function workflowDisplayOrder(workflow) {
  const initial = workflow.initial || workflow.nodes?.[0]?.id;
  const transitions = workflow.transitions || [];
  const order = [];
  const seen = new Set();
  const queue = initial ? [initial] : [];
  while (queue.length) {
    const nodeId = queue.shift();
    if (!nodeId || seen.has(nodeId)) continue;
    seen.add(nodeId);
    order.push(nodeId);
    for (const transition of transitions) {
      if (transition.from === nodeId && transition.when !== "rejected" && !seen.has(transition.to)) {
        queue.push(transition.to);
      }
    }
  }
  for (const node of workflow.nodes || []) {
    if (!seen.has(node.id)) order.push(node.id);
  }
  return order;
}

export function resolveNodeDisplayStatus(nodeId, runNode) {
  if (!workflowState.currentState?.run_id) return "idle";
  if (workflowState.currentState.current_node === nodeId && workflowState.currentState.status === "running") return "running";
  if (!runNode) return "pending";
  return runNode.status || "pending";
}

export function resolveNodeLifecycle(node, nodeIndex, runNode) {
  if (workflowState.nodeEditOpen && nodeIndex === workflowState.selectedNodeIndex) {
    return { key: "editing", label: "编辑中", className: "lifecycle-editing" };
  }
  if (!workflowState.currentState?.run_id) {
    return { key: "idle", label: "待运行", className: "lifecycle-idle" };
  }
  const displayStatus = resolveNodeDisplayStatus(node.id, runNode);
  if (displayStatus === "running") {
    return { key: "executing", label: "执行中", className: "lifecycle-executing" };
  }
  if (
    displayStatus === "paused" &&
    (runNode?.phase === "review" || nodeRole(node) === "review")
  ) {
    return { key: "reviewing", label: "Review 中", className: "lifecycle-reviewing" };
  }
  if (["completed", "approved"].includes(displayStatus)) {
    return { key: "done", label: "已完成", className: "lifecycle-done" };
  }
  if (displayStatus === "failed") {
    return { key: "failed", label: "执行失败", className: "lifecycle-failed" };
  }
  if (displayStatus === "rejected") {
    return { key: "rejected", label: "Review 驳回", className: "lifecycle-rejected" };
  }
  return { key: "pending", label: "等待中", className: "lifecycle-pending" };
}

export function nodeDurationMs(runNode, displayStatus) {
  const startedAt = parseTimestamp(runNode?.started_at);
  if (!startedAt) {
    if (displayStatus === "running") return 0;
    return null;
  }
  const finishedAt = parseTimestamp(runNode?.finished_at);
  const end = finishedAt || (displayStatus === "running" ? Date.now() : null);
  if (!end) return null;
  return Math.max(0, end - startedAt);
}

export function runDurationMs() {
  const startedAt = parseTimestamp(workflowState.currentState?.started_at);
  if (!startedAt) return null;
  return Math.max(0, Date.now() - startedAt);
}

export function outgoingTransitions(nodeId) {
  return (workflowState.editingWorkflow.transitions || []).filter((transition) => transition.from === nodeId);
}

export function branchTagsHtml(nodeId) {
  const branches = outgoingTransitions(nodeId).filter((transition) => transition.when !== "always");
  if (!branches.length) return "";
  const tags = branches.map((transition) => {
    const target = (workflowState.editingWorkflow.nodes || []).find((node) => node.id === transition.to);
    const targetName = target?.name || transition.to;
    return `<span class="sm-branch-tag ${escapeHtml(transition.when)}">${escapeHtml(transition.when)} → ${escapeHtml(targetName)}</span>`;
  });
  return `<div class="sm-branch-tags">${tags.join("")}</div>`;
}

export function transitionEdgeHtml(transition) {
  const edgeClass = transition.when === "approved"
    ? "approved"
    : transition.when === "rejected"
      ? "rejected"
      : "always";
  return `
    <div class="sm-edge ${edgeClass}">
      <div class="sm-edge-line"></div>
      <span class="sm-edge-label">${escapeHtml(transition.when)}</span>
    </div>
  `;
}

function nodeStatusNote(node, runNode, displayStatus) {
  if (runNode?.message) return runNode.message;
  if (displayStatus === "paused" && runNode?.phase === "review") {
    return "执行已完成，等待 Review 验收产出";
  }
  if (nodeRole(node) === "review" && ["idle", "pending", "paused"].includes(displayStatus)) {
    return "等待 Review 决策";
  }
  if (nodeNeedsReview(node) && displayStatus === "idle") {
    return `Review 模式 · ${approvalModeLabel(node.approval?.mode || "auto")}`;
  }
  return "";
}

export function buildStateMachineNodeHtml(node, runNode, displayStatus, nodeIndex = null) {
  const role = nodeRole(node);
  const roleLabel = nodeRoleLabel(node);
  const executorLabel = resolveExecutorLabel(node);
  const duration = nodeDurationMs(runNode, displayStatus);
  const artifact = runNode?.artifact ? runNode.artifact.replace(/^artifacts\//, "") : "-";
  const expected = expectedOutputLabel(node);
  const badges = [`<span class="node-badge ${role}">${escapeHtml(roleLabel)}</span>`];
  if (executorLabel) badges.push(`<span class="node-badge executor">${escapeHtml(executorLabel)}</span>`);
  const resolvedIndex =
    nodeIndex == null
      ? (workflowState.editingWorkflow.nodes || []).findIndex((item) => item.id === node.id)
      : nodeIndex;
  const lifecycle = resolveNodeLifecycle(node, resolvedIndex, runNode);
  badges.push(`<span class="node-badge lifecycle ${escapeHtml(lifecycle.className)}">${escapeHtml(lifecycle.label)}</span>`);
  const note = nodeStatusNote(node, runNode, displayStatus);
  const noteHtml = note ? `<div class="sm-node-note">${escapeHtml(note)}</div>` : "";
  return `
    <div class="sm-node-head">
      <div class="sm-node-title">
        <div class="sm-node-name-row">
          <strong>${escapeHtml(node.name || node.id)}</strong>
          <div class="node-meta sm-node-badges">${badges.join("")}</div>
        </div>
        <div class="node-id sm-node-id">${escapeHtml(node.id)}</div>
      </div>
      <span class="status ${escapeHtml(displayStatus)}">${escapeHtml(nodePhaseLabel(displayStatus, runNode?.phase || ""))}</span>
    </div>
    ${buildNodePhaseTrackHtml(node, runNode, displayStatus)}
    <div class="sm-node-stats">
      <span class="sm-stat">
        <span class="sm-stat-k">耗时</span>
        <span class="sm-stat-v">${duration == null ? "-" : formatDuration(duration)}</span>
      </span>
      <span class="sm-stat">
        <span class="sm-stat-k">预期</span>
        <span class="sm-stat-v">${escapeHtml(expected)}</span>
      </span>
      <span class="sm-stat">
        <span class="sm-stat-k">实际</span>
        <span class="sm-stat-v">${escapeHtml(artifact)}</span>
      </span>
    </div>
    ${noteHtml}
    ${branchTagsHtml(node.id)}
  `;
}

export function buildNodeCardHtml(node, options = {}) {
  const displayStatus = options.status || (workflowState.currentState?.run_id ? "idle" : node.approval?.mode || "auto");
  if (workflowState.currentState?.run_id || options.status) {
    const runNode = workflowState.currentState?.nodes?.[node.id] || null;
    const displayStatus = options.status || resolveNodeDisplayStatus(node.id, runNode);
    return buildStateMachineNodeHtml(node, runNode, displayStatus);
  }
  const role = nodeRole(node);
  const roleLabel = nodeRoleLabel(node);
  const executorLabel = resolveExecutorLabel(node);
  const subtitle =
    role === "review"
      ? `${node.approval?.mode || "human"} 审批卡点`
      : node.skill
        ? `Skill · ${node.skill}`
        : "未绑定 Skill";
  const badges = [`<span class="node-badge ${role}">${escapeHtml(roleLabel)}</span>`];
  if (executorLabel) {
    badges.push(`<span class="node-badge executor">${escapeHtml(executorLabel)}</span>`);
  }
  if (node.type === "skill") {
    badges.push(`<span class="node-badge executor">legacy skill type</span>`);
  }
  const statusHtml = options.status
    ? `<span class="status ${escapeHtml(options.status)}">${escapeHtml(options.status)}</span>`
    : `<span class="status">${escapeHtml(node.approval?.mode || "auto")}</span>`;
  const messageHtml = options.message
    ? `<div class="node-id">${escapeHtml(options.message)}</div>`
    : `<div class="node-id">${escapeHtml(subtitle)}</div>`;
  return `
    <div class="node-title">
      <div class="node-head">
        <strong>${escapeHtml(node.name || node.id)}</strong>
      </div>
      <div class="node-meta">${badges.join("")}</div>
      ${messageHtml}
    </div>
    ${statusHtml}
  `;
}
