import { $, escapeHtml } from "../core/dom.js";
import { api } from "../core/api.js";
import { setLog } from "../core/log.js";
import { getExecutorCatalog, refreshExecutorCatalog } from "../core/executors.js";
import { workflowState } from "./state.js";
import {
  applyWorkflowDraft,
  cloneWorkflowToWorkspace,
  openWorkflowEditor,
  syncLinearTransitions,
  syncWorkflowFormToWorkflow,
} from "./catalog.js";
import { currentNode, syncNodeFormToWorkflow } from "./node-form.js";
import { setWorkflowView } from "./inspector.js";

const MAX_UNDO = 5;
const MAX_ATTACHMENTS = 6;
const MAX_ATTACHMENT_TEXT = 12000;
const MENTION_PATTERN = /@([a-zA-Z0-9_]+)/g;

function emptyAssistBundle() {
  return {
    chatHistory: [],
    pendingDraft: null,
    pendingSummary: "",
    pendingChanges: [],
    undoStack: [],
    session_id: "",
    chat_id: "",
    hydrated: false,
    running: false,
    streamAssistantText: "",
    progressPercent: 0,
    progressMessage: "描述要如何修改工作流；可用 @节点id 指定焦点。",
    errorMessage: "",
    logText: "",
    inputDraft: "",
    providerId: "",
    attachments: [],
    mentionQuery: "",
    mentionStart: -1,
    mentionActiveIndex: 0,
  };
}

const assistByWorkflowId = new Map();
let activeWorkflowId = "";

function activeBundle() {
  return bundleFor(activeWorkflowId);
}

function isActiveWorkflow(workflowId) {
  return Boolean(workflowId) && workflowId === activeWorkflowId;
}

function bundleFor(workflowId) {
  if (!workflowId) return emptyAssistBundle();
  if (!assistByWorkflowId.has(workflowId)) {
    assistByWorkflowId.set(workflowId, emptyAssistBundle());
  }
  return assistByWorkflowId.get(workflowId);
}

function saveUiToBundle(workflowId) {
  if (!workflowId) return;
  const bundle = bundleFor(workflowId);
  const input = $("workflowAssistInput");
  const select = $("workflowAssistProvider");
  if (input) bundle.inputDraft = input.value;
  if (select) bundle.providerId = select.value;
}

function applyUiFromBundle(workflowId) {
  const bundle = bundleFor(workflowId);
  const input = $("workflowAssistInput");
  const select = $("workflowAssistProvider");
  if (input && document.activeElement !== input) {
    input.value = bundle.inputDraft || "";
  }
  if (select && bundle.providerId) select.value = bundle.providerId;
  updateAssistProviderTitle();
  bundle.mentionQuery = "";
  bundle.mentionStart = -1;
  bundle.mentionActiveIndex = 0;
  hideMentionMenu();
}

function saveActiveBundleUi() {
  if (!activeWorkflowId) return;
  saveUiToBundle(activeWorkflowId);
}

function flushActiveAssistBundle() {
  saveActiveBundleUi();
}

function rememberWorkflowSession(workflowId, sessionId, chatId) {
  if (!workflowId) return;
  const bundle = bundleFor(workflowId);
  bundle.session_id = sessionId || bundle.session_id || "";
  bundle.chat_id = chatId || bundle.chat_id || "";
}

async function hydrateAssistFromServer(workflowId) {
  const bundle = bundleFor(workflowId);
  if (bundle.hydrated) return;
  try {
    const payload = await api(`/workflows/${encodeURIComponent(workflowId)}/assist/session`);
    if (bundle.hydrated) return;
    if (bundle.chatHistory.length) {
      bundle.hydrated = true;
      return;
    }
    if (payload.session_id) {
      bundle.session_id = String(payload.session_id);
    }
    if (payload.chat_id) {
      bundle.chat_id = String(payload.chat_id);
    }
    if (Array.isArray(payload.messages) && payload.messages.length) {
      bundle.chatHistory = payload.messages.map((item) => {
        const role = item.role === "user" ? "user" : "assistant";
        const content = String(item.content || "");
        const compact = role === "user" ? splitAttachmentContext(content) : { displayContent: content, hint: "" };
        return {
          role,
          content,
          displayContent: compact.displayContent,
          hint: compact.hint,
        };
      }).filter((item) => item.content.trim());
    }
    if (payload.pending_summary && !bundle.pendingSummary) {
      bundle.pendingSummary = String(payload.pending_summary);
    }
    bundle.hydrated = true;
  } catch {
    bundle.hydrated = true;
  }
}

