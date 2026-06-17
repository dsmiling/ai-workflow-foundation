import { $ } from "../core/dom.js";
import { api } from "../core/api.js";
import { setSettingsView } from "./general.js";
import {
  blankSkill,
  collectSkillEditorPayload,
  fillSkillEditor,
  loadSkillEditor,
  previewSkillMarkdown,
  refreshSkillAssistant,
  renderSkillAssistantList,
  resetSkillEditor,
  setSkillSourceTab,
} from "./skills.js";
import { mountAgentSettings, refreshAgentAssistant, resetAgentEditor } from "./agents.js";
import { settingsState } from "./state.js";

let mounted = false;

export function mountSettings() {
  if (mounted) return;
  mounted = true;

  document.querySelectorAll("[data-settings-view]").forEach((button) => {
    button.addEventListener("click", () => setSettingsView(button.getAttribute("data-settings-view")));
  });

  document.querySelectorAll("[data-skill-source]").forEach((button) => {
    button.addEventListener("click", () => {
      setSkillSourceTab(button.getAttribute("data-skill-source"));
      refreshSkillAssistant({ selectFirst: true }).catch((error) => {
        $("skillMeta").textContent = error.message;
      });
    });
  });

  $("newSkillBtn").addEventListener("click", () => {
    setSkillSourceTab("workspace");
    settingsState.selectedSkillEditable = true;
    settingsState.selectedSkillSource = "workspace";
    fillSkillEditor({
      skill: blankSkill(),
      markdown: "# Skill Instructions\n\nDescribe how this skill should execute.\n",
      source: "workspace",
      editable: true,
      path: "",
    });
    renderSkillAssistantList();
  });

  $("importSkillBtn").addEventListener("click", () => {
    $("importSkillFile").click();
  });

  $("importSkillFile").addEventListener("change", async () => {
    const input = $("importSkillFile");
    const file = input.files && input.files[0];
    input.value = "";
    if (!file) return;
    try {
      const markdown = await file.text();
      const preview = await previewSkillMarkdown(markdown);
      setSkillSourceTab("workspace");
      settingsState.selectedSkillEditable = true;
      settingsState.selectedSkillSource = "workspace";
      fillSkillEditor(preview);
      if (preview.conflict) {
        const suffix = Date.now().toString().slice(-4);
        $("skillId").value = `${preview.skill.id}_${suffix}`;
        $("skillMeta").textContent = `已从 ${file.name} 解析 · id 冲突，已建议新 id，确认后保存`;
      } else {
        $("skillMeta").textContent = `已从 ${file.name} 解析 · 确认后点击保存导入`;
      }
      renderSkillAssistantList();
    } catch (error) {
      $("skillMeta").textContent = error.message;
    }
  });

  $("saveSkillBtn").addEventListener("click", async () => {
    try {
      const payload = collectSkillEditorPayload();
      if (!payload.skill.id) {
        $("skillMeta").textContent = "请填写 Skill id。";
        return;
      }
      const isUpdate =
        !settingsState.skillEditorIsNew &&
        settingsState.selectedSkillEditable &&
        settingsState.selectedSkillId &&
        settingsState.selectedSkillId === payload.skill.id;
      const method = isUpdate ? "PUT" : "POST";
      const path = isUpdate ? `/skills/${encodeURIComponent(payload.skill.id)}` : "/skills";
      const result = await api(path, {
        method,
        body: JSON.stringify(payload),
      });
      settingsState.skillEditorIsNew = false;
      settingsState.selectedSkillId = result.skill.id;
      settingsState.selectedSkillSource = "workspace";
      settingsState.selectedSkillEditable = true;
      setSkillSourceTab("workspace");
      $("skillMeta").textContent = `已保存 ${result.skill.id}`;
      await refreshSkillAssistant();
      await loadSkillEditor(result.skill.id, "workspace");
    } catch (error) {
      $("skillMeta").textContent = error.message;
    }
  });

  $("cloneSkillBtn").addEventListener("click", async () => {
    if (!settingsState.selectedSkillId) return;
    const currentSource = settingsState.skillAssistantSource;
    const clonedSkillId = settingsState.selectedSkillId;
    const clonedSkillSource = settingsState.selectedSkillSource || currentSource;
    try {
      if (currentSource === "wayland") {
        await api("/skills/import/wayland", {
          method: "POST",
          body: JSON.stringify({ skill_id: settingsState.selectedSkillId }),
        });
        $("skillMeta").textContent = `已从 Wayland 导入 ${settingsState.selectedSkillId}`;
      } else if (currentSource === "market") {
        await api("/skills/market/install", {
          method: "POST",
          body: JSON.stringify({ skill_id: settingsState.selectedSkillId }),
        });
        $("skillMeta").textContent = `已从市场安装 ${settingsState.selectedSkillId}`;
      } else {
        await api(`/skills/${encodeURIComponent(settingsState.selectedSkillCloneFrom || settingsState.selectedSkillId)}/clone`, {
          method: "POST",
          body: JSON.stringify({ new_id: settingsState.selectedSkillId }),
        });
        $("skillMeta").textContent =
          currentSource === "example"
            ? `已复制 ${settingsState.selectedSkillCloneFrom || settingsState.selectedSkillId} 到工作区，草稿仍保留`
            : `已复制 ${settingsState.selectedSkillCloneFrom || settingsState.selectedSkillId}`;
      }
      if (currentSource === "example") {
        await refreshSkillAssistant();
        await loadSkillEditor(clonedSkillId, clonedSkillSource);
        return;
      }
      setSkillSourceTab("workspace");
      await refreshSkillAssistant();
      await loadSkillEditor(clonedSkillId, "workspace");
    } catch (error) {
      $("skillMeta").textContent = error.message;
    }
  });

  $("deleteSkillBtn").addEventListener("click", async () => {
    try {
      if (settingsState.skillEditorIsNew) {
        resetSkillEditor();
        renderSkillAssistantList();
        return;
      }
      if (!settingsState.selectedSkillId || !settingsState.selectedSkillEditable) return;
      await api(`/skills/${encodeURIComponent(settingsState.selectedSkillId)}`, { method: "DELETE" });
      resetSkillEditor("Skill 已删除");
      await refreshSkillAssistant();
    } catch (error) {
      $("skillMeta").textContent = error.message;
    }
  });

  mountAgentSettings();
}
