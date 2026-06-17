import { $ } from "../core/dom.js";
import { api } from "../core/api.js";
import { settingsState } from "./state.js";

function skillSourceLabel(source) {
  if (source === "example") return "草稿";
  if (source === "workspace") return "我的";
  return source || "unknown";
}

function skillField(id) {
  const panel = document.querySelector('[data-settings-panel="skills"]');
  return panel?.querySelector(`#${id}`) || $(id);
}

function setSkillFieldValue(id, value) {
  const field = skillField(id);
  if (field) field.value = value ?? "";
}

function setSkillFieldReadOnly(id, readOnly) {
  const field = skillField(id);
  if (field) field.readOnly = Boolean(readOnly);
}

function setSkillButtonDisplay(id, visible) {
  const button = skillField(id);
  if (button) button.style.display = visible ? "" : "none";
}

function setSkillMeta(message) {
  const meta = skillField("skillMeta");
  if (meta) meta.textContent = message;
}

export function resetSkillEditor(message = "选择或新建 Skill。") {
  settingsState.skillEditorIsNew = false;
  settingsState.selectedSkillId = "";
  settingsState.selectedSkillSource = "";
  settingsState.selectedSkillEditable = false;
  settingsState.selectedSkillCloneFrom = "";
  setSkillFieldValue("skillId", "");
  setSkillFieldReadOnly("skillId", false);
  setSkillFieldValue("skillName", "");
  setSkillFieldValue("skillGoal", "");
  setSkillFieldValue("skillDescription", "");
  setSkillFieldValue("skillExecutor", "");
  setSkillFieldValue("skillPrimaryOutput", "");
  setSkillFieldValue("skillQuality", "");
  setSkillFieldValue("skillMarkdown", "");
  setSkillMeta(message);
  setSkillButtonDisplay("saveSkillBtn", false);
  setSkillButtonDisplay("deleteSkillBtn", false);
  setSkillButtonDisplay("cloneSkillBtn", false);
}

export async function loadSkillEditor(skillId, source = settingsState.skillAssistantSource) {
  const normalizedSource = source || settingsState.skillAssistantSource;
  const withSource =
    normalizedSource && normalizedSource !== "wayland" && normalizedSource !== "market"
      ? `?source=${encodeURIComponent(normalizedSource)}`
      : "";
  try {
    const payload = await api(`/skills/${encodeURIComponent(skillId)}${withSource}`);
    fillSkillEditor(payload);
    return payload;
  } catch (error) {
    if (!withSource) throw error;
    const payload = await api(`/skills/${encodeURIComponent(skillId)}`);
    fillSkillEditor(payload);
    return payload;
  }
}

export function fillSkillEditor(payload) {
  const skill = payload.skill || {};
  const quality = Array.isArray(skill.quality) ? skill.quality : [];
  settingsState.skillEditorIsNew =
    settingsState.skillAssistantSource === "workspace" &&
    Boolean(payload.editable) &&
    (!payload.path || payload.source === "import");
  settingsState.selectedSkillId = settingsState.skillEditorIsNew ? "" : (skill.id || "");
  settingsState.selectedSkillSource = payload.source || settingsState.skillAssistantSource;
  settingsState.selectedSkillEditable = Boolean(payload.editable);
  settingsState.selectedSkillCloneFrom = skill.id || "";
  setSkillFieldValue("skillId", skill.id || "");
  setSkillFieldReadOnly("skillId", Boolean(payload.path && payload.editable));
  setSkillFieldValue("skillName", skill.name || "");
  setSkillFieldValue("skillGoal", skill.goal || "");
  setSkillFieldValue("skillDescription", skill.description || "");
  setSkillFieldValue("skillExecutor", skill.executor || "");
  setSkillFieldValue("skillPrimaryOutput", (skill.output && skill.output.primary) || "");
  setSkillFieldValue("skillQuality", quality.join("\n"));
  setSkillFieldValue("skillMarkdown", payload.markdown || "");
  setSkillMeta(
    settingsState.skillEditorIsNew
      ? payload.source === "import"
        ? "从 SKILL.md 导入 · 填写后点击保存"
        : "新建 Skill · 填写后点击保存"
      : `${skillSourceLabel(payload.source)} · ${payload.editable ? "可编辑" : "只读"} · ${payload.path || ""}`,
  );
  setSkillButtonDisplay(
    "saveSkillBtn",
    settingsState.skillAssistantSource === "workspace" && (payload.editable || !payload.path),
  );
  setSkillButtonDisplay(
    "deleteSkillBtn",
    settingsState.skillAssistantSource === "workspace" && (payload.editable || settingsState.skillEditorIsNew),
  );
  const deleteBtn = skillField("deleteSkillBtn");
  if (deleteBtn) deleteBtn.textContent = settingsState.skillEditorIsNew ? "取消" : "删除";
  setSkillButtonDisplay("cloneSkillBtn", settingsState.skillAssistantSource !== "workspace");
  const cloneBtn = skillField("cloneSkillBtn");
  if (cloneBtn) {
    cloneBtn.textContent =
      settingsState.skillAssistantSource === "wayland"
        ? payload.installed
          ? "已安装"
          : "从 Wayland 导入"
        : settingsState.skillAssistantSource === "market"
          ? payload.installed
            ? "已安装"
            : "安装到工作区"
          : "复制到工作区";
  }
}

