import { $, escapeHtml } from "../core/dom.js";
import { api } from "../core/api.js";
import { settingsState } from "./state.js";
import { refreshExecutorCatalog } from "../core/executors.js";

const STATUS_LABELS = {
  ready: "就绪",
  missing: "缺配置",
  ok: "测试通过",
  error: "异常",
};

const DEFAULT_TEST_PROMPT = "Reply with exactly: AIWF agent ok";

let agentTemplates = [];
let agentGenerateHistory = [];
let agentGenerateLastAgent = null;
let agentGenerateRunning = false;

export function agentStatusLabel(agent) {
  if (!agent) return "";
  return STATUS_LABELS[agent.status] || (agent.ready ? "就绪" : "未知");
}

function roleAgents() {
  return settingsState.agentCatalog.filter((item) => item.tier === "role" || item.source === "workspace");
}

function providers() {
  return settingsState.agentCatalog.filter((item) => item.tier === "provider" || item.source === "builtin");
}

function countRolesForProvider(providerId) {
  return roleAgents().filter((item) => item.provider === providerId).length;
}

function blankRole() {
  const suffix = Date.now().toString().slice(-4);
  return {
    id: `role_custom_${suffix}`,
    label: "新助手",
    provider: providers()[0]?.id || "cursor-agent-cli",
    ident: { name: "", role: "", vibe: "" },
    soul: "",
  };
}

function setRoleEditorChrome(mode) {
  settingsState.roleEditorMode = mode;
  const isCreate = mode === "create";
  const isEdit = mode === "edit";
  const isOpen = isCreate || isEdit;

  $("roleEditorEmpty").hidden = isOpen;
  $("roleEditorPanel").hidden = !isOpen;
  $("roleEditorCreateTools").hidden = !isCreate;
  $("roleEditorEditActions").hidden = !isEdit;
  $("roleEditorTestLabel").hidden = !isEdit;
  $("roleAgentTestPromptLabel").hidden = !isEdit;
  $("roleAgentTestPrompt").hidden = !isEdit;
  $("roleAgentTestResult").hidden = !isEdit;
  $("cancelRoleEditorBtn").hidden = !isCreate;
  $("createRoleAgentBtn").hidden = !isCreate;

  const duplicateBtn = $("duplicateRoleAgentBtn");
  if (duplicateBtn) {
    duplicateBtn.disabled = !isEdit || !settingsState.roleEditorSourceId;
  }

  if (isCreate && !$("roleEditorModeLabel").dataset.customTitle) {
    $("roleEditorModeLabel").textContent = "新建助手";
  } else if (isEdit) {
    const label = $("roleAgentLabel").value.trim() || settingsState.roleEditorSourceId;
    $("roleEditorModeLabel").textContent = `编辑：${label}`;
    $("roleEditorModeLabel").dataset.customTitle = "";
  }
}

function clearRoleForm() {
  $("roleAgentId").value = "";
  $("roleAgentLabel").value = "";
  $("roleAgentProvider").value = providers()[0]?.id || "";
  $("roleAgentIdentName").value = "";
  $("roleAgentIdentRole").value = "";
  $("roleAgentIdentVibe").value = "";
  $("roleAgentSoul").value = "";
  $("roleAgentTestPrompt").value = DEFAULT_TEST_PROMPT;
  $("roleAgentTestResult").innerHTML = "";
  $("roleAgentMeta").textContent = "";
}

function ensureAssistantsTab() {
  if (settingsState.agentTab === "assistants") {
    renderRoleList();
    return;
  }
  settingsState.agentTab = "assistants";
  document.querySelectorAll("[data-agent-tab]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-agent-tab") === "assistants");
  });
  document.querySelectorAll("[data-agent-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.getAttribute("data-agent-panel") === "assistants");
  });
  renderRoleList();
}