export function migrateWorkflowAssistState(fromWorkflowId, toWorkflowId) {
  if (!fromWorkflowId || !toWorkflowId || fromWorkflowId === toWorkflowId) return;
  saveActiveBundleUi();
  const source = bundleFor(fromWorkflowId);
  const cloned = {
    chatHistory: source.chatHistory.slice(),
    pendingDraft: source.pendingDraft ? JSON.parse(JSON.stringify(source.pendingDraft)) : null,
    pendingSummary: source.pendingSummary || "",
    pendingChanges: source.pendingChanges ? source.pendingChanges.slice() : [],
    undoStack: source.undoStack.slice(),
    session_id: "",
    chat_id: "",
    hydrated: false,
    running: false,
    streamAssistantText: source.running ? "" : (source.streamAssistantText || ""),
    progressPercent: source.progressPercent || 0,
    progressMessage: source.progressMessage || "",
    errorMessage: source.errorMessage || "",
    logText: source.logText || "",
    inputDraft: source.inputDraft || "",
    providerId: source.providerId || "",
    attachments: source.attachments ? source.attachments.map((item) => ({ ...item })) : [],
    mentionQuery: "",
    mentionStart: -1,
    mentionActiveIndex: 0,
  };
  if (!source.running) {
    source.chatHistory = [];
    source.pendingDraft = null;
    source.pendingSummary = "";
    source.pendingChanges = [];
    source.undoStack = [];
    source.streamAssistantText = "";
    source.logText = "";
    source.errorMessage = "";
  } else {
    source.running = false;
    source.streamAssistantText = "";
  }
  assistByWorkflowId.set(toWorkflowId, cloned);
  if (activeWorkflowId === fromWorkflowId) {
    activeWorkflowId = toWorkflowId;
    renderAssistShell();
  }
}

export async function syncWorkflowAssistContext(workflowId) {
  const nextId = (workflowId || workflowState.editingWorkflow?.id || "").trim();
  if (nextId === activeWorkflowId) {
    renderAssistShell();
    return;
  }
  flushActiveAssistBundle();
  activeWorkflowId = nextId;
  await hydrateAssistFromServer(nextId);
  renderAssistShell();
}

function renderAssistShell() {
  const bundle = activeBundle();
  if (bundle.chatHistory.length && !bundle.running) {
    const idleHint = "描述要如何修改工作流；可用 @节点id 指定焦点。";
    if (!bundle.progressMessage || bundle.progressMessage === idleHint) {
      bundle.progressMessage = "已恢复此工作流的助手对话。";
    }
  }
  if (bundle.running && !bundle.progressMessage) {
    bundle.progressMessage = "生成中...";
  }
  applyUiFromBundle(activeWorkflowId);
  renderAssistChat();
  renderAssistAttachments();
  renderPendingPreview();
  updateUndoButton();
  renderAssistFocusChips();
  renderAssistContextMeta();
  setAssistProgressUI(bundle.progressPercent, bundle.progressMessage);
  setAssistErrorUI(bundle.errorMessage);
  const log = $("workflowAssistLog");
  if (log) log.textContent = bundle.logText || "";
  updateAssistControls();
  updateBackgroundRunHint();
}

function updateBackgroundRunHint() {
  const label = $("workflowAssistProgressLabel");
  if (!label) return;
  const runningElsewhere = [...assistByWorkflowId.entries()].filter(
    ([workflowId, bundle]) => bundle.running && workflowId !== activeWorkflowId,
  );
  if (!runningElsewhere.length) return;
  const names = runningElsewhere.map(([workflowId]) => workflowId).join("、");
  if (!activeBundle().running) {
    label.textContent = `${label.textContent} · 后台生成中：${names}`;
  }
}

function providers() {
  const catalog = getExecutorCatalog();
  const items = catalog.providers?.length ? catalog.providers : catalog.agent_providers || [];
  return items.filter((item) => item.tier === "provider" || item.source === "builtin" || item.kind);
}

function acpProviders() {
  return providers().filter((item) => item.kind === "cli-session");
}

function syncWorkflowForms() {
  if (workflowState.workflowEditOpen) syncWorkflowFormToWorkflow();
  if (workflowState.nodeEditOpen) syncNodeFormToWorkflow();
}

function currentSelectedNodeId() {
  const node = workflowState.editingWorkflow.nodes?.[workflowState.selectedNodeIndex];
  return node?.id || "";
}

function parseFocusNodeIds(text) {
  const ids = new Set();
  const known = new Set((workflowState.editingWorkflow.nodes || []).map((node) => node.id).filter(Boolean));
  for (const match of text.matchAll(MENTION_PATTERN)) {
    if (known.has(match[1])) ids.add(match[1]);
  }
  const selected = currentSelectedNodeId();
  if (selected) ids.add(selected);
  return [...ids];
}

function validateMentions(text) {
  const known = new Set((workflowState.editingWorkflow.nodes || []).map((node) => node.id).filter(Boolean));
  const invalid = [];
  for (const match of text.matchAll(MENTION_PATTERN)) {
    if (!known.has(match[1])) invalid.push(match[1]);
  }
  return invalid;
}

function ensureEditableForAssist() {
  if (workflowState.currentWorkflowEditable) return false;
  try {
    cloneWorkflowToWorkspace();
    setLog("只读工作流已自动复制为 workspace 副本，助手将修改副本。");
    return true;
  } catch (error) {
    setLog(`自动复制副本失败，先基于当前草稿继续对话：${error.message}`);
    return false;
  }
}

