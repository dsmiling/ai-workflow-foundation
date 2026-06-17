import { $ } from "../core/dom.js";
import { api } from "../core/api.js";
import { settingsState } from "./state.js";
import { addOption } from "../workflow/node-form.js";
import { renderSkillAssistantList, selectFirstSkillAssistantItem } from "./skill-list.js";

export {
  collectSkillEditorPayload,
  fillSkillEditor,
  loadMarketSkillPreview,
  loadSkillEditor,
  loadWaylandSkillPreview,
  resetSkillEditor,
} from "./skill-editor.js";
export { renderSkillAssistantList, selectFirstSkillAssistantItem } from "./skill-list.js";

function skillSourceLabel(source) {
  if (source === "example") return "草稿";
  if (source === "workspace") return "我的";
  return source || "unknown";
}

function workspacePreferredSkills(skills) {
  const byId = new Map();
  for (const skill of skills) {
    const existing = byId.get(skill.id);
    if (!existing || skill.source === "workspace") {
      byId.set(skill.id, skill);
    }
  }
  return Array.from(byId.values());
}

export function setSkillSourceTab(source) {
  settingsState.skillAssistantSource = source;
  document.querySelectorAll("[data-skill-source]").forEach((item) => {
    item.classList.toggle("active", item.getAttribute("data-skill-source") === source);
  });
}

export function blankSkill() {
  const suffix = Date.now().toString().slice(-4);
  return {
    id: `skill_${suffix}`,
    name: `Skill ${suffix}`,
    description: "",
    goal: "",
    output: { primary: "output.md" },
    quality: [],
    executor: "skill",
  };
}

export async function ensureSkillApi() {
  const health = await api("/health");
  if ((health.skill_api || 0) < 2) {
    throw new Error("后端 Skill API 版本过旧。请完全退出 AIWF 应用后重新启动 Launch-AIWF.ps1。");
  }
}

export async function refreshSkillCatalog() {
  const payload = await api("/skills");
  settingsState.skillCatalog = payload.skills || [];
  const select = $("nodeSkill");
  const current = select.value;
  select.innerHTML = '<option value="">(none)</option>';
  for (const skill of workspacePreferredSkills(settingsState.skillCatalog)) {
    addOption("nodeSkill", skill.id, `${skill.name} [${skillSourceLabel(skill.source)}]`);
  }
  if (current) select.value = current;
  if ($("settingsPage").classList.contains("active") && document.querySelector('[data-settings-panel="skills"].active')) {
    renderSkillAssistantList();
  }
}

export async function refreshSkillAssistant({ selectFirst = false } = {}) {
  await ensureSkillApi();
  await refreshSkillCatalog();
  if (settingsState.skillAssistantSource === "wayland") {
    const payload = await api("/skills/sources/wayland");
    settingsState.waylandSkillCatalog = payload.skills || [];
  }
  if (settingsState.skillAssistantSource === "market") {
    const payload = await api("/skills/market/catalog");
    settingsState.marketSkillCatalog = payload.skills || [];
  }
  renderSkillAssistantList();
  if (selectFirst) {
    await selectFirstSkillAssistantItem();
  }
}

export async function previewSkillMarkdown(markdown, skillId = "") {
  return api("/skills/import/markdown/preview", {
    method: "POST",
    body: JSON.stringify({
      markdown,
      skill_id: skillId || undefined,
    }),
  });
}

export async function importSkillMarkdown(markdown, options = {}) {
  return api("/skills/import/markdown", {
    method: "POST",
    body: JSON.stringify({
      markdown,
      skill_id: options.skillId || undefined,
      new_id: options.newId || undefined,
      markdown_path: options.markdownPath || undefined,
    }),
  });
}
