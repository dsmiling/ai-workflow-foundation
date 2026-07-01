import { $ } from "../core/dom.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { refreshSkillCatalog } from "../settings/skills.js";
import {
  blankWorkflow,
  cloneWorkflowToWorkspace,
  defaultNode,
  openWorkflowEditor,
  openWorkflowNodes,
  populateWorkflowForm,
  refreshWorkflowCatalog,
  renderWorkflowCards,
  saveWorkflow,
  selectWorkflow,
  syncLinearTransitions,
  syncWorkflowFormToWorkflow,
} from "./catalog.js";
import { renderEditorNodes, openNodeEditor } from "./editor.js";
import { setWorkflowView, renderWorkflowInspector, renderNodeInspector, initNodeInspectorTabs } from "./inspector.js";
import { renderNodeForm, syncNodeFormToWorkflow, refreshSkillPreview, applyNodeTypeChange } from "./node-form.js";
import {
  loadState,
  openArtifact,
  refreshChanges,
  refreshRevisions,
  setState,
} from "./run.js";
import { workflowState } from "./state.js";
import { applyDefaultExecutorControls, readGlobalExecutorPayload, refreshExecutorCatalog } from "../core/executors.js";
import { initNodeTestPanel, runNodeTest } from "./node-test.js";
import { initNodeInputsEditor } from "./node-inputs-editor.js";
import { initNodeIteratePanel, renderNodeIteratePanel } from "./node-iterate.js";
import { initWorkflowAssist } from "./assist.js";
import { initWorkflowShellLayout } from "./shell-layout.js";

let outputsAdvancedMode = false;

function initNodeOutputsAdvancedToggle() {
  const toggle = $("nodeOutputsAdvancedToggle");
  if (!toggle || toggle.dataset.bound) return;
  toggle.dataset.bound = "1";
  toggle.addEventListener("click", () => {
    outputsAdvancedMode = !outputsAdvancedMode;
    const preview = $("nodeOutputContractPreview");
    const textarea = $("nodeOutputs");
    if (preview) preview.hidden = outputsAdvancedMode;
    if (textarea) textarea.hidden = !outputsAdvancedMode;
    toggle.textContent = outputsAdvancedMode ? "契约预览" : "高级 · JSON";
  });
}