function setAssistProgressUI(percent, message) {
  const fill = $("workflowAssistProgressFill");
  const label = $("workflowAssistProgressLabel");
  if (fill) fill.style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;
  if (label && message) label.textContent = message;
}

function setAssistProgressFor(workflowId, percent, message) {
  const bundle = bundleFor(workflowId);
  bundle.progressPercent = Math.max(0, Math.min(100, percent || 0));
  if (message) bundle.progressMessage = message;
  if (isActiveWorkflow(workflowId)) {
    setAssistProgressUI(bundle.progressPercent, bundle.progressMessage);
  }
}

function setAssistErrorUI(message) {
  const box = $("workflowAssistError");
  if (!box) return;
  if (!message) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.textContent = message;
}

function setAssistErrorFor(workflowId, message) {
  const bundle = bundleFor(workflowId);
  bundle.errorMessage = message || "";
  if (isActiveWorkflow(workflowId)) {
    setAssistErrorUI(bundle.errorMessage);
  }
}

function appendAssistLogFor(workflowId, line) {
  if (!line) return;
  const bundle = bundleFor(workflowId);
  bundle.logText = `${bundle.logText || ""}${bundle.logText ? "\n" : ""}${line}`;
}

function clipChangeValue(value, limit = 48) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function formatChangeDelta(path, before, after) {
  const beforeText = clipChangeValue(before);
  const afterText = clipChangeValue(after);
  if (!beforeText && afterText) {
    return { op: "added", text: `+ ${path}: ${afterText}` };
  }
  if (beforeText && !afterText) {
    return { op: "removed", text: `- ${path}: ${beforeText}` };
  }
  return { op: "changed", text: `△ ${path}: ${beforeText} → ${afterText}` };
}

function createChangesetHtml(changes) {
  if (!Array.isArray(changes) || !changes.length) return "";
  const rows = [];
  for (const item of changes) {
    const kind = String(item.kind || "");
    if (kind === "workflow") {
      const line = formatChangeDelta(`workflow.${item.path}`, item.before, item.after);
      rows.push(`<div class="workflow-assist-change-line ${line.op}">${escapeHtml(line.text)}</div>`);
      continue;
    }
    if (kind === "node_added") {
      rows.push(`<div class="workflow-assist-change-line added">+ nodes/${escapeHtml(item.node_id || "")}</div>`);
      continue;
    }
    if (kind === "node_removed") {
      rows.push(`<div class="workflow-assist-change-line removed">- nodes/${escapeHtml(item.node_id || "")}</div>`);
      continue;
    }
    if (kind === "node_field") {
      const line = formatChangeDelta(`nodes/${item.node_id}/${item.path}`, item.before, item.after);
      rows.push(`<div class="workflow-assist-change-line ${line.op}">${escapeHtml(line.text)}</div>`);
      continue;
    }
    if (kind === "transition_added") {
      const when = String(item.when || "always");
      rows.push(
        `<div class="workflow-assist-change-line added">+ transitions/${escapeHtml(item.from || "")}→${escapeHtml(item.to || "")} [${escapeHtml(when)}]</div>`,
      );
      continue;
    }
    if (kind === "transition_removed") {
      const when = String(item.when || "always");
      rows.push(
        `<div class="workflow-assist-change-line removed">- transitions/${escapeHtml(item.from || "")}→${escapeHtml(item.to || "")} [${escapeHtml(when)}]</div>`,
      );
    }
  }
  return `<div class="workflow-assist-changeset">${rows.join("")}</div>`;
}

function updateAssistControls() {
  const bundle = activeBundle();
  const running = Boolean(bundle.running);
  const sendBtn = $("workflowAssistSendBtn");
  const attachBtn = $("workflowAssistAttachBtn");
  const clearBtn = $("workflowAssistClearBtn");
  const modelSelect = $("workflowAssistProvider");
  if (sendBtn) sendBtn.disabled = running;
  if (attachBtn) attachBtn.disabled = running;
  if (clearBtn) clearBtn.disabled = running;
  if (modelSelect) modelSelect.disabled = running;
  if ($("workflowAssistApplyBtn")) $("workflowAssistApplyBtn").disabled = running || !bundle.pendingDraft;
  if ($("workflowAssistDiscardBtn")) $("workflowAssistDiscardBtn").disabled = running || !bundle.pendingDraft;
}

function createChatBubble(item, { streaming = false } = {}) {
  const bubble = document.createElement("div");
  bubble.className = `workflow-assist-chat-item ${item.role}${streaming ? " streaming" : ""}`;
  const body = Array.isArray(item.changes) && item.changes.length
    ? createChangesetHtml(item.changes)
    : `<div class="workflow-assist-chat-content">${escapeHtml(item.displayContent || item.content)}</div>`;
  const hintHtml = item.hint
    ? `<div class="workflow-assist-chat-hint muted">${escapeHtml(item.hint)}</div>`
    : "";
  bubble.innerHTML = `
    <div class="workflow-assist-chat-role">${item.role === "user" ? "你" : "AI"}</div>
    ${body}
    ${hintHtml}
  `;
  return bubble;
}