export function setAgentTab(tab) {
  settingsState.agentTab = tab;
  document.querySelectorAll("[data-agent-tab]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-agent-tab") === tab);
  });
  document.querySelectorAll("[data-agent-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.getAttribute("data-agent-panel") === tab);
  });
  if (tab === "providers") {
    renderProviderList();
    if (settingsState.selectedProviderId) {
      loadProviderEditor(settingsState.selectedProviderId).catch(() => {});
    } else {
      resetProviderEditor();
    }
  } else {
    renderRoleList();
    if (settingsState.roleEditorMode === "edit" && settingsState.roleEditorSourceId) {
      loadRoleEditor(settingsState.roleEditorSourceId).catch(() => closeRoleEditor());
    } else if (settingsState.roleEditorMode === "create") {
      setRoleEditorChrome("create");
    } else {
      closeRoleEditor();
    }
  }
}

export async function loadAgentTemplates() {
  try {
    const payload = await api("/agents/templates");
    agentTemplates = payload.templates || [];
  } catch {
    agentTemplates = [];
  }
  populateAgentTemplateSelect();
}

function populateAgentTemplateSelect() {
  const select = $("agentTemplateSelect");
  if (!select) return;
  select.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "选择模板（可选）";
  select.appendChild(placeholder);
  for (const template of agentTemplates) {
    const option = document.createElement("option");
    option.value = template.template_id;
    option.textContent = template.label || template.template_id;
    select.appendChild(option);
  }
}

export async function refreshAgentAssistant() {
  await loadAgentTemplates();
  const payload = await api("/agents");
  settingsState.agentCatalog = payload.agents || [];
  populateRoleProviderSelect();
  if (settingsState.agentTab === "providers") {
    renderProviderList();
    if (settingsState.selectedProviderId) {
      const agent = settingsState.agentCatalog.find((item) => item.id === settingsState.selectedProviderId);
      if (agent) fillProviderEditor(agent);
    }
  } else {
    renderRoleList();
    if (settingsState.roleEditorMode === "edit" && settingsState.roleEditorSourceId) {
      const agent = settingsState.agentCatalog.find((item) => item.id === settingsState.roleEditorSourceId);
      if (agent) fillRoleEditor(agent);
      else closeRoleEditor("助手不存在或已删除。");
    } else if (settingsState.roleEditorMode === "create") {
      setRoleEditorChrome("create");
    }
  }
  await refreshExecutorCatalog();
}

export function resetAgentEditor() {
  resetProviderEditor();
  closeRoleEditor();
}

export function resetProviderEditor(message = "选择左侧连接层查看状态。") {
  settingsState.selectedProviderId = "";
  $("providerDetailCard").hidden = true;
  $("providerDetailEmpty").hidden = false;
  $("providerDetailEmpty").textContent = message;
  $("providerTestResult").innerHTML = "";
  $("testProviderBtn").disabled = true;
  renderProviderList();
}

function renderProviderStatusDetail(agent) {
  const detail = $("providerStatusDetail");
  if (!detail) return;
  const missing = Array.isArray(agent.missing) ? agent.missing : [];
  if (missing.length) {
    detail.innerHTML = `
      <div class="provider-status-message">${escapeHtml(agent.status_detail || "缺少配置。")}</div>
      <ul class="provider-missing-list">
        ${missing.map((item) => `<li><code>${escapeHtml(String(item))}</code></li>`).join("")}
      </ul>
    `;
  } else {
    detail.textContent = agent.status_detail || "配置齐全，可测试连接。";
  }
}

function showProviderDetail(agent) {
  $("providerDetailEmpty").hidden = true;
  $("providerDetailCard").hidden = false;
  $("providerDetailTitle").textContent = agent.label || agent.id;
  const statusClass = agent.ready ? "agent-status-ready" : "agent-status-missing";
  const pill = $("providerStatusPill");
  pill.className = `agent-status-pill ${statusClass}`;
  pill.textContent = agentStatusLabel(agent);
  renderProviderStatusDetail(agent);
  $("providerTestResult").innerHTML = "";
  $("testProviderBtn").disabled = false;
}

