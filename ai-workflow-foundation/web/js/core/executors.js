import { $ } from "./dom.js";
import { api } from "./api.js";

const EXECUTOR_LABELS = {
  mock: "Mock",
  agent: "Agent",
  skill: "Skill 编排",
  openai: "Agent",
};

let catalog = {
  executors: [
    { id: "mock", label: "Mock" },
    { id: "agent", label: "Agent" },
    { id: "skill", label: "Skill 编排" },
  ],
  providers: [],
  role_agents: [],
  agent_providers: [],
  defaults: { executor: "mock", agent_provider: "openai-api" },
};

export function getExecutorCatalog() {
  return catalog;
}

function roleAgents() {
  if (catalog.role_agents?.length) return catalog.role_agents;
  return (catalog.agent_providers || []).filter((item) => item.source === "workspace" || item.tier === "role");
}

function providerById(providerId) {
  const providers = catalog.providers?.length ? catalog.providers : catalog.agent_providers || [];
  return providers.find((item) => item.id === providerId);
}

export async function refreshExecutorCatalog() {
  try {
    catalog = await api("/executors");
    if (!catalog.providers?.length && catalog.agent_providers?.length) {
      catalog.providers = catalog.agent_providers.filter((item) => item.tier === "provider" || !item.source || item.source === "builtin");
    }
    if (!catalog.role_agents?.length) {
      catalog.role_agents = catalog.agent_providers?.filter((item) => item.source === "workspace" || item.tier === "role") || [];
    }
  } catch {
    // Keep fallback catalog when API is unavailable during boot.
  }
  return catalog;
}

export function normalizeExecutorValue(value) {
  if (!value) return "";
  if (value === "openai") return "agent";
  return value;
}

export function fillSelectOptions(select, options, selectedValue = "") {
  if (!select) return;
  select.innerHTML = "";
  for (const option of options) {
    const item = document.createElement("option");
    item.value = option.value;
    item.textContent = option.label;
    select.appendChild(item);
  }
  if (selectedValue) select.value = selectedValue;
}

export function populateExecutorSelect(select, { includeEmpty = false, emptyLabel = "跟随默认" } = {}) {
  if (!select) return;
  const options = [];
  if (includeEmpty) options.push({ value: "", label: emptyLabel });
  for (const item of catalog.executors || []) {
    options.push({ value: item.id, label: item.label || EXECUTOR_LABELS[item.id] || item.id });
  }
  fillSelectOptions(select, options, select.value || "");
}

export function agentProviderStatusLabel(item) {
  if (!item) return "";
  if (item.status === "ok") return "测试通过";
  if (item.ready || item.status === "ready") return "就绪";
  if (item.status === "missing") return "缺配置";
  if (item.status === "error") return "异常";
  return "";
}

export function populateAgentProviderSelect(select, { includeEmpty = false, emptyLabel = "跟随默认" } = {}) {
  populateRoleAgentSelect(select, { includeEmpty, emptyLabel });
}

export function populateRoleAgentSelect(select, { includeEmpty = false, emptyLabel = "跟随默认" } = {}) {
  if (!select) return;
  const options = [];
  if (includeEmpty) options.push({ value: "", label: emptyLabel });
  for (const item of roleAgents()) {
    const provider = providerById(item.provider);
    const providerLabel = provider?.label || item.provider || "";
    const status = agentProviderStatusLabel(item);
    const statusSuffix = status ? ` · ${status}` : "";
    options.push({
      value: item.id,
      label: `${item.label || item.id} · ${providerLabel}${statusSuffix}`,
    });
  }
  fillSelectOptions(select, options, select.value || "");
}

export function syncAgentProviderVisibility(executorSelect, providerField) {
  if (!providerField) return;
  const executor = normalizeExecutorValue(executorSelect?.value || "");
  providerField.hidden = executor !== "agent";
}