function renderAssistChat() {
  const container = $("workflowAssistChat");
  if (!container) return;
  const bundle = activeBundle();
  if (!bundle.chatHistory.length && !bundle.streamAssistantText) {
    container.innerHTML = '<div class="workflow-assist-empty muted">还没有对话。可探讨需求，或用自然语言描述要如何修改工作流。</div>';
    return;
  }
  container.innerHTML = "";
  for (const item of bundle.chatHistory) {
    container.appendChild(createChatBubble(item));
  }
  if (bundle.streamAssistantText) {
    container.appendChild(createChatBubble(
      { role: "assistant", content: bundle.streamAssistantText },
      { streaming: Boolean(bundle.running) },
    ));
  }
  container.scrollTop = container.scrollHeight;
}

function renderPendingPreview() {
  const preview = $("workflowAssistPreview");
  const summaryBox = $("workflowAssistPreviewSummary");
  const meta = $("workflowAssistPreviewMeta");
  const applyBtn = $("workflowAssistApplyBtn");
  const discardBtn = $("workflowAssistDiscardBtn");
  const bundle = activeBundle();
  if (!preview) return;
  if (!bundle.pendingDraft) {
    preview.hidden = true;
    if (applyBtn) applyBtn.disabled = true;
    if (discardBtn) discardBtn.disabled = true;
    return;
  }
  preview.hidden = false;
  if (summaryBox) {
    summaryBox.innerHTML = bundle.pendingChanges?.length
      ? createChangesetHtml(bundle.pendingChanges)
      : escapeHtml(bundle.pendingSummary || "无结构变更");
  }
  const before = workflowState.editingWorkflow.nodes?.length || 0;
  const after = bundle.pendingDraft.nodes?.length || 0;
  if (meta) {
    meta.textContent = `节点数：${before} → ${after} · 应用前可继续对话微调`;
  }
  if (applyBtn) applyBtn.disabled = !!bundle.running;
  if (discardBtn) discardBtn.disabled = !!bundle.running;
}

function updateUndoButton() {
  const undoBtn = $("workflowAssistUndoBtn");
  const bundle = activeBundle();
  if (undoBtn) undoBtn.disabled = !bundle.undoStack.length || !!bundle.running;
}

export function renderAssistFocusChips() {
  const box = $("workflowAssistFocus");
  if (!box) return;
  const node = workflowState.editingWorkflow.nodes?.[workflowState.selectedNodeIndex];
  const input = $("workflowAssistInput")?.value || "";
  const mentions = [...input.matchAll(MENTION_PATTERN)].map((match) => match[1]);
  const parts = [];
  if (node?.id) parts.push(`选中 ${node.name || node.id} (${node.id})`);
  for (const id of mentions) {
    if (id !== node?.id) parts.push(`@${id}`);
  }
  box.textContent = parts.length ? parts.join(" · ") : "未选中节点";
}

function formatAttachmentSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function splitAttachmentContext(content) {
  const marker = "\n\n[附件上下文]\n";
  const raw = String(content || "");
  const markerIndex = raw.indexOf(marker);
  if (markerIndex < 0) {
    return { displayContent: raw, hint: "" };
  }
  const displayContent = raw.slice(0, markerIndex).trim();
  const attachmentLines = raw
    .slice(markerIndex + marker.length)
    .split("\n")
    .filter((line) => line.startsWith("- "))
    .map((line) => line.replace(/^- /, "").trim());
  return {
    displayContent,
    hint: attachmentLines.length ? `附件：${attachmentLines.join("、")}` : "附件已添加",
  };
}

function isReadableAttachment(file) {
  const name = String(file?.name || "").toLowerCase();
  const textExts = [
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".tsv", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".html", ".css", ".scss", ".less", ".xml", ".ini", ".cfg", ".toml", ".sh", ".ps1",
  ];
  return file?.type?.startsWith("text/")
    || textExts.some((ext) => name.endsWith(ext));
}

async function buildAttachmentRecord(file) {
  const record = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: file.name || "unnamed",
    size: Number(file.size || 0),
    type: file.type || "application/octet-stream",
    inlineText: "",
  };
  if (!isReadableAttachment(file)) return record;
  try {
    const raw = await file.text();
    const normalized = raw.replace(/\r\n/g, "\n").trim();
    if (normalized) {
      record.inlineText = normalized.slice(0, MAX_ATTACHMENT_TEXT);
    }
  } catch {
    record.inlineText = "";
  }
  return record;
}

function attachmentHintText(attachments) {
  if (!attachments.length) return "";
  return `附件：${attachments.map((item) => item.name).join("、")}`;
}

async function buildAssistDescription(description, attachments) {
  if (!attachments.length) return description;
  const blocks = attachments.map((item) => {
    const header = `- ${item.name}${item.size ? ` (${formatAttachmentSize(item.size)})` : ""}`;
    if (!item.inlineText) {
      return `${header}\n  [未内联内容，仅提供文件名和大小]`;
    }
    return `${header}\n${item.inlineText}`;
  });
  return `${description}\n\n[附件上下文]\n${blocks.join("\n\n")}`;
}