export function closeRoleEditor(message = "选择左侧助手进行编辑，或点击「新建」。") {
  settingsState.selectedRoleId = "";
  settingsState.roleEditorSourceId = "";
  settingsState.roleEditorMode = "none";
  clearRoleForm();
  $("roleEditorEmpty").hidden = false;
  $("roleEditorEmpty").textContent = message;
  $("roleEditorPanel").hidden = true;
  renderRoleList();
}

export function openCreateRole(agent = blankRole(), options = {}) {
  settingsState.roleEditorMode = "create";
  settingsState.selectedRoleId = "";
  settingsState.roleEditorSourceId = "";
  clearRoleForm();
  populateRoleProviderSelect();
  $("roleAgentId").readOnly = false;
  $("roleAgentLabel").readOnly = false;
  $("roleAgentProvider").disabled = false;
  $("roleAgentIdentName").readOnly = false;
  $("roleAgentIdentRole").readOnly = false;
  $("roleAgentIdentVibe").readOnly = false;
  $("roleAgentSoul").readOnly = false;
  fillRoleForm(agent);
  const titleEl = $("roleEditorModeLabel");
  titleEl.textContent = options.title || "新建助手";
  titleEl.dataset.customTitle = options.title ? "1" : "";
  setRoleEditorChrome("create");
  $("roleAgentMeta").textContent = options.message || "填写配置后点击右上角「创建助手」。";
  renderRoleList();
}

function duplicateCurrentRole() {
  const sourceId = settingsState.roleEditorSourceId;
  if (settingsState.roleEditorMode !== "edit" || !sourceId) {
    ensureAssistantsTab();
    $("roleEditorEmpty").hidden = false;
    $("roleEditorEmpty").textContent = "请先选择要复制的助手。";
    return;
  }
  const agent = settingsState.agentCatalog.find((item) => item.id === sourceId);
  if (!agent) {
    $("roleAgentMeta").textContent = "助手不存在或已删除。";
    return;
  }
  const suffix = Date.now().toString().slice(-4);
  openCreateRole(
    {
      id: `${sourceId}_${suffix}`,
      label: `${agent.label || sourceId} 副本`,
      provider: agent.provider || providers()[0]?.id || "cursor-agent-cli",
      ident: { ...(agent.ident || {}) },
      soul: agent.soul || agent.description || "",
    },
    {
      title: `复制：${agent.label || sourceId}`,
      message: "已复制当前助手配置，修改后点击右上角「创建助手」。",
    },
  );
}

function fillRoleForm(agent) {
  $("roleAgentId").value = agent.id || "";
  $("roleAgentLabel").value = agent.label || agent.id || "";
  $("roleAgentProvider").value = agent.provider || providers()[0]?.id || "";
  const ident = agent.ident || {};
  $("roleAgentIdentName").value = ident.name || "";
  $("roleAgentIdentRole").value = ident.role || "";
  $("roleAgentIdentVibe").value = ident.vibe || "";
  $("roleAgentSoul").value = agent.soul || agent.description || "";
}

function populateRoleProviderSelect() {
  const select = $("roleAgentProvider");
  if (!select) return;
  select.innerHTML = "";
  for (const item of providers()) {
    const option = document.createElement("option");
    option.value = item.provider || item.id;
    option.textContent = `${item.label} · ${item.kind === "cli" ? "CLI" : "API"}`;
    select.appendChild(option);
  }
}

function collectRoleDraftPayload() {
  const payload = collectRoleEditorPayload();
  const draft = {
    id: payload.id,
    label: payload.label,
    provider: payload.provider,
    ident: payload.ident,
    soul: payload.soul,
  };
  return Object.fromEntries(Object.entries(draft).filter(([, value]) => {
    if (value && typeof value === "object") {
      return Object.values(value).some((item) => String(item || "").trim());
    }
    return String(value || "").trim();
  }));
}

