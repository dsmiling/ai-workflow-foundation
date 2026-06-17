import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { workflowState } from "./state.js";
import { currentNode } from "./node-form.js";
import { nodeRole } from "./transitions.js";
import { renderChangelist } from "./changelist.js";
import { loadState, openArtifact, setState } from "./run.js";
import { renderNodeInspector, setWorkflowView } from "./inspector.js";
import { readGlobalExecutorPayload } from "../core/executors.js";

function aggregateSessionChangelist(turns) {
  const merged = new Map();
  for (const turn of turns || []) {
    for (const change of turn.result?.changes || []) {
      if (change?.target) merged.set(change.target, change);
    }
  }
  return Array.from(merged.values());
}

export async function renderNodeIteratePanel() {
  const panel = $("nodeOverviewIteratePanel");
  if (!panel) return;
  const node = currentNode();
  const runId = workflowState.currentState?.run_id || $("runId")?.value?.trim();
  if (!node || nodeRole(node) === "review" || !runId) {
    panel.innerHTML = '<div class="muted">加载运行后可在迭代 Tab 多轮 refine 节点产物。</div>';
    return;
  }

  let sessionPayload;
  try {
    sessionPayload = await api(`/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(node.id)}/session`);
  } catch {
    panel.innerHTML = '<div class="muted">尚无 Session。先运行节点测试创建 Turn 1。</div>';
    return;
  }

  const session = sessionPayload.session;
  const turnsPayload = await api(
    `/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(node.id)}/session/turns`,
  ).catch(() => ({ turns: [] }));
  const turns = turnsPayload.turns || [];
  const sessionChanges = aggregateSessionChangelist(turns);

  const turnLines = turns
    .map(
      (turn) =>
        `<div class="iterate-turn"><strong>Turn ${turn.turn}</strong>` +
        `${turn.feedback ? ` · ${escapeHtml(turn.feedback)}` : ""}` +
        `<div class="muted">${escapeHtml(turn.result?.summary || "")}</div></div>`,
    )
    .join("");

  panel.innerHTML = `
    <div class="iterate-meta muted">Session · ${escapeHtml(session.status)} · turn ${session.turn}</div>
    <div class="iterate-turns">${turnLines || '<div class="muted">暂无 Turn</div>'}</div>
    <div class="inspector-section-label">Session Changelist</div>
    <div id="nodeSessionChangelist" class="changelist-panel"></div>
    <label for="nodeIterateFeedback">继续优化</label>
    <textarea id="nodeIterateFeedback" rows="3" placeholder="例如：补充协议章节与资源配置表"></textarea>
    <div class="inspector-actions">
      <button class="primary" id="nodeIterateBtn">继续迭代</button>
      <button id="nodeIterateCommitBtn">完成迭代</button>
    </div>
  `;

  renderChangelist($("nodeSessionChangelist"), {
    summary: turns[turns.length - 1]?.result?.summary || "",
    assets: turns[turns.length - 1]?.result?.assets || [],
    changes: sessionChanges,
  }, {
    onAssetClick: async (ref) => {
      try {
        await openArtifact(ref);
        setWorkflowView("runs");
      } catch (error) {
        setLog(error.message);
      }
    },
  });

  $("nodeIterateBtn")?.addEventListener("click", () => {
    submitIterate().catch((error) => setLog(error.message));
  });
  $("nodeIterateCommitBtn")?.addEventListener("click", () => {
    submitCommit().catch((error) => setLog(error.message));
  });
}

async function submitIterate() {
  const node = currentNode();
  const runId = workflowState.currentState?.run_id || $("runId")?.value?.trim();
  const feedback = $("nodeIterateFeedback")?.value?.trim();
  if (!node || !runId || !feedback) {
    setLog("请输入迭代反馈。");
    return;
  }
  const payload = await api(`/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(node.id)}/iterate`, {
    method: "POST",
    body: JSON.stringify({ feedback, ...readGlobalExecutorPayload() }),
  });
  setState(payload.state);
  setLog(`迭代 Turn 完成: ${node.id}`);
  await loadState();
  renderNodeInspector();
}

async function submitCommit() {
  const node = currentNode();
  const runId = workflowState.currentState?.run_id || $("runId")?.value?.trim();
  if (!node || !runId) return;
  const payload = await api(
    `/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(node.id)}/session/commit`,
    { method: "POST", body: JSON.stringify(readGlobalExecutorPayload()) },
  );
  setState(payload.state);
  setLog(`Session 已提交: ${node.id}`);
  await loadState();
  renderNodeInspector();
}

export function initNodeIteratePanel() {
  document.querySelectorAll("[data-node-detail-tab]").forEach((button) => {
    if (button.getAttribute("data-node-detail-tab") !== "iterate") return;
    button.addEventListener("click", () => {
      void renderNodeIteratePanel();
    });
  });
}