function renderAssistAttachments() {
  const list = $("workflowAssistAttachmentList");
  if (!list) return;
  const attachments = activeBundle().attachments || [];
  list.innerHTML = "";
  list.hidden = !attachments.length;
  attachments.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "workflow-assist-attachment-chip";
    chip.innerHTML = `
      <span class="workflow-assist-attachment-name">${escapeHtml(item.name)}</span>
      <span class="muted">${escapeHtml(formatAttachmentSize(item.size))}</span>
      <button type="button" class="workflow-assist-attachment-remove" data-attachment-remove="${escapeHtml(item.id)}" aria-label="移除附件">x</button>
    `;
    list.appendChild(chip);
  });
}

function renderAssistContextMeta() {
  const meta = $("workflowAssistContextMeta");
  if (!meta) return;
  const bundle = activeBundle();
  const inputLength = ($("workflowAssistInput")?.value || bundle.inputDraft || "").trim().length;
  const messageCount = bundle.chatHistory.length + (bundle.streamAssistantText ? 1 : 0);
  const attachmentCount = bundle.attachments?.length || 0;
  const charCount = bundle.chatHistory.reduce((sum, item) => sum + String(item.content || "").length, 0) + inputLength;
  const parts = [`上下文 ${messageCount} 条`, `${charCount} 字`];
  if (attachmentCount) parts.push(`附件 ${attachmentCount}`);
  meta.textContent = parts.join(" · ");
}

async function addAssistAttachments(fileList) {
  const bundle = activeBundle();
  if (!fileList?.length) return;
  const remaining = Math.max(MAX_ATTACHMENTS - bundle.attachments.length, 0);
  if (!remaining) {
    setLog(`最多添加 ${MAX_ATTACHMENTS} 个附件。`);
    return;
  }
  const picked = Array.from(fileList).slice(0, remaining);
  const records = await Promise.all(picked.map((file) => buildAttachmentRecord(file)));
  const existing = new Set(bundle.attachments.map((item) => `${item.name}:${item.size}`));
  for (const record of records) {
    const key = `${record.name}:${record.size}`;
    if (existing.has(key)) continue;
    bundle.attachments.push(record);
    existing.add(key);
  }
  renderAssistAttachments();
  renderAssistContextMeta();
}

function removeAssistAttachment(attachmentId) {
  const bundle = activeBundle();
  bundle.attachments = bundle.attachments.filter((item) => item.id !== attachmentId);
  renderAssistAttachments();
  renderAssistContextMeta();
}

export function populateAssistProviderSelect() {
  const select = $("workflowAssistProvider");
  if (!select) return;
  select.innerHTML = "";
  for (const item of acpProviders()) {
    const option = document.createElement("option");
    option.value = item.provider || item.id;
    const compact = compactProviderLabel(item);
    const full = fullProviderLabel(item);
    option.textContent = compact;
    option.title = full;
    option.dataset.fullLabel = full;
    select.appendChild(option);
  }
  const preferred = acpProviders().find((item) => item.id === "cursor-agent-acp" && item.ready)
    || acpProviders().find((item) => item.ready)
    || acpProviders()[0];
  if (preferred) {
    select.value = preferred.provider || preferred.id;
  }
  updateAssistProviderTitle();
}

function compactProviderLabel(item) {
  const label = String(item?.label || item?.id || "模型").trim();
  const normalized = label
    .replace(/\s+Agent\s+ACP/gi, "")
    .replace(/\s+ACP/gi, "")
    .replace(/\s+Provider/gi, "")
    .trim();
  if (/cursor/i.test(normalized)) return "Cursor";
  if (/codex/i.test(normalized)) return "Codex";
  if (/openai/i.test(normalized)) return "OpenAI";
  return normalized || "模型";
}

function fullProviderLabel(item) {
  const label = String(item?.label || item?.id || "模型").trim();
  const status = item?.ready ? "就绪" : "缺配置";
  return `${label} (${status})`;
}

function updateAssistProviderTitle() {
  const select = $("workflowAssistProvider");
  if (!select) return;
  const selected = select.options[select.selectedIndex];
  select.title = selected?.dataset?.fullLabel || selected?.textContent || "";
}

function parseSseEvents(chunk) {
  const events = [];
  const lines = chunk.split("\n");
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
      continue;
    }
    if (!line && dataLines.length) {
      try {
        events.push(JSON.parse(dataLines.join("\n")));
      } catch {
        // Ignore malformed chunks; wait for more data.
      }
      dataLines.length = 0;
    }
  }
  if (dataLines.length) {
    try {
      events.push(JSON.parse(dataLines.join("\n")));
    } catch {
      // Incomplete JSON payload.
    }
  }
  return events;
}