function renderAgentGenerateChat() {
  const container = $("agentGenerateChat");
  if (!container) return;
  container.innerHTML = "";
  if (!agentGenerateHistory.length) {
    container.innerHTML = `<div class="muted">还没有对话。可先手动填写部分字段，再在这里描述要如何优化。</div>`;
    return;
  }
  for (const item of agentGenerateHistory) {
    const bubble = document.createElement("div");
    bubble.className = `agent-generate-chat-item ${item.role}`;
    bubble.innerHTML = `
      <div class="agent-generate-chat-role">${item.role === "user" ? "你" : "AI"}</div>
      <div>${escapeHtml(item.content)}</div>
    `;
    container.appendChild(bubble);
  }
  container.scrollTop = container.scrollHeight;
}

function setAgentGenerateProgress(percent, message) {
  const fill = $("agentGenerateProgressFill");
  const label = $("agentGenerateProgressLabel");
  if (fill) fill.style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;
  if (label && message) label.textContent = message;
}

function appendAgentGenerateLog(line) {
  const log = $("agentGenerateLog");
  if (!log || !line) return;
  log.textContent = `${log.textContent}${log.textContent ? "\n" : ""}${line}`;
  log.scrollTop = log.scrollHeight;
}

function resetAgentGenerateDialogState() {
  agentGenerateHistory = [];
  agentGenerateLastAgent = null;
  agentGenerateRunning = false;
  const input = $("agentGenerateInput");
  const log = $("agentGenerateLog");
  const applyBtn = $("applyAgentGenerateBtn");
  if (input) input.value = "";
  if (log) log.textContent = "";
  if (applyBtn) applyBtn.disabled = true;
  setAgentGenerateProgress(0, "可描述需求，也可先填一半表单后再来优化。");
  renderAgentGenerateChat();
}

function summarizeGeneratedAgent(agent) {
  const ident = agent.ident || {};
  return `已生成草稿：${agent.label || agent.id}\n角色：${ident.role || "-"}\n气质：${ident.vibe || "-"}`;
}

async function consumeAgentGenerateStream(response, onEvent) {
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
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      const dataLine = lines.find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      const event = JSON.parse(dataLine.slice(6));
      onEvent(event);
    }
  }
}

async function sendAgentGenerateMessage() {
  const input = $("agentGenerateInput");
  const description = input.value.trim();
  if (!description) {
    setAgentGenerateProgress(0, "请先输入描述。");
    return;
  }
  if (agentGenerateRunning) return;
  agentGenerateRunning = true;
  $("sendAgentGenerateBtn").disabled = true;
  $("applyAgentGenerateBtn").disabled = true;
  agentGenerateHistory.push({ role: "user", content: description });
  renderAgentGenerateChat();
  input.value = "";
  $("agentGenerateLog").textContent = "";
  setAgentGenerateProgress(5, "准备生成...");
  const draft = collectRoleDraftPayload();
  let streamPercent = 5;
  try {
    const response = await fetch("/agents/generate/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description,
        provider: $("agentGenerateProvider").value,
        draft,
        messages: agentGenerateHistory,
      }),
    });
    await consumeAgentGenerateStream(response, (event) => {
      if (event.type === "progress") {
        streamPercent = Number(event.percent) || streamPercent;
        setAgentGenerateProgress(streamPercent, event.message);
      } else if (event.type === "log") {
        appendAgentGenerateLog(event.line);
        streamPercent = Math.min(90, streamPercent + 1);
        setAgentGenerateProgress(streamPercent, "连接层输出中...");
      } else if (event.type === "done") {
        agentGenerateLastAgent = event.agent;
        agentGenerateHistory.push({
          role: "assistant",
          content: summarizeGeneratedAgent(event.agent),
        });
        renderAgentGenerateChat();
        $("applyAgentGenerateBtn").disabled = false;
        setAgentGenerateProgress(100, event.message || "生成完成，可填入表单继续调整。");
      } else if (event.type === "error") {
        throw new Error(event.message || "生成失败。");
      }
    });
  } catch (error) {
    setAgentGenerateProgress(0, error.message);
    agentGenerateHistory.push({ role: "assistant", content: `生成失败：${error.message}` });
    renderAgentGenerateChat();
  } finally {
    agentGenerateRunning = false;
    $("sendAgentGenerateBtn").disabled = false;
  }
}

