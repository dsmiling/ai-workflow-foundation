import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { workflowState } from "./state.js";
import {
  nodeRole,
  expectedOutputLabel,
  approvalModeLabel,
  nodeNeedsReview,
  resolveNodeDisplayStatus,
  resolveNodeLifecycle,
} from "./transitions.js";
import { resolveExecutorLabel } from "../core/executors.js";
import { currentNode, setNodeDetailTab, setNodeEditTab, syncNodeFormToWorkflow } from "./node-form.js";
import { expectedReviewLabel, normalizeNodeReview, reviewChecklistText } from "./node-review.js";
import { renderNodeTestPanel } from "./node-test.js";
import { loadState, openArtifact } from "./run.js";
import { fetchNodeResult, renderChangelist } from "./changelist.js";
import { renderNodeIteratePanel } from "./node-iterate.js";

function renderKvRow(key, value, { tone = "" } = {}) {
  const toneClass = tone ? ` inspector-kv-v--${tone}` : "";
  return `<div class="inspector-kv-row"><span class="inspector-kv-k">${escapeHtml(key)}</span><span class="inspector-kv-v${toneClass}">${escapeHtml(value)}</span></div>`;
}

function renderExecuteOverview(node) {
  const executor = resolveExecutorLabel(node) || "默认";
  const skill = node.skill || "未绑定";
  const rows = [
    renderKvRow("名称", node.name || node.id),
    renderKvRow("ID", node.id, { tone: "code" }),
    renderKvRow("Skill", skill, { tone: node.skill ? "" : "muted" }),
    renderKvRow("引擎", executor, { tone: executor === "默认" ? "muted" : "" }),
    renderKvRow("预期产出", expectedOutputLabel(node), { tone: "code" }),
  ];
  $("nodeSelectionSummary").innerHTML = rows.join("");
}

function renderReviewOverview(node) {
  const review = normalizeNodeReview(node);
  const runNode = workflowState.currentState?.nodes?.[node.id] || null;
  const rows = [
    ["Review 模式", approvalModeLabel(review.mode)],
    ["Review 级别", review.level],
    ["Review Skill", review.skill || "无"],
    ["验收对象", expectedReviewLabel(node)],
  ];
  if (review.criteria) rows.push(["验收标准", review.criteria]);
  if (review.checklist?.length) rows.push(["检查清单", reviewChecklistText(review.checklist)]);
  if (runNode?.artifact) rows.push(["当前产出", runNode.artifact.replace(/^artifacts\//, "")]);
  if (runNode?.message) rows.push(["运行消息", runNode.message]);

  $("nodeReviewSummary").innerHTML = rows
    .map(([key, value]) => renderKvRow(key, value))
    .join("");

  const lifecycle = resolveNodeLifecycle(node, workflowState.selectedNodeIndex, runNode);
  const canReview =
    workflowState.currentState?.run_id &&
    lifecycle.key === "reviewing" &&
    (nodeNeedsReview(node) || nodeRole(node) === "review");
  $("nodeReviewRuntimePanel").hidden = !canReview;
  if (canReview) {
    populateReviewRejectTargets(node);
  }
}

function populateReviewRejectTargets(node) {
  const select = $("nodeReviewRejectTarget");
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

async function renderNodeChangelist(node) {
  const container = $("nodeChangelist");
  if (!container || nodeRole(node) === "review") return;
  const runId = workflowState.currentState?.run_id || $("runId")?.value?.trim();
  const runNode = workflowState.currentState?.nodes?.[node.id];
  let result = runNode?.result || null;
  if (!result && runId) {
    result = await fetchNodeResult(runId, node.id);
  }
  renderChangelist(container, result, {
    onAssetClick: async (ref) => {
      try {
        await openArtifact(ref);
        setWorkflowView("runs");
      } catch (error) {
        setLog(error.message);
      }
    },
  });
}

export function renderWorkflowInspector() {
  $("workflowSelectionView").hidden = workflowState.workflowEditOpen;
  $("workflowEditView").hidden = !workflowState.workflowEditOpen;
  if (!workflowState.editingWorkflow?.id) {
    $("workflowSelectionSummary").textContent = "暂无选中的工作流。";
    return;
  }
  if (!workflowState.workflowEditOpen) {
    const meta = $("workflowMeta").textContent || "";
    const lines = [
      workflowState.editingWorkflow.name || workflowState.editingWorkflow.id,
      `ID · ${workflowState.editingWorkflow.id}`,
      `节点数 · ${workflowState.editingWorkflow.nodes?.length || 0}`,
      `转移数 · ${workflowState.editingWorkflow.transitions?.length || 0}`,
      `初始节点 · ${workflowState.editingWorkflow.initial || workflowState.editingWorkflow.nodes?.[0]?.id || "-"}`,
      meta,
    ];
    if (workflowState.currentWorkflowPath) lines.push(`路径 · ${workflowState.currentWorkflowPath}`);
    $("workflowSelectionSummary").innerHTML = lines.map((line) => `<div>${escapeHtml(line)}</div>`).join("");
  }
  if ($("workflowPage").dataset.workflowView === "workflows") {
    const titles = workflowState.workflowEditOpen
      ? ["工作流详情", "编辑当前工作流的基础信息。"]
      : ["工作流概览", "单击选中工作流，双击进入节点编排。"];
    $("inspectorTitle").textContent = titles[0];
    $("inspectorSubtitle").textContent = titles[1];
  }
}

export function setWorkflowView(view) {
  $("workflowPage").dataset.workflowView = view;
  document.querySelectorAll(".context-tab[data-workflow-view]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-workflow-view") === view);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.getAttribute("data-view-panel") === view);
  });
  document.querySelectorAll("[data-inspector-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.getAttribute("data-inspector-panel") === view);
  });
  const titles = {
    workflows: workflowState.workflowEditOpen
      ? ["工作流详情", "编辑当前工作流的基础信息。"]
      : ["工作流概览", "单击选中工作流，双击进入节点编排。"],
    nodes: workflowState.nodeEditOpen
      ? ["节点详情", "编辑当前选中的节点。"]
      : ["节点概览", "单击选中节点，双击进入编辑。"],
    runs: ["运行详情", "处理当前运行、审核和版本。"],
  };
  const [title, subtitle] = titles[view] || titles.nodes;
  $("inspectorTitle").textContent = title;
  $("inspectorSubtitle").textContent = subtitle;
  if (view === "workflows") renderWorkflowInspector();
  if (view === "nodes") renderNodeInspector();
}