async function consumeAssistStream(response, onEvent) {
  if (!response.ok) {
    const text = await response.text();
    let message = response.statusText;
    try {
      const payload = JSON.parse(text);
      message = payload.error || message;
    } catch {
      if (text.trim()) message = text.trim();
    }
    throw new Error(message);
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("浏览器不支持流式响应。");
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal = false;
  const dispatch = (event) => {
    onEvent(event);
    if (event?.type === "done" || event?.type === "error") {
      terminal = true;
    }
  };
  try {
    while (!terminal) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";
      for (const chunk of chunks) {
        for (const event of parseSseEvents(chunk)) {
          dispatch(event);
          if (terminal) break;
        }
      }
    }
    if (!terminal && buffer.trim()) {
      for (const event of parseSseEvents(buffer)) {
        dispatch(event);
        if (terminal) break;
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Stream may already be closed.
    }
  }
}

function hideMentionMenu() {
  const menu = $("workflowAssistMentionMenu");
  if (menu) menu.hidden = true;
  const bundle = activeBundle();
  bundle.mentionQuery = "";
  bundle.mentionStart = -1;
}

function filteredMentionNodes() {
  const nodes = workflowState.editingWorkflow.nodes || [];
  const bundle = activeBundle();
  const query = bundle.mentionQuery.toLowerCase();
  return nodes.filter((node) => {
    const id = String(node.id || "");
    const name = String(node.name || "");
    if (!query) return true;
    return id.toLowerCase().includes(query) || name.toLowerCase().includes(query);
  });
}

function renderMentionMenu() {
  const menu = $("workflowAssistMentionMenu");
  const input = $("workflowAssistInput");
  const bundle = activeBundle();
  if (!menu || !input || bundle.mentionStart < 0) {
    hideMentionMenu();
    return;
  }
  const matches = filteredMentionNodes();
  if (!matches.length) {
    hideMentionMenu();
    return;
  }
  if (bundle.mentionActiveIndex >= matches.length) bundle.mentionActiveIndex = 0;
  menu.hidden = false;
  menu.innerHTML = "";
  matches.forEach((node, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `workflow-assist-mention-item${index === bundle.mentionActiveIndex ? " active" : ""}`;
    button.textContent = `${node.name || node.id} (${node.id})`;
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      insertMention(node.id);
    });
    menu.appendChild(button);
  });
}

function insertMention(nodeId) {
  const input = $("workflowAssistInput");
  const bundle = activeBundle();
  if (!input || bundle.mentionStart < 0) return;
  const before = input.value.slice(0, bundle.mentionStart);
  const after = input.value.slice(input.selectionStart);
  input.value = `${before}@${nodeId} ${after}`;
  bundle.inputDraft = input.value;
  const cursor = before.length + nodeId.length + 2;
  input.setSelectionRange(cursor, cursor);
  hideMentionMenu();
  renderAssistFocusChips();
  renderAssistContextMeta();
  input.focus();
}

function handleMentionInput() {
  const input = $("workflowAssistInput");
  if (!input) return;
  const bundle = activeBundle();
  const value = input.value;
  bundle.inputDraft = value;
  const cursor = input.selectionStart;
  const prefix = value.slice(0, cursor);
  const at = prefix.lastIndexOf("@");
  if (at < 0 || (at > 0 && /\S/.test(prefix[at - 1]))) {
    hideMentionMenu();
    renderAssistFocusChips();
    renderAssistContextMeta();
    return;
  }
  const query = prefix.slice(at + 1);
  if (/\s/.test(query)) {
    hideMentionMenu();
    renderAssistFocusChips();
    renderAssistContextMeta();
    return;
  }
  bundle.mentionStart = at;
  bundle.mentionQuery = query;
  bundle.mentionActiveIndex = 0;
  renderMentionMenu();
  renderAssistFocusChips();
  renderAssistContextMeta();
}