function populateAgentGenerateProviderSelect() {
  const select = $("agentGenerateProvider");
  if (!select) return;
  select.innerHTML = "";
  for (const item of providers()) {
    const option = document.createElement("option");
    option.value = item.provider || item.id;
    const status = item.ready ? "就绪" : "缺配置";
    option.textContent = `${item.label} · ${item.kind === "cli" ? "CLI" : "API"} (${status})`;
    select.appendChild(option);
  }
  const preferred = providers().find((item) => item.id === "cursor-agent-cli" && item.ready)
    || providers().find((item) => item.ready)
    || providers()[0];
  if (preferred) {
    select.value = preferred.provider || preferred.id;
  }
}

function openAgentGenerateDialog() {
  if (settingsState.roleEditorMode === "none") {
    ensureAssistantsTab();
    openCreateRole();
  }
  populateAgentGenerateProviderSelect();
  resetAgentGenerateDialogState();
  const draft = collectRoleDraftPayload();
  if (Object.keys(draft).length) {
    setAgentGenerateProgress(0, "已读取当前表单内容，将作为上下文一起优化。");
  }
  $("agentGenerateDialog").hidden = false;
  $("agentGenerateInput").focus();
}

function closeAgentGenerateDialog() {
  if (agentGenerateRunning) return;
  $("agentGenerateDialog").hidden = true;
}

function applyGeneratedAgentDraft(agent) {
  fillRoleForm(agent);
  const mode = settingsState.roleEditorMode === "edit" ? "edit" : "create";
  if (mode === "create") {
    $("roleEditorModeLabel").textContent = `新建：${agent.label || agent.id}`;
    $("roleEditorModeLabel").dataset.customTitle = "1";
    $("roleAgentMeta").textContent = "AI 已生成草稿，请确认后点击「创建助手」。";
  } else {
    $("roleEditorModeLabel").textContent = `编辑：${agent.label || agent.id}`;
    $("roleEditorModeLabel").dataset.customTitle = "1";
    $("roleAgentMeta").textContent = "AI 已优化参数，请确认后点击「保存」。";
  }
  setRoleEditorChrome(mode);
  renderRoleList();
}

function applyAgentGenerateResult() {
  if (!agentGenerateLastAgent) return;
  applyGeneratedAgentDraft(agentGenerateLastAgent);
  setAgentGenerateProgress(100, "已填入表单，可继续手动修改或再次对话优化。");
}

function renderProviderList() {
  const container = $("agentProviderList");
  if (!container) return;
  container.innerHTML = "";
  const heading = document.createElement("div");
  heading.className = "agent-list-section-label";
  heading.textContent = "连接层";
  container.appendChild(heading);

  for (const agent of providers()) {
    const card = document.createElement("button");
    card.type = "button";
    const roleCount = countRolesForProvider(agent.id);
    const selected = settingsState.selectedProviderId === agent.id;
    card.className = `skill-card agent-card agent-card-provider${selected ? " selected" : ""}`;
    const statusClass = agent.ready ? "agent-status-ready" : "agent-status-missing";
    card.innerHTML = `
      <div class="agent-card-main">
        <div class="skill-card-title">${escapeHtml(agent.label || agent.id)}</div>
        <div class="skill-card-meta">连接层 · ${escapeHtml(agent.kind === "cli" ? "CLI" : "API")}</div>
        <div class="agent-status-pill ${statusClass}">${escapeHtml(agentStatusLabel(agent))}</div>
      </div>
      <div class="agent-role-count">${roleCount} 个助手</div>
    `;
    card.addEventListener("click", () => {
      loadProviderEditor(agent.id).catch((error) => {
        resetProviderEditor(error.message);
      });
    });
    container.appendChild(card);
  }
}