export function renderNodeInspector() {
  const node = currentNode();
  $("nodeSelectionView").hidden = workflowState.nodeEditOpen;
  $("nodeEditView").hidden = !workflowState.nodeEditOpen;
  if (!node) {
    $("nodeSelectionSummary").innerHTML = '<div class="muted">当前工作流没有节点。</div>';
    const executeInfoLabel = $("nodeOverviewExecutePanel")?.querySelector(".node-overview-section");
    if (executeInfoLabel) executeInfoLabel.hidden = true;
    renderNodeTestPanel();
    return;
  }

  if (workflowState.nodeEditOpen) {
    setNodeEditTab(workflowState.nodeDetailTab, { persist: false });
  } else {
    if ($("nodeType")) $("nodeType").value = node.type === "review" ? "review" : "ai";
    const isStandaloneReview = nodeRole(node) === "review";
    document.querySelectorAll("[data-node-detail-tab]").forEach((button) => {
      const tab = button.getAttribute("data-node-detail-tab");
      button.hidden = isStandaloneReview && tab === "execute";
    });
    if (!isStandaloneReview) renderExecuteOverview(node);
    renderReviewOverview(node);
    void renderNodeChangelist(node);
    const executeInfoLabel = $("nodeOverviewExecutePanel")?.querySelector(".node-overview-section");
    if (executeInfoLabel) executeInfoLabel.hidden = isStandaloneReview;
    const reviewInfoLabel = $("nodeOverviewReviewPanel")?.querySelector(".node-overview-section");
    if (reviewInfoLabel) reviewInfoLabel.hidden = false;
    setNodeDetailTab(isStandaloneReview ? "review" : workflowState.nodeDetailTab, { persist: false });
  }

  renderNodeTestPanel();
  if (!workflowState.nodeEditOpen && workflowState.nodeDetailTab === "iterate") {
    void renderNodeIteratePanel();
  }

  if ($("workflowPage").dataset.workflowView === "nodes") {
    const tabLabel =
      workflowState.nodeDetailTab === "review"
        ? "Review"
        : workflowState.nodeDetailTab === "iterate"
          ? "迭代"
          : "执行";
    const titles = workflowState.nodeEditOpen
      ? [`节点详情 · ${tabLabel}`, "切换「执行配置 / Review 配置」编辑节点。"]
      : [`节点概览 · ${tabLabel}`, "切换查看执行详情或 Review 详情。"];
    $("inspectorTitle").textContent = titles[0];
    $("inspectorSubtitle").textContent = titles[1];
  }
}

export async function submitNodeReview(decision) {
  const node = currentNode();
  const runId = $("runId")?.value?.trim();
  if (!node || !runId) {
    setLog("请先加载运行后再进行 Review。");
    return;
  }
  const body = {
    node_id: node.id,
    decision,
    feedback: $("nodeReviewFeedback")?.value || "",
  };
  const targetNode = $("nodeReviewRejectTarget")?.value?.trim();
  if (decision === "reject" && targetNode) body.target_node = targetNode;
  try {
    const payload = await api(`/runs/${encodeURIComponent(runId)}/reviews`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setLog(decision === "approve" ? "Review 已通过" : `Review 已驳回${payload.change_id ? ` · ${payload.change_id}` : ""}`);
    await api(`/runs/${encodeURIComponent(runId)}/resume`, { method: "POST", body: "{}" }).catch(() => null);
    await loadState();
    renderNodeInspector();
  } catch (error) {
    setLog(error.message);
  }
}

export function initNodeInspectorTabs() {
  document.querySelectorAll("[data-node-detail-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      setNodeDetailTab(button.getAttribute("data-node-detail-tab"), { persist: true });
      renderNodeInspector();
      if (button.getAttribute("data-node-detail-tab") === "iterate") {
        void renderNodeIteratePanel();
      }
    });
  });
  document.querySelectorAll("[data-node-edit-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      if (workflowState.nodeEditOpen) {
        try {
          syncNodeFormToWorkflow();
        } catch (error) {
          setLog(error.message);
          return;
        }
      }
      setNodeEditTab(button.getAttribute("data-node-edit-tab"), { persist: true });
      renderNodeInspector();
    });
  });
  $("nodeReviewApproveBtn")?.addEventListener("click", () => {
    submitNodeReview("approve").catch((error) => setLog(error.message));
  });
  $("nodeReviewRejectBtn")?.addEventListener("click", () => {
    submitNodeReview("reject").catch((error) => setLog(error.message));
  });
}