export function bindExecutorControls(executorSelect, providerField, providerSelect) {
  if (!executorSelect) return;
  if (executorSelect.dataset.boundExecutor !== "1") {
    executorSelect.dataset.boundExecutor = "1";
    executorSelect.addEventListener("change", () => syncAgentProviderVisibility(executorSelect, providerField));
  }
  syncAgentProviderVisibility(executorSelect, providerField);
}

export function readExecutorPayload(executorSelect, providerSelect, fallback = {}) {
  const rawExecutor = executorSelect?.value ?? fallback.executor ?? "";
  const executor = normalizeExecutorValue(rawExecutor) || normalizeExecutorValue(fallback.executor) || catalog.defaults.executor || "mock";
  const payload = { executor };
  if (executor === "agent") {
    payload.agent_provider =
      providerSelect?.value ||
      fallback.agent_provider ||
      catalog.defaults.agent_provider ||
      "";
  }
  return payload;
}

export function resolveExecutorLabel(node) {
  if (!node || node.type === "review") return "";
  const executor = normalizeExecutorValue(node.executor || "");
  if (executor === "mock") return "Mock";
  if (executor === "skill") return "Skill 编排";
  if (executor === "agent") {
    const role = roleAgents().find((item) => item.id === node.agent_provider);
    if (role) return `Agent · ${role.label || role.id}`;
    const provider = providerById(node.agent_provider);
    return provider ? `Agent · ${provider.label}` : "Agent";
  }
  if (!executor) return "默认";
  return EXECUTOR_LABELS[executor] || executor;
}

export function applyDefaultExecutorControls() {
  populateExecutorSelect($("executor"));
  populateRoleAgentSelect($("agentProvider"));
  bindExecutorControls($("executor"), $("agentProviderField"), $("agentProvider"));
  if ($("executor") && catalog.defaults?.executor) {
    $("executor").value = normalizeExecutorValue(catalog.defaults.executor);
  }
  syncAgentProviderVisibility($("executor"), $("agentProviderField"));
}

export function applyNodeExecutorControls(node) {
  populateExecutorSelect($("nodeExecutor"), { includeEmpty: true, emptyLabel: "默认" });
  populateRoleAgentSelect($("nodeAgentProvider"), { includeEmpty: true, emptyLabel: "跟随全局" });
  bindExecutorControls($("nodeExecutor"), $("nodeAgentProviderField"), $("nodeAgentProvider"));
  if (node) {
    $("nodeExecutor").value = normalizeExecutorValue(node.executor || "");
    $("nodeAgentProvider").value = node.agent_provider || "";
  }
  syncAgentProviderVisibility($("nodeExecutor"), $("nodeAgentProviderField"));
}

export function applyNodeTestExecutorControls(node) {
  populateExecutorSelect($("nodeTestExecutor"), { includeEmpty: true, emptyLabel: "跟随节点 / 默认" });
  populateRoleAgentSelect($("nodeTestAgentProvider"), { includeEmpty: true, emptyLabel: "跟随节点 / 默认" });
  bindExecutorControls($("nodeTestExecutor"), $("nodeTestAgentProviderField"), $("nodeTestAgentProvider"));
  if (node) {
    $("nodeTestExecutor").value = normalizeExecutorValue(node.test_executor || "");
    $("nodeTestAgentProvider").value = node.test_agent_provider || "";
  }
  syncAgentProviderVisibility($("nodeTestExecutor"), $("nodeTestAgentProviderField"));
}

export function syncNodeTestToWorkflow(node) {
  if (!node || !$("nodeTestExecutor")) return;
  const executor = normalizeExecutorValue($("nodeTestExecutor").value);
  if (executor) {
    node.test_executor = executor;
    if (executor === "agent") {
      const provider = $("nodeTestAgentProvider")?.value;
      if (provider) node.test_agent_provider = provider;
      else delete node.test_agent_provider;
    } else {
      delete node.test_agent_provider;
    }
  } else {
    delete node.test_executor;
    delete node.test_agent_provider;
  }
}

export function readGlobalExecutorPayload() {
  return readExecutorPayload($("executor"), $("agentProvider"));
}