function renderRoleList() {
  const container = $("agentRoleList");
  if (!container) return;
  container.innerHTML = "";

  const roles = roleAgents();
  if (!roles.length) {
    container.innerHTML = `<div class="muted">暂无助手，点击「新建」。</div>`;
    return;
  }

  for (const role of roles) {
    const provider = providers().find((item) => item.id === role.provider);
    const card = document.createElement("button");
    card.type = "button";
    const selected = settingsState.roleEditorMode === "edit" && settingsState.roleEditorSourceId === role.id;
    card.className = `skill-card agent-card${selected ? " selected" : ""}`;
    const statusClass = role.ready ? "agent-status-ready" : "agent-status-missing";
    card.innerHTML = `
      <div class="agent-card-main">
        <div class="skill-card-title">${escapeHtml(role.label || role.id)}</div>
        <div class="skill-card-meta">${escapeHtml(role.ident?.role || role.id)} · ${escapeHtml(provider?.label || role.provider || "")}</div>
        <div class="agent-status-pill ${statusClass}">${escapeHtml(agentStatusLabel(role))}</div>
      </div>
    `;
    card.addEventListener("click", () => {
      loadRoleEditor(role.id).catch((error) => {
        $("roleAgentMeta").textContent = error.message;
      });
    });
    container.appendChild(card);
  }
}

export async function loadProviderEditor(providerId) {
  const payload = await api(`/agents/${encodeURIComponent(providerId)}`);
  fillProviderEditor(payload.agent);
  renderProviderList();
}

export async function loadRoleEditor(roleId) {
  const payload = await api(`/agents/${encodeURIComponent(roleId)}`);
  fillRoleEditor(payload.agent);
  renderRoleList();
}

export function fillProviderEditor(agent) {
  settingsState.selectedProviderId = agent.id;
  showProviderDetail(agent);
}

export function fillRoleEditor(agent) {
  if (!agent.editable) {
    closeRoleEditor("该助手不可编辑。");
    return;
  }
  settingsState.roleEditorMode = "edit";
  settingsState.roleEditorSourceId = agent.id;
  settingsState.selectedRoleId = agent.id;
  clearRoleForm();
  populateRoleProviderSelect();
  fillRoleForm(agent);
  $("roleAgentId").readOnly = false;
  $("roleAgentLabel").readOnly = false;
  $("roleAgentProvider").disabled = false;
  $("roleAgentIdentName").readOnly = false;
  $("roleAgentIdentRole").readOnly = false;
  $("roleAgentIdentVibe").readOnly = false;
  $("roleAgentSoul").readOnly = false;
  setRoleEditorChrome("edit");
  $("roleAgentMeta").textContent = agent.status_detail || "";
  $("roleAgentTestResult").innerHTML = "";
  renderRoleList();
}

export function collectRoleEditorPayload() {
  return {
    id: $("roleAgentId").value.trim(),
    label: $("roleAgentLabel").value.trim(),
    provider: $("roleAgentProvider").value,
    ident: {
      name: $("roleAgentIdentName").value.trim(),
      role: $("roleAgentIdentRole").value.trim(),
      vibe: $("roleAgentIdentVibe").value.trim(),
    },
    soul: $("roleAgentSoul").value.trim(),
  };
}

function applyTemplateToCreateForm() {
  const templateId = $("agentTemplateSelect")?.value;
  if (!templateId) {
    $("roleAgentMeta").textContent = "请先选择助手模板。";
    return;
  }
  const template = agentTemplates.find((item) => item.template_id === templateId);
  if (!template) return;
  const suffix = Date.now().toString().slice(-4);
  openCreateRole({
    id: `role_${template.template_id}_${suffix}`,
    label: template.label || template.template_id,
    provider: template.provider || "cursor-agent-cli",
    ident: { ...(template.ident || {}) },
    soul: template.soul || "",
  });
  $("roleEditorModeLabel").textContent = `新建：${template.label}`;
  $("roleEditorModeLabel").dataset.customTitle = "1";
  $("roleAgentMeta").textContent = `已应用模板「${template.label}」，确认后点击右上角「创建助手」。`;
}