async function sendAssistMessage() {
  saveActiveBundleUi();
  const input = $("workflowAssistInput");
  const description = input?.value.trim();
  if (!description) {
    setAssistProgressFor(activeWorkflowId, 0, "请先输入描述。");
    return;
  }
  if (activeBundle().running) return;

  const invalidMentions = validateMentions(description);
  if (invalidMentions.length) {
    setLog(`未知节点：${invalidMentions.join(", ")}`);
    return;
  }

  syncWorkflowForms();
  ensureEditableForAssist();
  syncLinearTransitions();

  const runWorkflowId = workflowState.editingWorkflow?.id || activeWorkflowId;
  if (!runWorkflowId) return;
  if (runWorkflowId !== activeWorkflowId) {
    activeWorkflowId = runWorkflowId;
  }
  const runBundle = bundleFor(runWorkflowId);
  saveUiToBundle(runWorkflowId);
  const requestDescription = await buildAssistDescription(description, runBundle.attachments || []);
  const attachmentHint = attachmentHintText(runBundle.attachments || []);
  runBundle.running = true;
  runBundle.streamAssistantText = "";
  runBundle.errorMessage = "";
  runBundle.logText = "";

  setAssistErrorFor(runWorkflowId, "");
  updateAssistControls();

  runBundle.chatHistory.push({
    role: "user",
    content: requestDescription,
    displayContent: description,
    hint: attachmentHint,
  });
  runBundle.inputDraft = "";
  renderAssistChat();
  if (input) input.value = "";
  renderAssistFocusChips();
  renderAssistContextMeta();
  hideMentionMenu();

  if (isActiveWorkflow(runWorkflowId)) {
    runBundle.logText = "";
  }
  setAssistProgressFor(runWorkflowId, 5, "准备生成...");

  const requestDraft = JSON.parse(JSON.stringify(workflowState.editingWorkflow));
  const requestFocusNodeIds = parseFocusNodeIds(description);
  const requestSelectedNodeId = currentSelectedNodeId();
  const requestProvider = runBundle.providerId || $("workflowAssistProvider")?.value || "";
  let assistantCommitted = false;

  const renderRunView = () => {
    if (!isActiveWorkflow(runWorkflowId)) return;
    renderAssistShell();
  };

  try {
    const session = {
      session_id: runBundle.session_id || "",
      chat_id: runBundle.chat_id || "",
    };
    const response = await fetch("/workflows/assist/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description: requestDescription,
        provider: requestProvider,
        draft: requestDraft,
        workflow_id: runWorkflowId,
        session_id: session.session_id || undefined,
        selected_node_id: requestSelectedNodeId || undefined,
        focus_node_ids: requestFocusNodeIds,
        messages: runBundle.chatHistory.map((item) => ({ role: item.role, content: item.content })),
      }),
    });
    await consumeAssistStream(response, (event) => {
      if (event.type === "session") {
        rememberWorkflowSession(
          event.workflow_id || runWorkflowId,
          event.session_id,
          event.chat_id,
        );
      } else if (event.type === "progress") {
        setAssistProgressFor(runWorkflowId, event.percent, event.message);
      } else if (event.type === "log") {
        appendAssistLogFor(runWorkflowId, event.line);
      } else if (event.type === "assistant") {
        const content = String(event.content || event.text || "");
        if (content) {
          runBundle.streamAssistantText += content;
          renderRunView();
        }
      } else if (event.type === "done") {
        const changes = Array.isArray(event.changes) ? event.changes : [];
        const hasStructuralChange = event.changed === true && changes.length > 0;
        const reply = String(
          event.reply || runBundle.streamAssistantText || (!hasStructuralChange ? event.message : "") || "",
        ).trim();
        const content = hasStructuralChange ? "" : reply;
        if (content) {
          runBundle.chatHistory.push({
            role: "assistant",
            content,
          });
        }
        assistantCommitted = true;
        runBundle.streamAssistantText = "";
        if (event.changed === true && event.workflow && changes.length > 0) {
          runBundle.pendingDraft = event.workflow;
          runBundle.pendingSummary = String(event.summary || event.message || reply || "").trim();
          runBundle.pendingChanges = changes;
          setAssistProgressFor(runWorkflowId, 100, "草稿已就绪，请预览后应用。");
        } else {
          runBundle.pendingDraft = null;
          runBundle.pendingSummary = "";
          runBundle.pendingChanges = [];
          setAssistProgressFor(runWorkflowId, 100, "对话完成。");
        }
        setAssistErrorFor(runWorkflowId, "");
        renderRunView();
      } else if (event.type === "error") {
        throw new Error(event.message || "生成失败。");
      }
    });
  } catch (error) {
    if (runBundle.streamAssistantText && !assistantCommitted) {
      runBundle.chatHistory.push({
        role: "assistant",
        content: runBundle.streamAssistantText,
      });
      runBundle.streamAssistantText = "";
      renderRunView();
    }
    setAssistProgressFor(runWorkflowId, 0, "生成未完成");
    setAssistErrorFor(runWorkflowId, error.message);
    if (isActiveWorkflow(runWorkflowId)) {
      setLog(error.message);
    }
  } finally {
    runBundle.running = false;
    runBundle.streamAssistantText = "";
    if (isActiveWorkflow(runWorkflowId)) {
      renderAssistShell();
    } else {
      updateAssistControls();
    }
    if (isActiveWorkflow(runWorkflowId)) {
      renderAssistFocusChips();
    }
  }
}

function applyPendingDraft() {
  const bundle = activeBundle();
  if (!bundle.pendingDraft || bundle.running) {
    if (!bundle.pendingDraft) setLog("没有可应用的草稿。");
    return;
  }
  try {
    const previousId = currentSelectedNodeId();
    bundle.undoStack.push(JSON.parse(JSON.stringify(workflowState.editingWorkflow)));
    if (bundle.undoStack.length > MAX_UNDO) bundle.undoStack.shift();
    applyWorkflowDraft(bundle.pendingDraft, { selectedNodeId: previousId });
    bundle.pendingDraft = null;
    bundle.pendingSummary = "";
    bundle.pendingChanges = [];
    renderPendingPreview();
    updateUndoButton();
    setAssistErrorFor(activeWorkflowId, "");
    const appliedName = workflowState.editingWorkflow.name || workflowState.editingWorkflow.id;
    setAssistProgressFor(activeWorkflowId, 100, `已应用到内存：${appliedName}`);
    setLog(`已应用助手草稿（${appliedName}），满意后请点保存。`);
    void openWorkflowEditor().catch((error) => setLog(error.message));
  } catch (error) {
    setAssistErrorFor(activeWorkflowId, error.message);
    setLog(error.message);
  }
}

