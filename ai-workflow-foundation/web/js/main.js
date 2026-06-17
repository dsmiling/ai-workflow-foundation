import { $ } from "./core/dom.js";
import { setLog } from "./core/log.js";
import { initWorkflow } from "./workflow/index.js";

let settingsMounted = false;

async function ensureSettingsMounted() {
  if (settingsMounted) return;
  const { mountSettings } = await import("./settings/index.js");
  mountSettings();
  settingsMounted = true;
}

function bindMainNavigation() {
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const pageId = button.getAttribute("data-page");
      document.querySelectorAll("[data-page]").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === pageId));
      if (pageId === "settingsPage") {
        ensureSettingsMounted()
          .then(() => import("./settings/general.js"))
          .then(({ setSettingsView }) => {
            setSettingsView(document.querySelector("[data-settings-view].active")?.getAttribute("data-settings-view") || "general");
          })
          .catch((error) => setLog(error.message));
      }
    });
  });
}

bindMainNavigation();
initWorkflow().catch((error) => {
  $("health").textContent = error.message;
  setLog(error.message);
});