function renderTestResult(containerId, result, errorMessage = "") {
  const container = $(containerId);
  if (errorMessage) {
    container.innerHTML = `<div class="agent-test-message">${escapeHtml(errorMessage)}</div>`;
    return;
  }
  const statusClass = result.status === "ok" ? "agent-status-ready" : "agent-status-missing";
  container.innerHTML = `
    <div class="agent-status-pill ${statusClass}">${escapeHtml(STATUS_LABELS[result.status] || result.status)}</div>
    <div class="agent-test-message">${escapeHtml(result.message || "")}</div>
    ${result.output ? `<pre class="agent-test-output">${escapeHtml(result.output)}</pre>` : ""}
  `;
}

async function createRoleAgent() {
  if (settingsState.roleEditorMode !== "create") {
    $("roleAgentMeta").textContent = "当前不在新建模式。";
    return;
  }
  const payload = collectRoleEditorPayload();
  if (!payload.id) {
    $("roleAgentMeta").textContent = "请填写 Agent id。";
    return;
  }
  if (!payload.label) {
    $("roleAgentMeta").textContent = "请填写显示名称。";
    return;
  }
  if (roleAgents().some((item) => item.id === payload.id)) {
    $("roleAgentMeta").textContent = `Agent id「${payload.id}」已存在，请换一个。`;
    return;
  }
  const result = await api("/agents", {
    method: "POST",
    body: JSON.stringify({ agent: payload }),
  });
  settingsState.roleEditorMode = "edit";
  settingsState.roleEditorSourceId = result.agent.id;
  settingsState.selectedRoleId = result.agent.id;
  await refreshAgentAssistant();
  fillRoleEditor(result.agent);
  $("roleAgentMeta").textContent = `已创建 ${result.agent.id}`;
}

async function saveRoleAgent() {
  const payload = collectRoleEditorPayload();
  const sourceId = settingsState.roleEditorSourceId;
  if (!sourceId) {
    $("roleAgentMeta").textContent = "未选中要保存的助手。";
    return;
  }
  if (!payload.id) {
    $("roleAgentMeta").textContent = "请填写 Agent id。";
    return;
  }
  if (payload.id !== sourceId && roleAgents().some((item) => item.id === payload.id)) {
    $("roleAgentMeta").textContent = `Agent id「${payload.id}」已存在，请换一个。`;
    return;
  }
  const result = await api(`/agents/${encodeURIComponent(sourceId)}`, {
    method: "PUT",
    body: JSON.stringify({ agent: payload }),
  });
  settingsState.roleEditorSourceId = result.agent.id;
  settingsState.selectedRoleId = result.agent.id;
  await refreshAgentAssistant();
  fillRoleEditor(result.agent);
  $("roleAgentMeta").textContent =
    payload.id !== sourceId ? `已重命名为 ${result.agent.id}` : `已保存 ${result.agent.id}`;
}