export function loadWaylandSkillPreview(item) {
  settingsState.skillEditorIsNew = false;
  settingsState.selectedSkillId = item.id;
  settingsState.selectedSkillSource = item.source || "wayland";
  settingsState.selectedSkillEditable = false;
  setSkillFieldValue("skillId", item.id);
  setSkillFieldReadOnly("skillId", true);
  setSkillFieldValue("skillName", item.name || item.id);
  setSkillFieldValue("skillGoal", item.preview || "");
  setSkillFieldValue("skillDescription", item.preview || "");
  setSkillFieldValue("skillExecutor", "skill");
  setSkillFieldValue("skillPrimaryOutput", `${item.id}.md`);
  setSkillFieldValue("skillQuality", "Follow the imported SKILL.md instructions.");
  setSkillFieldValue("skillMarkdown", "");
  setSkillMeta(`${item.source} · ${item.path} · ${item.installed ? "已安装" : "点击导入安装"}`);
  setSkillButtonDisplay("saveSkillBtn", false);
  setSkillButtonDisplay("deleteSkillBtn", false);
  setSkillButtonDisplay("cloneSkillBtn", true);
  const cloneBtn = skillField("cloneSkillBtn");
  if (cloneBtn) cloneBtn.textContent = item.installed ? "已安装" : "从 Wayland 导入";
}

export function loadMarketSkillPreview(item) {
  settingsState.skillEditorIsNew = false;
  settingsState.selectedSkillId = item.id;
  settingsState.selectedSkillSource = "market";
  settingsState.selectedSkillEditable = false;
  setSkillFieldValue("skillId", item.id);
  setSkillFieldReadOnly("skillId", true);
  setSkillFieldValue("skillName", item.name || item.id);
  setSkillFieldValue("skillGoal", item.description || "");
  setSkillFieldValue("skillDescription", item.description || "");
  setSkillFieldValue("skillExecutor", "skill");
  setSkillFieldValue("skillPrimaryOutput", `${item.id}.md`);
  setSkillFieldValue("skillQuality", "");
  setSkillFieldValue("skillMarkdown", "");
  setSkillMeta(`market · clone_from=${item.clone_from || item.id} · ${item.installed ? "已安装" : "可安装"}`);
  setSkillButtonDisplay("saveSkillBtn", false);
  setSkillButtonDisplay("deleteSkillBtn", false);
  setSkillButtonDisplay("cloneSkillBtn", true);
  const cloneBtn = skillField("cloneSkillBtn");
  if (cloneBtn) cloneBtn.textContent = item.installed ? "已安装" : "安装到工作区";
}

export function primeSkillEditorFromListItem(item) {
  settingsState.selectedSkillId = item.id;
  settingsState.selectedSkillSource = item.source || settingsState.skillAssistantSource;
  settingsState.selectedSkillCloneFrom = item.clone_from || item.id;
  settingsState.selectedSkillEditable = Boolean(item.editable);
  settingsState.skillEditorIsNew = false;
  setSkillFieldValue("skillId", item.id);
  setSkillFieldReadOnly("skillId", true);
  setSkillFieldValue("skillName", item.name || item.id);
  setSkillFieldValue("skillGoal", "");
  setSkillFieldValue("skillDescription", "");
  setSkillFieldValue("skillExecutor", item.executor || "");
  setSkillFieldValue("skillPrimaryOutput", item.has_markdown ? `${item.id}.md` : "");
  setSkillFieldValue("skillQuality", "");
  setSkillFieldValue("skillMarkdown", "");
  setSkillMeta(`加载 ${item.name || item.id}…`);
  setSkillButtonDisplay("saveSkillBtn", false);
  setSkillButtonDisplay("deleteSkillBtn", false);
  setSkillButtonDisplay("cloneSkillBtn", settingsState.skillAssistantSource !== "workspace");
  if (settingsState.skillAssistantSource !== "workspace") {
    const cloneBtn = skillField("cloneSkillBtn");
    if (cloneBtn) {
      cloneBtn.textContent = settingsState.skillAssistantSource === "example" ? "复制到工作区" : "安装到工作区";
    }
  }
}

export function collectSkillEditorPayload() {
  const id = skillField("skillId")?.value.trim() || "";
  const quality = (skillField("skillQuality")?.value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const skill = {
    id,
    name: skillField("skillName")?.value.trim() || id,
    description: skillField("skillDescription")?.value.trim() || "",
    goal: skillField("skillGoal")?.value.trim() || "",
    output: { primary: skillField("skillPrimaryOutput")?.value.trim() || `${id}.md` },
    quality,
  };
  const executor = skillField("skillExecutor")?.value;
  if (executor) skill.executor = executor;
  return {
    skill,
    markdown: skillField("skillMarkdown")?.value || "",
  };
}
