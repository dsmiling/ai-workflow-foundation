import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { workflowState } from "./state.js";
import { saveWorkflow } from "./catalog.js";
import { setState, openArtifact } from "./run.js";
import { nodeRole, nodePhaseLabel, expectedOutputLabel } from "./transitions.js";
import {
  applyNodeTestExecutorControls,
  readExecutorPayload,
  readGlobalExecutorPayload,
  syncNodeTestToWorkflow,
} from "../core/executors.js";
import { fetchNodeResult, renderChangelist } from "./changelist.js";
import { renderNodeInspector } from "./inspector.js";
import { currentNode } from "./node-form.js";

let lastTestResult = null;

function resolveTestExecutorPayload(node) {
  if ($("nodeTestExecutor")?.value) {
    return readExecutorPayload($("nodeTestExecutor"), $("nodeTestAgentProvider"));
  }
  if (node?.test_executor || node?.test_agent_provider) {
    return readExecutorPayload(null, null, {
      executor: node.test_executor,
      agent_provider: node.test_agent_provider,
    });
  }
  if (node?.executor || node?.agent_provider) {
    return readExecutorPayload(null, null, {
      executor: node.executor,
      agent_provider: node.agent_provider,
    });
  }
  return readGlobalExecutorPayload();
}

function evaluateNodeTest(node, nodeState) {
  const status = nodeState?.status || "unknown";
  const phase = nodePhaseLabel(status, nodeState?.phase || "");
  const artifactRef = nodeState?.artifact || "";
  const artifactName = artifactRef ? artifactRef.replace(/^artifacts\//, "") : "";
  const expected = expectedOutputLabel(node);
  const isReview = nodeRole(node) === "review";

  if (status === "failed" || status === "rejected") {
    return {
      passed: false,
      tone: "fail",
      title: status === "rejected" ? "Review 未通过" : "测试未通过",
      detail: nodeState?.message || `${phase}，请检查 Skill 配置与输入。`,
      artifactRef: artifactRef,
    };
  }

  if (isReview) {
    if (status === "paused") {
      return {
        passed: true,
        tone: "warn",
        title: "已到达 Review 卡点",
        detail: "上游节点已执行完成，当前节点等待 Review 决策。",
        artifactRef: "",
      };
    }
    return {
      passed: false,
      tone: "fail",
      title: "Review 节点未就绪",
      detail: `当前状态：${phase}。请先执行上游节点。`,
      artifactRef: "",
    };
  }

  if (status === "paused" && nodeState?.phase === "review") {
    return {
      passed: true,
      tone: "warn",
      title: "执行完成，等待 Review",
      detail: nodeState?.message || "产出已生成，请验收 artifact 后再继续。",
      artifactRef,
    };
  }

  const success = status === "completed";
  if (!success) {
    return {
      passed: false,
      tone: status === "running" ? "running" : "fail",
      title: status === "running" ? "仍在执行" : "测试未完成",
      detail: nodeState?.message || `当前状态：${phase}。`,
      artifactRef: artifactRef,
    };
  }

  if (!artifactRef) {
    return {
      passed: false,
      tone: "fail",
      title: "执行完成但无产出",
      detail: `预期产物：${expected}`,
      artifactRef: "",
    };
  }

  const primary = node.outputs?.primary || `${node.id}.md`;
  const artifactMatches = artifactName === primary || artifactName.endsWith(`/${primary}`) || artifactName.includes(primary);
  return {
    passed: artifactMatches,
    tone: artifactMatches ? "pass" : "warn",
    title: artifactMatches ? "测试通过" : "已产出但文件名不匹配",
    detail: artifactMatches
      ? `已生成 ${artifactName}`
      : `实际 ${artifactName}，预期 ${primary}`,
    artifactRef,
  };
}

function renderTestResultCard(result) {
  if (!result) {
    $("nodeTestResult").className = "node-test-result";
    $("nodeTestResult").innerHTML = '<div class="muted">尚未运行测试。</div>';
    $("nodeTestArtifactPreview").hidden = true;
    $("nodeTestArtifactPreview").value = "";
    $("nodeTestOpenArtifactBtn").disabled = true;
    return;
  }

  $("nodeTestResult").className = `node-test-result tone-${result.evaluation.tone}`;
  const lines = [
    `<div class="node-test-result-title">${escapeHtml(result.evaluation.title)}</div>`,
    `<div class="node-test-result-detail">${escapeHtml(result.evaluation.detail)}</div>`,
  ];
  if (result.runId && result.runId !== "-") {
    lines.push(`<div class="node-test-result-meta muted">${escapeHtml(result.runId)}</div>`);
  }
  $("nodeTestResult").innerHTML = lines.join("");
  $("nodeTestOpenArtifactBtn").disabled = !result.evaluation.artifactRef;
  if (result.preview) {
    $("nodeTestArtifactPreview").hidden = false;
    $("nodeTestArtifactPreview").value = result.preview;
  } else {
    $("nodeTestArtifactPreview").hidden = true;
    $("nodeTestArtifactPreview").value = "";
  }
}

export function renderNodeTestPanel() {
  const card = $("nodeInspectorCard");
  if (!card) return;
  const node = currentNode();
  const inOverview = !workflowState.nodeEditOpen;
  const testSection = card.querySelector(".inspector-section-label");
  const testControls = [
    $("nodeTestExecutor")?.closest(".inspector-field"),
    $("nodeTestAgentProviderField"),
    $("nodeTestEnsureUpstream")?.closest(".inspector-check"),
    $("nodeTestRunBtn")?.closest(".inspector-actions"),
    $("nodeTestResult"),
    $("nodeTestArtifactPreview"),
  ].filter(Boolean);
  const showTest = inOverview && Boolean(node) && workflowState.nodeDetailTab !== "review";
  testControls.forEach((el) => {
    el.hidden = !showTest;
  });
  if (testSection) testSection.hidden = !showTest;

  if (!showTest) {
    renderTestResultCard(null);
    return;
  }

  const isReview = nodeRole(node) === "review";
  $("nodeTestSkillWarn").hidden = isReview || Boolean(node.skill);
  applyNodeTestExecutorControls(node);
  $("nodeTestEnsureUpstream").checked = true;
  $("nodeTestEnsureUpstream").disabled = isReview;

  if (lastTestResult?.nodeId === node.id) {
    renderTestResultCard(lastTestResult);
  } else {
    renderTestResultCard(null);
  }
}

export async function runNodeTest(options = {}) {
  const { stayOnView = false, source = "overview" } = options;
  const node = currentNode();
  if (!node) return null;

  if (nodeRole(node) !== "review" && !node.skill) {
    setLog("当前节点未绑定 Skill，无法测试。");
    return null;
  }

  const runBtn = source === "overview" ? $("nodeTestRunBtn") : $("testNodeBtn");
  if (runBtn) runBtn.disabled = true;

  try {
    const runId = $("runId").value.trim();
    const executorPayload = resolveTestExecutorPayload(node);
    const ensureUpstream = $("nodeTestEnsureUpstream") ? $("nodeTestEnsureUpstream").checked : true;
    let payload;

    if (runId) {
      payload = await api(`/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(node.id)}/run`, {
        method: "POST",
        body: JSON.stringify({ ...executorPayload, ensure_upstream: ensureUpstream }),
      });
    } else {
      if (workflowState.currentWorkflowEditable) {
        await saveWorkflow();
      }
      payload = await api("/runs", {
        method: "POST",
        body: JSON.stringify({
          workflow_id: workflowState.editingWorkflow.id,
          until_node: node.id,
          ...executorPayload,
        }),
      });
    }

    const nodeState = payload.state.nodes[node.id] || {};
    const evaluation = evaluateNodeTest(node, nodeState);
    let preview = "";
    if (evaluation.artifactRef) {
      try {
        const artifactPayload = await api(
          `/runs/${encodeURIComponent(payload.state.run_id)}/artifact?ref=${encodeURIComponent(evaluation.artifactRef)}`,
        );
        preview = artifactPayload.content || "";
      } catch {
        preview = "";
      }
    }

    lastTestResult = {
      nodeId: node.id,
      runId: payload.state.run_id,
      nodeState,
      evaluation,
      preview,
      result: nodeState.result || null,
    };

    setState(payload.state);
    renderNodeTestPanel();
    renderNodeInspector();

    const logPrefix = evaluation.passed ? "节点测试通过" : "节点测试完成";
    setLog(`${logPrefix}: ${node.id} -> ${nodeState.status || "unknown"}`);

    if (!stayOnView && source === "edit") {
      const { setWorkflowView } = await import("./inspector.js");
      setWorkflowView("runs");
      if (evaluation.artifactRef) {
        await openArtifact(evaluation.artifactRef);
      }
    }

    return lastTestResult;
  } catch (error) {
    setLog(error.message);
    lastTestResult = {
      nodeId: node.id,
      runId: $("runId").value.trim() || "-",
      nodeState: { status: "failed", message: error.message },
      evaluation: {
        passed: false,
        tone: "fail",
        title: "测试失败",
        detail: error.message,
        artifactRef: "",
      },
      preview: "",
    };
    renderTestResultCard(lastTestResult);
    return null;
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

export function initNodeTestPanel() {
  for (const id of ["nodeTestExecutor", "nodeTestAgentProvider"]) {
    $(id)?.addEventListener("change", () => {
      syncNodeTestToWorkflow(currentNode());
    });
  }

  $("nodeTestRunBtn")?.addEventListener("click", () => {
    runNodeTest({ stayOnView: true, source: "overview" }).catch((error) => setLog(error.message));
  });

  $("nodeTestOpenArtifactBtn")?.addEventListener("click", async () => {
    const ref = lastTestResult?.evaluation?.artifactRef;
    if (!ref) return;
    try {
      await openArtifact(ref);
      const { setWorkflowView } = await import("./inspector.js");
      setWorkflowView("runs");
    } catch (error) {
      setLog(error.message);
    }
  });
}
