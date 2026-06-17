import { $ } from "../core/dom.js";
import { refreshSkillAssistant } from "./skills.js";
import { refreshAgentAssistant, resetAgentEditor, setAgentTab } from "./agents.js";
import { settingsState } from "./state.js";

export function setSettingsView(view) {
  document.querySelectorAll("[data-settings-view]").forEach((button) => {
    button.classList.toggle("active", button.getAttribute("data-settings-view") === view);
  });
  document.querySelectorAll("[data-settings-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.getAttribute("data-settings-panel") === view);
  });
  if (view === "skills") {
    refreshSkillAssistant({ selectFirst: true }).catch((error) => {
      $("skillMeta").textContent = error.message;
    });
  }
  if (view === "agents") {
    resetAgentEditor();
    setAgentTab(settingsState.agentTab || "providers");
    refreshAgentAssistant().catch((error) => {
      const meta = settingsState.agentTab === "providers" ? $("providerDetailEmpty") : $("roleAgentMeta");
      if (meta) meta.textContent = error.message;
    });
  }
}