async function deleteRoleAgent() {
  const sourceId = settingsState.roleEditorSourceId;
  if (!sourceId) return;
  await api(`/agents/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
  closeRoleEditor("助手已删除");
  await refreshAgentAssistant();
}

async function testProvider() {
  if (!settingsState.selectedProviderId) {
    resetProviderEditor("请先选择连接层。");
    return;
  }
  $("testProviderBtn").disabled = true;
  $("providerTestResult").innerHTML = `<div class="muted">正在测试连接...</div>`;
  try {
    const result = await api(`/agents/${encodeURIComponent(settingsState.selectedProviderId)}/test`, {
      method: "POST",
      body: JSON.stringify({ prompt: DEFAULT_TEST_PROMPT }),
    });
    await refreshAgentAssistant();
    renderTestResult("providerTestResult", result);
  } catch (error) {
    renderTestResult("providerTestResult", null, error.message);
  } finally {
    $("testProviderBtn").disabled = false;
  }
}

async function testRoleAgent() {
  const sourceId = settingsState.roleEditorSourceId;
  if (!sourceId) {
    $("roleAgentMeta").textContent = "请先选择助手。";
    return;
  }
  $("testRoleAgentBtn").disabled = true;
  $("roleAgentMeta").textContent = "测试中...";
  $("roleAgentTestResult").innerHTML = `<div class="muted">正在调用 Agent，请稍候...</div>`;
  try {
    const result = await api(`/agents/${encodeURIComponent(sourceId)}/test`, {
      method: "POST",
      body: JSON.stringify({ prompt: $("roleAgentTestPrompt").value.trim() || DEFAULT_TEST_PROMPT }),
    });
    await refreshAgentAssistant();
    renderTestResult("roleAgentTestResult", result);
    $("roleAgentMeta").textContent = result.message || "测试完成。";
  } catch (error) {
    $("roleAgentMeta").textContent = error.message;
    renderTestResult("roleAgentTestResult", null, error.message);
  } finally {
    $("testRoleAgentBtn").disabled = false;
  }
}

export function mountAgentSettings() {
  document.querySelectorAll("[data-agent-tab]").forEach((button) => {
    button.addEventListener("click", () => setAgentTab(button.getAttribute("data-agent-tab")));
  });

  $("newRoleAgentBtn")?.addEventListener("click", () => {
    ensureAssistantsTab();
    openCreateRole();
  });

  $("duplicateRoleAgentBtn")?.addEventListener("click", () => {
    ensureAssistantsTab();
    duplicateCurrentRole();
  });

  $("applyAgentTemplateBtn")?.addEventListener("click", () => {
    applyTemplateToCreateForm();
  });

  $("openAgentGenerateBtn")?.addEventListener("click", () => {
    openAgentGenerateDialog();
  });

  $("closeAgentGenerateBtn")?.addEventListener("click", closeAgentGenerateDialog);
  $("cancelAgentGenerateBtn")?.addEventListener("click", closeAgentGenerateDialog);
  $("agentGenerateBackdrop")?.addEventListener("click", closeAgentGenerateDialog);
  $("sendAgentGenerateBtn")?.addEventListener("click", () => {
    sendAgentGenerateMessage().catch((error) => {
      setAgentGenerateProgress(0, error.message);
    });
  });
  $("applyAgentGenerateBtn")?.addEventListener("click", () => {
    applyAgentGenerateResult();
  });
  $("agentGenerateInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendAgentGenerateMessage().catch((error) => {
        setAgentGenerateProgress(0, error.message);
      });
    }
  });

  $("cancelRoleEditorBtn")?.addEventListener("click", () => {
    closeRoleEditor();
  });

  $("createRoleAgentBtn")?.addEventListener("click", () => {
    createRoleAgent().catch((error) => {
      $("roleAgentMeta").textContent = error.message;
    });
  });

  $("saveRoleAgentBtn").addEventListener("click", () => {
    saveRoleAgent().catch((error) => {
      $("roleAgentMeta").textContent = error.message;
    });
  });

  $("deleteRoleAgentBtn").addEventListener("click", () => {
    deleteRoleAgent().catch((error) => {
      $("roleAgentMeta").textContent = error.message;
    });
  });

  $("testProviderBtn").addEventListener("click", () => {
    testProvider().catch((error) => {
      renderTestResult("providerTestResult", null, error.message);
    });
  });

  $("testRoleAgentBtn").addEventListener("click", () => {
    testRoleAgent().catch((error) => {
      $("roleAgentMeta").textContent = error.message;
    });
  });
}

export async function loadAgentEditor(agentId) {
  const agent = settingsState.agentCatalog.find((item) => item.id === agentId);
  if (agent?.tier === "provider" || agent?.source === "builtin") {
    setAgentTab("providers");
    await loadProviderEditor(agentId);
  } else {
    setAgentTab("assistants");
    await loadRoleEditor(agentId);
  }
}

export function fillAgentEditor(agent) {
  if (agent?.tier === "provider" || agent?.source === "builtin") {
    fillProviderEditor(agent);
  } else {
    fillRoleEditor(agent);
  }
}

// Backward-compatible aliases
export function resetRoleEditor(message) {
  closeRoleEditor(message);
}
