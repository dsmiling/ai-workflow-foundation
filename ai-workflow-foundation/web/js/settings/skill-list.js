import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/dom.js";
import { settingsState } from "./state.js";
import {
  loadMarketSkillPreview,
  loadSkillEditor,
  loadWaylandSkillPreview,
  primeSkillEditorFromListItem,
} from "./skill-editor.js";

function skillSourceLabel(source) {
  if (source === "example") return "草稿";
  if (source === "workspace") return "我的";
  return source || "unknown";
}

function setSkillMeta(message) {
  const panel = document.querySelector('[data-settings-panel="skills"]');
  const meta = panel?.querySelector("#skillMeta") || $("skillMeta");
  if (meta) meta.textContent = message;
}

function getSkillAssistantItems() {
  if (settingsState.skillAssistantSource === "workspace") {
    return settingsState.skillCatalog.filter((item) => item.source === "workspace");
  }
  if (settingsState.skillAssistantSource === "example") {
    return settingsState.skillCatalog.filter((item) => item.source === "example");
  }
  if (settingsState.skillAssistantSource === "wayland") {
    return settingsState.waylandSkillCatalog;
  }
  if (settingsState.skillAssistantSource === "market") {
    return settingsState.marketSkillCatalog;
  }
  return [];
}

function isSkillAssistantItemSelected(item) {
  if (item.id !== settingsState.selectedSkillId) return false;
  if (settingsState.skillAssistantSource === "market") {
    return settingsState.selectedSkillSource === "market";
  }
  if (settingsState.skillAssistantSource === "wayland") {
    return (item.source || "wayland") === (settingsState.selectedSkillSource || "wayland");
  }
  return item.source === settingsState.selectedSkillSource;
}

export function renderSkillAssistantList() {
  const box = $("skillList");
  box.innerHTML = "";
  const items = getSkillAssistantItems();
  if (!items.length) {
    box.innerHTML = '<div class="empty-state">暂无 Skill。</div>';
    return;
  }
  for (const item of items) {
    const card = document.createElement("button");
    card.type = "button";
    const className =
      settingsState.skillAssistantSource === "market"
        ? "market-card"
        : settingsState.skillAssistantSource === "wayland"
          ? "wayland-card"
          : "skill-card";
    card.className = `${className}${isSkillAssistantItemSelected(item) ? " selected" : ""}`;
    const meta =
      settingsState.skillAssistantSource === "wayland"
        ? `${item.source} · ${item.installed ? "已安装" : "未安装"}`
        : settingsState.skillAssistantSource === "market"
          ? `${item.installed ? "已安装" : "可安装"} · ${(item.tags || []).join(", ")}`
          : `${skillSourceLabel(item.source)} · ${item.executor || "default"} · ${item.has_markdown ? "含 SKILL.md" : "仅 JSON"}`;
    card.innerHTML = `
      <div class="skill-card-title">${escapeHtml(item.name || item.id)}</div>
      <div class="skill-card-meta">${escapeHtml(item.id)}</div>
      <div class="skill-card-meta">${escapeHtml(meta)}</div>
    `;
    card.addEventListener("click", () => {
      void selectSkillAssistantItem(item);
    });
    box.appendChild(card);
  }
}

async function selectSkillAssistantItem(item) {
  try {
    if (settingsState.skillAssistantSource === "wayland") {
      settingsState.selectedSkillId = item.id;
      settingsState.selectedSkillSource = item.source || "wayland";
      settingsState.selectedSkillCloneFrom = item.clone_from || item.id;
      renderSkillAssistantList();
      loadWaylandSkillPreview(item);
      return;
    }
    if (settingsState.skillAssistantSource === "market") {
      settingsState.selectedSkillId = item.id;
      settingsState.selectedSkillSource = "market";
      settingsState.selectedSkillCloneFrom = item.clone_from || item.id;
      renderSkillAssistantList();
      loadMarketSkillPreview(item);
      return;
    }
    primeSkillEditorFromListItem(item);
    renderSkillAssistantList();
    await loadSkillEditor(item.id, item.source);
  } catch (error) {
    setSkillMeta(error.message || "加载 Skill 失败。");
  }
}

export async function selectFirstSkillAssistantItem() {
  const items = getSkillAssistantItems();
  if (!items.length) return;
  await selectSkillAssistantItem(items[0]);
}