function discardPendingDraft() {
  const bundle = activeBundle();
  bundle.pendingDraft = null;
  bundle.pendingSummary = "";
  bundle.pendingChanges = [];
  renderPendingPreview();
  setAssistProgressFor(activeWorkflowId, 0, "已丢弃待应用草稿。");
}

async function clearAssistHistory() {
  const workflowId = activeWorkflowId || workflowState.editingWorkflow?.id || "";
  if (!workflowId) return;
  const bundle = bundleFor(workflowId);
  if (bundle.running) {
    setLog("请等待当前生成完成后再清空历史。");
    return;
  }
  if (!window.confirm("清空当前工作流的助手历史记录？这会删除已保存的对话上下文。")) {
    return;
  }
  await api(`/workflows/${encodeURIComponent(workflowId)}/assist/session`, { method: "DELETE" });
  bundle.chatHistory = [];
  bundle.pendingDraft = null;
  bundle.pendingSummary = "";
  bundle.pendingChanges = [];
  bundle.undoStack = [];
  bundle.session_id = "";
  bundle.chat_id = "";
  bundle.hydrated = true;
  bundle.running = false;
  bundle.streamAssistantText = "";
  bundle.progressPercent = 0;
  bundle.progressMessage = "历史记录已清空。";
  bundle.errorMessage = "";
  bundle.logText = "";
  bundle.inputDraft = "";
  bundle.attachments = [];
  const input = $("workflowAssistInput");
  if (input) input.value = "";
  const fileInput = $("workflowAssistFileInput");
  if (fileInput) fileInput.value = "";
  hideMentionMenu();
  renderAssistShell();
  setLog(`已清空工作流助手历史（${workflowId}）。`);
}

function undoLastApply() {
  const bundle = activeBundle();
  if (!bundle.undoStack.length || bundle.running) return;
  const snapshot = bundle.undoStack.pop();
  applyWorkflowDraft(snapshot);
  updateUndoButton();
  setWorkflowView("nodes");
  setLog("已撤销上一次应用。");
}

export function initWorkflowAssist() {
  populateAssistProviderSelect();
  activeWorkflowId = workflowState.editingWorkflow?.id || "";
  const bundle = bundleFor(activeWorkflowId);
  if (!bundle.providerId && $("workflowAssistProvider")?.value) {
    bundle.providerId = $("workflowAssistProvider").value;
  }
  void syncWorkflowAssistContext(activeWorkflowId);

  $("workflowAssistSendBtn")?.addEventListener("click", () => {
    sendAssistMessage().catch((error) => setLog(error.message));
  });

  const preview = $("workflowAssistPreview");
  preview?.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.closest("#workflowAssistApplyBtn")) {
      event.preventDefault();
      applyPendingDraft();
      return;
    }
    if (target.closest("#workflowAssistDiscardBtn")) {
      event.preventDefault();
      discardPendingDraft();
      return;
    }
    if (target.closest("#workflowAssistUndoBtn")) {
      event.preventDefault();
      undoLastApply();
    }
  });
  $("workflowAssistApplyBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    applyPendingDraft();
  });
  $("workflowAssistDiscardBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    discardPendingDraft();
  });
  $("workflowAssistUndoBtn")?.addEventListener("click", (event) => {
    event.preventDefault();
    undoLastApply();
  });
  $("workflowAssistClearBtn")?.addEventListener("click", () => {
    clearAssistHistory().catch((error) => setLog(error.message));
  });
  $("workflowAssistAttachBtn")?.addEventListener("click", () => {
    $("workflowAssistFileInput")?.click();
  });
  $("workflowAssistFileInput")?.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    addAssistAttachments(target.files).catch((error) => setLog(error.message));
    target.value = "";
  });
  $("workflowAssistAttachmentList")?.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest("[data-attachment-remove]");
    if (!(button instanceof HTMLElement)) return;
    removeAssistAttachment(button.dataset.attachmentRemove || "");
  });

  $("workflowAssistInput")?.addEventListener("input", handleMentionInput);
  $("workflowAssistInput")?.addEventListener("keydown", (event) => {
    const menu = $("workflowAssistMentionMenu");
    const bundle = activeBundle();
    if (!menu || menu.hidden) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendAssistMessage().catch((error) => setLog(error.message));
      }
      return;
    }
    const matches = filteredMentionNodes();
    if (event.key === "ArrowDown") {
      event.preventDefault();
      bundle.mentionActiveIndex = (bundle.mentionActiveIndex + 1) % matches.length;
      renderMentionMenu();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      bundle.mentionActiveIndex = (bundle.mentionActiveIndex - 1 + matches.length) % matches.length;
      renderMentionMenu();
    } else if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      if (matches[bundle.mentionActiveIndex]) insertMention(matches[bundle.mentionActiveIndex].id);
    } else if (event.key === "Escape") {
      hideMentionMenu();
    }
  });

  $("workflowAssistProvider")?.addEventListener("change", () => {
    saveUiToBundle(activeWorkflowId);
    updateAssistProviderTitle();
  });

  refreshExecutorCatalog().then(() => populateAssistProviderSelect()).catch(() => {});
}