export function initWorkflow() {
  $("workflowSelect").addEventListener("change", () => {
    selectWorkflow($("workflowSelect").value).catch((error) => setLog(error.message));
  });

  $("newWorkflowBtn").addEventListener("click", () => {
    if (workflowState.workflowEditOpen) syncWorkflowFormToWorkflow();
    if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
    blankWorkflow();
    workflowState.currentWorkflowEditable = true;
    workflowState.currentWorkflowPath = "";
    workflowState.selectedNodeIndex = 0;
    workflowState.workflowEditOpen = false;
    workflowState.nodeEditOpen = true;
    $("wfId").readOnly = false;
    $("workflowMeta").textContent = "workspace · 新建未保存";
    populateWorkflowForm();
    renderEditorNodes();
    renderNodeForm();
    renderNodeInspector();
    renderWorkflowCards();
    renderWorkflowInspector();
    setWorkflowView("nodes");
    const firstNode = workflowState.editingWorkflow.nodes?.[0];
    if (firstNode?.skill) {
      setLog(`已创建单节点工作流草稿，默认 Skill：${firstNode.skill}。保存前可继续编辑节点。`);
    } else {
      setLog("已创建单节点工作流草稿。请为节点选择 Skill 后再保存。");
    }
  });

  $("cloneWorkflowBtn").addEventListener("click", async () => {
    cloneWorkflowToWorkspace();
    setLog("已复制到工作区草稿，请保存。");
  });

  $("saveWorkflowBtn").addEventListener("click", () => saveWorkflow().catch((error) => setLog(error.message)));
  $("deleteWorkflowBtn").addEventListener("click", async () => {
    const workflowId = $("workflowSelect").value;
    if (!workflowId) return;
    await api(`/workflows/${encodeURIComponent(workflowId)}`, { method: "DELETE" });
    await refreshWorkflowCatalog();
    setLog(`Deleted ${workflowId}`);
  });

  $("addNodeBtn").addEventListener("click", () => {
    if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
    workflowState.editingWorkflow.nodes.push(defaultNode());
    workflowState.selectedNodeIndex = workflowState.editingWorkflow.nodes.length - 1;
    syncLinearTransitions();
    openNodeEditor(workflowState.selectedNodeIndex);
  });

  $("removeNodeBtn").addEventListener("click", () => {
    if (workflowState.editingWorkflow.nodes.length <= 1) return;
    if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
    workflowState.editingWorkflow.nodes.splice(workflowState.selectedNodeIndex, 1);
    workflowState.selectedNodeIndex = Math.max(0, workflowState.selectedNodeIndex - 1);
    workflowState.nodeEditOpen = false;
    syncLinearTransitions();
    renderEditorNodes();
    renderNodeInspector();
  });

  $("moveUpBtn").addEventListener("click", () => {
    if (workflowState.selectedNodeIndex <= 0) return;
    if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
    const [node] = workflowState.editingWorkflow.nodes.splice(workflowState.selectedNodeIndex, 1);
    workflowState.selectedNodeIndex -= 1;
    workflowState.editingWorkflow.nodes.splice(workflowState.selectedNodeIndex, 0, node);
    syncLinearTransitions();
    renderEditorNodes();
    if (workflowState.nodeEditOpen) renderNodeForm();
    else renderNodeInspector();
  });

  $("moveDownBtn").addEventListener("click", () => {
    if (workflowState.selectedNodeIndex >= workflowState.editingWorkflow.nodes.length - 1) return;
    if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
    const [node] = workflowState.editingWorkflow.nodes.splice(workflowState.selectedNodeIndex, 1);
    workflowState.selectedNodeIndex += 1;
    workflowState.editingWorkflow.nodes.splice(workflowState.selectedNodeIndex, 0, node);
    syncLinearTransitions();
    renderEditorNodes();
    if (workflowState.nodeEditOpen) renderNodeForm();
    else renderNodeInspector();
  });

  initNodeTestPanel();
  initNodeInputsEditor();
  initNodeOutputsAdvancedToggle();
  initNodeIteratePanel();
  initNodeInspectorTabs();
  initWorkflowShellLayout();
  initWorkflowAssist();

  $("testNodeBtn").addEventListener("click", async () => {
    try {
      if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
      await runNodeTest({ stayOnView: false, source: "edit" });
    } catch (error) {
      setLog(error.message);
    }
  });

  $("editWorkflowInfoBtn").addEventListener("click", () => {
    openWorkflowEditor(workflowState.editingWorkflow.id).catch((error) => setLog(error.message));
  });

  $("workflowCards").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    if ($("workflowPage").dataset.workflowView !== "workflows" || workflowState.workflowEditOpen) return;
    event.preventDefault();
    openWorkflowNodes(workflowState.editingWorkflow.id).catch((error) => setLog(error.message));
  });

  $("editorNodes").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    if ($("workflowPage").dataset.workflowView !== "nodes" || workflowState.nodeEditOpen) return;
    event.preventDefault();
    openNodeEditor(workflowState.selectedNodeIndex);
  });

  $("nodeType").addEventListener("change", () => {
    try {
      applyNodeTypeChange($("nodeType").value);
      renderEditorNodes();
      renderNodeInspector();
      if (workflowState.nodeEditOpen) renderNodeForm();
    } catch (error) {
      setLog(error.message);
    }
  });

  ["wfRoot", "nodeId", "nodeName", "nodeSkill", "nodeExecutor", "nodeAgentProvider", "nodeInputs", "nodeOutputs", "approvalMode", "approvalLevel", "nodeRejectTarget", "nodeReviewSkill", "nodeReviewInputs", "nodeReviewCriteria", "nodeReviewChecklist"].forEach((id) => {
    $(id).addEventListener("input", () => {
      try {
        syncNodeFormToWorkflow();
        renderEditorNodes();
        if (id === "nodeSkill") refreshSkillPreview();
      } catch (error) {
        setLog(error.message);
      }
    });
    $(id).addEventListener("change", () => {
      try {
        syncNodeFormToWorkflow();
        renderEditorNodes();
        if (id === "nodeSkill") refreshSkillPreview();
        if (id === "nodeSkill" && workflowState.nodeEditOpen) renderNodeForm();
      } catch (error) {
        setLog(error.message);
      }
    });
  });

  document.querySelectorAll(".context-tab[data-workflow-view]").forEach((button) => {
    button.addEventListener("click", () => setWorkflowView(button.getAttribute("data-workflow-view")));
  });

  $("initBtn").addEventListener("click", async () => {
    const payload = await api("/init", { method: "POST", body: "{}" });
    setLog(payload.workspace);
  });

  $("validateBtn").addEventListener("click", async () => {
    syncNodeFormToWorkflow();
    const payload = await api("/validate", {
      method: "POST",
      body: JSON.stringify({
        workflow_id: workflowState.editingWorkflow.id,
        workflow: workflowState.currentWorkflowPath,
      }),
    });
    const report = payload.report;
    setLog(report.ok ? "Validation passed" : `Validation failed: ${report.errors.join("; ")}`);
  });

  $("runBtn").addEventListener("click", async () => {
    const payload = await api("/runs", {
      method: "POST",
      body: JSON.stringify({ workflow_id: workflowState.editingWorkflow.id, ...readGlobalExecutorPayload() }),
    });
    setState(payload.state);
    setWorkflowView("nodes");
    setLog(`Started ${payload.state.run_id}`);
  });

  $("loadBtn").addEventListener("click", () => loadState().catch((error) => setLog(error.message)));
  $("resumeBtn").addEventListener("click", async () => {
    const runId = $("runId").value.trim();
    const payload = await api(`/runs/${encodeURIComponent(runId)}/resume`, {
      method: "POST",
      body: JSON.stringify(readGlobalExecutorPayload()),
    });
    setState(payload.state);
  });
  $("rerunBtn").addEventListener("click", async () => {
    const runId = $("runId").value.trim();
    const payload = await api(`/runs/${encodeURIComponent(runId)}/rerun`, {
      method: "POST",
      body: JSON.stringify({ node_id: $("rerunNode").value, ...readGlobalExecutorPayload() }),
    });
    setState(payload.state);
  });

  $("artifactBtn").addEventListener("click", () => openArtifact($("artifactSelect").value).catch((error) => setLog(error.message)));
  $("artifactSaveBtn").addEventListener("click", async () => {
    const runId = $("runId").value.trim();
    if (!runId || !workflowState.currentArtifactRef) {
      setLog("Open an artifact before saving.");
      return;
    }
    const payload = await api(`/runs/${encodeURIComponent(runId)}/artifact`, {
      method: "PUT",
      body: JSON.stringify({ ref: workflowState.currentArtifactRef, content: $("artifact").value }),
    });
    if (payload.state) setState(payload.state);
    $("artifactMeta").textContent = `Saved ${workflowState.currentArtifactRef}`;
    setLog(`Saved ${workflowState.currentArtifactRef}`);
  });

  $("approveBtn").addEventListener("click", async () => {
    const runId = $("runId").value.trim();
    await api(`/runs/${encodeURIComponent(runId)}/reviews`, {
      method: "POST",
      body: JSON.stringify({
        node_id: $("reviewNode").value,
        decision: "approve",
        feedback: $("feedback").value,
      }),
    });
    setLog("Review approved");
    await loadState();
  });

  $("rejectBtn").addEventListener("click", async () => {
    const runId = $("runId").value.trim();
    const body = {
      node_id: $("reviewNode").value,
      decision: "reject",
      feedback: $("feedback").value,
    };
    const targetNode = $("targetNode").value.trim();
    if (targetNode) body.target_node = targetNode;
    const payload = await api(`/runs/${encodeURIComponent(runId)}/reviews`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setLog(`Rejected. Change request ${payload.change_id}`);
    await refreshChanges();
  });

  $("commitBtn").addEventListener("click", async () => {
    const runId = $("runId").value.trim();
    const payload = await api(`/runs/${encodeURIComponent(runId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({ message: $("commitMessage").value }),
    });
    setLog(`Created ${payload.revision_id}`);
    await refreshRevisions();
  });

  return Promise.all([
    api("/health").then((payload) => {
      $("health").textContent = `API ${payload.status}`;
    }),
    refreshExecutorCatalog().then(() => {
      applyDefaultExecutorControls();
    }),
    refreshSkillCatalog(),
    refreshWorkflowCatalog("unity_activity_create"),
  ]).catch((error) => {
    $("health").textContent = error.message;
    setLog(error.message);
  });
}
